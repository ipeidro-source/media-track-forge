"""Independent metadata validation, with explicit uncertainty and timing evidence."""

import re
import stat
from fractions import Fraction
from pathlib import Path
from typing import Literal

from mediatrack_forge.application.execution_ports import Inspector
from mediatrack_forge.application.inspection import InspectionError
from mediatrack_forge.domain.execution import ValidationCheck, ValidationReport
from mediatrack_forge.domain.media import Stream
from mediatrack_forge.domain.metadata import metadata_value
from mediatrack_forge.domain.planning import OperationPlan
from mediatrack_forge.infrastructure.srt import validate_srt


def _rational(value: str | None) -> float | None:
    try:
        number = float(Fraction(value)) if value else 0.0
        return number if number > 0 else None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def stream_duration(stream: Stream) -> float | None:
    if stream.duration_seconds is not None:
        return stream.duration_seconds
    # Matroska's available DURATION tag is timing evidence, not fabricated domain metadata.
    value = dict(stream.tags).get("DURATION", "")
    if re.fullmatch(r"\d+:\d{2}:\d{2}(?:\.\d+)?", value):
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return None


def timing_budget(streams: tuple[Stream, ...]) -> float | None:
    """Two timestamp ticks plus one available frame/packet boundary, not a fixed ms limit."""
    ticks: list[float] = []
    boundaries: list[float] = []
    for stream in streams:
        tick = _rational(stream.properties.time_base)
        if tick is not None:
            ticks.append(tick)
        rate = _rational(stream.properties.average_frame_rate)
        if stream.kind == "video" and rate is not None:
            boundaries.append(1 / rate)
        sample_rate = stream.properties.sample_rate_hz
        if sample_rate and stream.codec in ("aac", "mp3"):
            boundaries.append((1024 if stream.codec == "aac" else 1152) / sample_rate)
    if not ticks and not boundaries:
        return None
    return 2 * max(ticks, default=0) + max(boundaries, default=0)


class FFprobeOutputValidator:
    def validate(
        self, plan: OperationPlan, path: Path, inspector: Inspector, timeout_seconds: float
    ) -> ValidationReport:
        expected = tuple((s.source_stream.kind, s.target_codec) for s in plan.included)
        checks: list[ValidationCheck] = []

        def check(
            code: str,
            condition: bool,
            detail: str,
            index: int | None = None,
            *,
            uncertain: bool = False,
        ) -> None:
            status: Literal["passed", "warning", "error"] = (
                "passed" if condition else "warning" if uncertain else "error"
            )
            checks.append(ValidationCheck(code, status, detail, index))

        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                raise ValueError("Missing, empty or nonregular output")
            observed = inspector.inspect(path, timeout_seconds=timeout_seconds)
        except (OSError, ValueError, InspectionError):
            return ValidationReport(
                expected,
                None,
                (
                    ValidationCheck(
                        "OUTPUT_UNREADABLE",
                        "error",
                        "Staged output must be nonempty and probeable.",
                    ),
                ),
            )
        check("OUTPUT_FILE", True, "Staged output is a nonempty regular probeable file.")
        names = (observed.format.name or "").split(",")
        profile_matches = ("matroska" if plan.output.container == "mkv" else "mp4") in names
        if (
            plan.output.container == "mp4"
            and dict(observed.format.tags).get("major_brand") == "qt  "
        ):
            profile_matches = (
                False  # MOV shares ffprobe's alias family but is not this output profile.
            )
        check(
            "CONTAINER",
            profile_matches,
            "Detected container must match the approved output profile.",
        )
        check(
            "STREAM_COUNT",
            len(observed.streams) == len(expected),
            "No mapped stream may be missing or unexpected.",
        )
        for key, value in plan.output_format_tags:
            check(
                "FORMAT_METADATA",
                metadata_value(observed.format.tags, key) == value,
                f"Preserved container tag {key} must match the source.",
            )
        for planned, actual in zip(plan.included, observed.streams, strict=False):
            source = planned.source_stream
            index = planned.output_index
            check(
                "STREAM_KIND",
                actual.kind == source.kind,
                "Expected output stream kind/order.",
                index,
            )
            check(
                "STREAM_CODEC",
                actual.codec == planned.target_codec,
                "Expected copied codec or approved subtitle conversion.",
                index,
            )
            for field in ("width", "height", "channels", "sample_rate_hz"):
                value = getattr(source.properties, field)
                if value is not None:
                    check(
                        "STREAM_TECHNICAL_PROPERTIES",
                        getattr(actual.properties, field) == value,
                        "Mapped stream technical identity must remain consistent.",
                        index,
                    )
            tags = dict(planned.output_tags)
            uncertain_mp4 = plan.output.container == "mp4" and "MP4_METADATA_UNCERTAIN" in {
                issue.code for issue in plan.issues if issue.reference == planned.reference
            }
            for key, value in tags.items():
                und = plan.output.container == "mkv" and key == "language" and value == "und"
                observed_value = metadata_value(actual.tags, key)
                matches = (
                    observed_value == value
                    or (not value and not observed_value)
                    or (und and observed_value is None)
                )
                check(
                    "STREAM_METADATA",
                    matches,
                    f"Validate supported {key} metadata.",
                    index,
                    uncertain=uncertain_mp4 and key in ("language", "title"),
                )
            for key in ("default", "forced"):
                desired = dict(planned.output_disposition).get(key, 0)
                check(
                    "STREAM_DISPOSITION",
                    dict(actual.disposition).get(key, 0) == desired,
                    f"Validate explicit {key} disposition without automatic selection.",
                    index,
                    uncertain=uncertain_mp4,
                )
        uncertain_codes = {issue.code for issue in plan.issues if issue.severity == "warning"}
        for issue in plan.issues:
            if issue.severity == "warning":
                checks.append(ValidationCheck(issue.code, "warning", issue.message))
        budget = timing_budget(tuple(s.source_stream for s in plan.included) + observed.streams)
        for planned, actual in zip(plan.included, observed.streams, strict=False):
            if planned.source_stream.kind not in ("video", "audio"):
                continue
            before, after = stream_duration(planned.source_stream), stream_duration(actual)
            self._duration(checks, before, after, budget, planned.output_index)

        durations = [
            stream_duration(s.source_stream)
            for s in plan.included
            if s.source_stream.kind in ("video", "audio")
        ]
        if durations and all(value is not None for value in durations):
            expected_duration = max(value for value in durations if value is not None)
            for track in plan.external_tracks:
                if any(s.reference.source == track.source for s in plan.included):
                    expected_duration = max(
                        expected_duration,
                        max(cue.end_ms / 1000 for cue in validate_srt(track.source.path)),
                    )
            self._duration(
                checks, expected_duration, observed.format.duration_seconds, budget, None
            )
        elif len(plan.sources) == 1:
            # Container duration is an estimate: excluded long streams can affect this bound.
            all_media_selected = sum(
                s.kind in ("video", "audio") for s in plan.sources[0].streams
            ) == len(durations)
            if all_media_selected:
                self._duration(
                    checks,
                    plan.sources[0].format.duration_seconds,
                    observed.format.duration_seconds,
                    budget,
                    None,
                )
            checks.append(
                ValidationCheck(
                    "DURATION_ESTIMATE_UNCERTAIN",
                    "warning",
                    "Container estimates cannot prove each selected stream is complete.",
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    "DURATION_UNVERIFIED",
                    "warning",
                    "Available metadata does not establish a common duration.",
                )
            )

        chapters = (
            plan.sources[plan.chapter_input_index].chapters
            if plan.chapter_input_index is not None
            else ()
        )
        check(
            "CHAPTER_COUNT",
            len(observed.chapters) == len(chapters),
            "Only promised chapters may be present.",
        )
        for wanted, actual_chapter in zip(chapters, observed.chapters, strict=False):
            check("CHAPTER_TITLE", wanted.title == actual_chapter.title, "Promised chapter title.")
            for before, after in (
                (wanted.start_seconds, actual_chapter.start_seconds),
                (wanted.end_seconds, actual_chapter.end_seconds),
            ):
                if before is not None and after is not None and budget is not None:
                    check(
                        "CHAPTER_TIME",
                        abs(before - after) <= budget,
                        "Chapter movement must stay within metadata-derived timing boundaries.",
                    )
                else:
                    check(
                        "CHAPTER_TIME_UNVERIFIED",
                        False,
                        "Chapter timing cannot be established.",
                        uncertain="CHAPTER_TIMESTAMPS_UNCERTAIN" in uncertain_codes,
                    )
        return ValidationReport(expected, observed, tuple(checks))

    @staticmethod
    def _duration(
        checks: list[ValidationCheck],
        before: float | None,
        after: float | None,
        budget: float | None,
        index: int | None,
    ) -> None:
        if before is None:
            checks.append(
                ValidationCheck(
                    "DURATION_UNVERIFIED",
                    "warning",
                    "Expected source duration is unavailable; duration integrity is unverified.",
                    index,
                    before,
                    after,
                    budget,
                )
            )
        elif after is None:
            checks.append(
                ValidationCheck(
                    "DURATION_UNVERIFIABLE",
                    "error",
                    "Known source duration cannot be verified in the output.",
                    index,
                    before,
                    after,
                    budget,
                )
            )
        elif budget is None:
            checks.append(
                ValidationCheck(
                    "DURATION_TOLERANCE_UNAVAILABLE",
                    "error",
                    "Known source duration requires a reliable metadata-derived timing tolerance.",
                    index,
                    before,
                    after,
                    budget,
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    "DURATION",
                    "passed" if abs(before - after) <= budget else "error",
                    "Compare durations using timestamp ticks and known frame/packet boundaries.",
                    index,
                    before,
                    after,
                    budget,
                )
            )

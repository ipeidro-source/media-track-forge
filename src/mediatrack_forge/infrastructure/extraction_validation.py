"""Elementary output validation with independent selected-packet completeness evidence."""

import json
import os
import shutil
from pathlib import Path

from mediatrack_forge.application.execution_ports import Inspector
from mediatrack_forge.application.inspection import InspectionError
from mediatrack_forge.domain.execution import ValidationCheck, ValidationReport
from mediatrack_forge.domain.extraction import ExtractionPlan
from mediatrack_forge.domain.planning import OperationPlan
from mediatrack_forge.infrastructure.ffprobe import run_bounded
from mediatrack_forge.infrastructure.output_validation import (
    FFprobeOutputValidator,
    stream_duration,
    timing_budget,
)
from mediatrack_forge.infrastructure.srt import validate_srt


def packet_count(path: Path, index: int, executable: str | None, timeout: float) -> int:
    binary = shutil.which(executable or "ffprobe")
    if binary is None or (os.name == "nt" and Path(binary).suffix.lower() not in (".exe", ".com")):
        raise ValueError("Native ffprobe required")
    raw = run_bounded(
        [
            binary,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-select_streams",
            str(index),
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "json",
            "-i",
            str(path),
        ],
        timeout,
    )
    data = json.loads(raw)
    streams = data["streams"]
    if len(streams) != 1:
        raise ValueError("Exactly one counted stream required")
    count = int(streams[0]["nb_read_packets"])
    if count <= 0:
        raise ValueError("Nonempty packets required")
    return count


class ExtractionValidator:
    def __init__(self, ffprobe: str | None = None) -> None:
        self._ffprobe = ffprobe

    def validate(
        self, plan: OperationPlan, path: Path, inspector: Inspector, timeout_seconds: float
    ) -> ValidationReport:
        checks: list[ValidationCheck] = []
        expected = tuple((s.source_stream.kind, s.target_codec) for s in plan.included)
        observed = None
        try:
            if not isinstance(plan, ExtractionPlan) or len(plan.included) != 1:
                raise ValueError
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError
            observed = inspector.inspect(path, timeout_seconds=timeout_seconds)
            selected = plan.included[0]
            actual_format = "aac" if plan.output.container == "adts" else plan.output.container
            if (
                observed.format.name != actual_format
                or len(observed.streams) != 1
                or observed.chapters
            ):
                raise ValueError
            actual = observed.streams[0]
            if (actual.kind, actual.codec) != expected[0]:
                raise ValueError
            for field in ("width", "height", "channels", "sample_rate_hz"):
                value = getattr(selected.source_stream.properties, field)
                if value is not None and value != getattr(actual.properties, field):
                    raise ValueError
            before = packet_count(
                selected.reference.source.path,
                selected.reference.index,
                self._ffprobe,
                timeout_seconds,
            )
            after = packet_count(path, actual.index, self._ffprobe, timeout_seconds)
            if before != after:
                raise ValueError
            checks.append(
                ValidationCheck(
                    "EXTRACTION_PACKET_COUNT",
                    "passed",
                    "Independent full packet scan matched selected source/output packet counts.",
                )
            )
            if actual.kind == "subtitle":
                cues = validate_srt(path, require_suffix=False)
                if len(cues) != after:
                    raise ValueError
            else:
                source_duration = stream_duration(selected.source_stream)
                output_duration = stream_duration(actual)
                if source_duration is not None and output_duration is not None:
                    budget = timing_budget((selected.source_stream, actual))
                    rate = selected.source_stream.properties.sample_rate_hz
                    if selected.source_stream.codec == "aac" and rate and budget is not None:
                        # MP4 edit lists trim encoder priming/end padding; ADTS cannot store them.
                        budget += 2 * 1024 / rate
                    FFprobeOutputValidator._duration(
                        checks,
                        source_duration,
                        output_duration,
                        budget,
                        0,
                    )
                else:
                    checks.append(
                        ValidationCheck(
                            "EXTRACTION_TIMING_PACKET_VERIFIED",
                            "warning",
                            "Elementary timing unavailable; packet counts and codec properties "
                            "check truncation, not complete decoding or content identity.",
                        )
                    )
            checks.append(
                ValidationCheck(
                    "EXTRACTION_LAYOUT",
                    "passed",
                    "Actual elementary format, single codec and technical properties matched.",
                )
            )
        except (OSError, ValueError, KeyError, TypeError, InspectionError):
            checks.append(
                ValidationCheck(
                    "EXTRACTION_INVALID",
                    "error",
                    "Extracted format, codec, structure or packet completeness validation failed.",
                )
            )
        return ValidationReport(expected, observed, tuple(checks))

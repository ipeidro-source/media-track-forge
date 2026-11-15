"""Elementary output validation with independent selected-packet completeness evidence."""

import json
import math
import os
import shutil
from pathlib import Path

from mediatrack_forge.application.control import CancellationToken
from mediatrack_forge.application.execution_ports import Inspector
from mediatrack_forge.application.inspection import InspectionError
from mediatrack_forge.domain.execution import ExecutionFailure, ValidationCheck, ValidationReport
from mediatrack_forge.domain.extraction import ExtractionPlan
from mediatrack_forge.domain.planning import OperationPlan
from mediatrack_forge.infrastructure.ffprobe import run_bounded
from mediatrack_forge.infrastructure.output_validation import (
    FFprobeOutputValidator,
    stream_duration,
    timing_budget,
)
from mediatrack_forge.infrastructure.packet_probe import PacketScanError, probe_failure
from mediatrack_forge.infrastructure.srt import validate_srt
from mediatrack_forge.infrastructure.subtitle_packets import plain_text, subtitle_cues


def packet_count(
    path: Path,
    index: int,
    executable: str | None,
    timeout: float,
    *,
    cancellation: CancellationToken | None = None,
) -> int:
    if not math.isfinite(timeout) or timeout <= 0:
        raise PacketScanError("INVALID_TIMEOUT", "Packet scan requires a finite positive timeout.")
    if isinstance(index, bool) or index < 0:
        raise PacketScanError("INVALID_INDEX", "Select a nonnegative original stream index.")
    try:
        binary = shutil.which(executable or "ffprobe")
    except (OSError, ValueError) as exc:
        raise PacketScanError(
            "EXECUTABLE", "Cannot resolve the native ffprobe executable."
        ) from exc
    if binary is None or (os.name == "nt" and Path(binary).suffix.lower() not in (".exe", ".com")):
        raise PacketScanError("EXECUTABLE", "Select an available native ffprobe executable.")
    arguments = [
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
    ]
    try:
        raw = (
            run_bounded(arguments, timeout, cancellation=cancellation)
            if cancellation is not None
            else run_bounded(arguments, timeout)
        )
    except InspectionError as exc:
        raise probe_failure(exc) from exc
    except OSError as exc:
        raise PacketScanError(
            "IO", "Packet probe I/O failed; check file and tool availability."
        ) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PacketScanError(
            "JSON_INVALID", "Packet probe returned invalid JSON; check ffprobe."
        ) from exc
    if not isinstance(data, dict):
        raise PacketScanError(
            "STREAM_LAYOUT", "Packet probe response must contain one selected stream."
        )
    streams = data.get("streams")
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise PacketScanError(
            "STREAM_LAYOUT", "Packet probe did not return exactly one selected stream."
        )
    value = streams[0].get("nb_read_packets")
    if value is None or value == "N/A":
        raise PacketScanError(
            "COUNT_UNAVAILABLE", "ffprobe did not provide a packet count for the selected stream."
        )
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise PacketScanError(
            "COUNT_INVALID", "Packet count must be a nonnegative decimal integer."
        )
    if isinstance(value, str) and (not value.isascii() or not value.isdecimal()):
        raise PacketScanError(
            "COUNT_INVALID", "Packet count must be a nonnegative decimal integer."
        )
    try:
        count = int(value)
    except ValueError as exc:
        raise PacketScanError(
            "COUNT_INVALID", "Packet count cannot be represented safely."
        ) from exc
    if not 0 <= count <= 2**63 - 1:
        raise PacketScanError(
            "COUNT_INVALID", "Packet count is outside the supported integer range."
        )
    if count == 0:
        raise PacketScanError(
            "COUNT_EMPTY", "No packets were counted for the selected stream; inspect that track."
        )
    return count


class ExtractionValidator:
    def __init__(
        self,
        ffprobe: str | None = None,
        *,
        packet_scan_timeout_seconds: float = 300.0,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self._ffprobe = ffprobe
        self._scan_timeout = packet_scan_timeout_seconds
        self._cancellation = cancellation

    def validate(
        self, plan: OperationPlan, path: Path, inspector: Inspector, timeout_seconds: float
    ) -> ValidationReport:
        checks: list[ValidationCheck] = []
        expected = tuple((s.source_stream.kind, s.target_codec) for s in plan.included)
        observed = None
        invariant = "EXTRACTION_PLAN"
        limit = timeout_seconds
        try:
            if not isinstance(plan, ExtractionPlan) or len(plan.included) != 1:
                raise ValueError
            invariant = "EXTRACTION_OUTPUT_FILE"
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError
            observed = inspector.inspect(path, timeout_seconds=timeout_seconds)
            selected = plan.included[0]
            actual_format = "aac" if plan.output.container == "adts" else plan.output.container
            invariant = "EXTRACTION_STRUCTURE"
            if (
                observed.format.name != actual_format
                or len(observed.streams) != 1
                or observed.chapters
            ):
                raise ValueError
            actual = observed.streams[0]
            invariant = "EXTRACTION_CODEC"
            if (actual.kind, actual.codec) != expected[0]:
                raise ValueError
            invariant = "EXTRACTION_TECHNICAL_PROPERTIES"
            for field in ("width", "height", "channels", "sample_rate_hz"):
                value = getattr(selected.source_stream.properties, field)
                if value is not None and value != getattr(actual.properties, field):
                    raise ValueError
            invariant = "EXTRACTION_SOURCE_PACKET_SCAN"
            limit = self._scan_timeout
            before = packet_count(
                selected.reference.source.path,
                selected.reference.index,
                self._ffprobe,
                self._scan_timeout,
                cancellation=self._cancellation,
            )
            checks.append(
                ValidationCheck(invariant, "passed", f"Selected source packet count: {before}.")
            )
            invariant = "EXTRACTION_OUTPUT_PACKET_SCAN"
            after = packet_count(
                path,
                actual.index,
                self._ffprobe,
                self._scan_timeout,
                cancellation=self._cancellation,
            )
            checks.append(
                ValidationCheck(invariant, "passed", f"Staged output packet count: {after}.")
            )
            if actual.kind == "subtitle":
                invariant = "EXTRACTION_SRT_STRUCTURE"
                cues = validate_srt(path, require_suffix=False)
                invariant = "EXTRACTION_SRT_PACKET_COUNT"
                if len(cues) != after:
                    raise ValueError
                invariant = "EXTRACTION_SUBTITLE_SOURCE_SCAN"
                source_cues = subtitle_cues(
                    selected.reference.source.path,
                    selected.reference.index,
                    selected.source_stream.codec or "",
                    self._ffprobe,
                    self._scan_timeout,
                    cancellation=self._cancellation,
                )
                invariant = "EXTRACTION_SUBTITLE_CUE_COUNT"
                if len(source_cues) != len(cues):
                    raise ValueError
                for wanted, cue in zip(source_cues, cues, strict=True):
                    invariant = "EXTRACTION_SUBTITLE_TEXT"
                    text = (
                        plain_text(cue.text) if selected.action == "convert_subtitle" else cue.text
                    )
                    if wanted.text != text:
                        raise ValueError
                    invariant = "EXTRACTION_SUBTITLE_TIMING"
                    # SRT milliseconds quantize the source clock; no cumulative drift allowance.
                    if (
                        abs(wanted.start_ms - cue.start_ms) > 1
                        or abs(wanted.end_ms - cue.end_ms) > 1
                    ):
                        raise ValueError
                checks.append(
                    ValidationCheck(
                        "EXTRACTION_SUBTITLE_CUES",
                        "passed",
                        "Source text and cue timing matched independently; empty clear samples "
                        f"excluded ({before} source packets, {after} output cues).",
                    )
                )
            else:
                invariant = "EXTRACTION_PACKET_COUNT"
                if before != after:
                    raise ValueError
                checks.append(
                    ValidationCheck(
                        invariant,
                        "passed",
                        "Independent selected source/output packet counts matched.",
                    )
                )
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
        except (OSError, ValueError, KeyError, TypeError, InspectionError, ExecutionFailure) as exc:
            if isinstance(exc, ExecutionFailure) and exc.code == "PROCESS_CANCELLED":
                raise
            failure = (
                exc
                if isinstance(exc, PacketScanError)
                else probe_failure(exc)
                if isinstance(exc, InspectionError)
                else None
            )
            if failure is not None:
                checks.append(
                    ValidationCheck(
                        f"{invariant}_{failure.code}",
                        "error",
                        f"{failure.detail} Probe limit: {limit:g} seconds.",
                    )
                )
            checks.append(
                ValidationCheck(invariant, "error", f"Independent validation failed: {invariant}.")
            )
            checks.append(
                ValidationCheck(
                    "EXTRACTION_INVALID",
                    "error",
                    "Extracted format, codec, structure or packet completeness validation failed.",
                )
            )
        return ValidationReport(expected, observed, tuple(checks))

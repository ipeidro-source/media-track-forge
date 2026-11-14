"""Conservative single-stream extraction planning and shared safe execution."""

import os
from dataclasses import replace

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.execution_ports import (
    Inspector,
    OutputValidator,
    ProcessRunner,
    StagingStore,
)
from mediatrack_forge.application.inspection import InspectionError, snapshot_source
from mediatrack_forge.domain.execution import ExecutionFailure, ExecutionRequest
from mediatrack_forge.domain.extraction import EXTRACTION_MATRIX, ExtractionPlan
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import (
    CompatibilityIssue,
    OperationPlan,
    OutputProfile,
    PlannedStream,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.planning_paths import destination_path, equivalent_paths


def extraction_arguments(plan: ExtractionPlan) -> tuple[str, ...]:
    if not plan.intrinsically_valid or plan.pending_warnings or plan.destination_path is None:
        raise ExecutionFailure("INVALID_PLAN")
    selected = plan.included[0]
    args = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-protocol_whitelist",
        "file",
        "-i",
        str(plan.sources[0].source.path),
        "-map",
        f"0:{selected.reference.index}",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-c:0",
        "srt" if selected.action == "convert_subtitle" else "copy",
    ]
    if plan.bitstream_filters:
        args += ["-bsf:0", ",".join(plan.bitstream_filters)]
    args += ["-f", plan.output.container, str(plan.destination_path)]
    return tuple(args)


class ExtractionPlanningService:
    def plan(
        self,
        source: MediaAsset,
        reference: StreamReference,
        output_path: str,
        *,
        acknowledged_warnings: frozenset[str] = frozenset(),
        acknowledged_revision: str | None = None,
    ) -> ExtractionPlan:
        issues: list[CompatibilityIssue] = []

        def error(code: str, message: str) -> None:
            issues.append(CompatibilityIssue(code, "error", message))

        try:
            if snapshot_source(source.source.path) != source.source:
                error("SOURCE_CHANGED", "Inspect the changed source again.")
        except InspectionError:
            error("INVALID_SOURCE", "Select a readable local source.")
        destination = None
        try:
            destination = destination_path(output_path)
            if equivalent_paths(destination, source.source.path):
                error(
                    "SOURCE_DESTINATION_CONFLICT", "Choose a destination different from the source."
                )
            if os.path.lexists(destination):
                error("DESTINATION_EXISTS", "Choose a free destination.")
        except (ValueError, OSError, RuntimeError):
            error("INVALID_DESTINATION", "Choose a valid local destination.")
        stream = next(
            (s for s in source.streams if StreamReference(source.source, s.index) == reference),
            None,
        )
        extension = destination.suffix[1:].lower() if destination else ""
        family = "mp4" if "mp4" in (source.format.name or "").split(",") else source.format.name
        if family == "matroska,webm":
            family = "matroska"
        combination = next(
            (
                row
                for row in EXTRACTION_MATRIX
                if stream is not None and row[:3] == (stream.codec, family, extension)
            ),
            None,
        )
        if stream is None:
            error("UNKNOWN_STREAM_REFERENCE", "Select an original inspected stream index.")
        if combination is None:
            error(
                "UNSUPPORTED_EXTRACTION", "Choose a documented codec/source/extension combination."
            )
        expected_kind = {
            "h264": "video",
            "hevc": "video",
            "aac": "audio",
            "mp3": "audio",
            "subrip": "subtitle",
            "mov_text": "subtitle",
        }
        if stream is not None and stream.kind != expected_kind.get(stream.codec or ""):
            error("UNSUPPORTED_EXTRACTION", "The inspected stream kind does not match its codec.")
        if dict(source.format.tags).get("major_brand") == "qt  ":
            error("UNSUPPORTED_EXTRACTION", "MOV extraction is not in the validated MP4 matrix.")
        if stream is not None and stream.codec == "aac" and stream.properties.profile != "LC":
            error("UNSUPPORTED_AAC_PROFILE", "Only inspected AAC LC to ADTS is validated.")
        included: tuple[PlannedStream, ...] = ()
        if stream is not None and combination is not None:
            conversion = stream.codec == "mov_text"
            included = (
                PlannedStream(
                    reference,
                    stream,
                    0,
                    0,
                    "convert_subtitle" if conversion else "copy",
                    "subrip" if conversion else stream.codec,
                    (),
                    (),
                ),
            )
            if conversion:
                issues.append(
                    CompatibilityIssue(
                        "SUBTITLE_FORMATTING_MAY_CHANGE",
                        "warning",
                        "Converting mov_text to SRT may lose subtitle styling.",
                    )
                )
        issues.append(
            CompatibilityIssue(
                "EXTRACTION_METADATA_EXCLUDED",
                "warning",
                "Elementary extraction excludes container metadata, chapters and dispositions.",
            )
        )
        plan = ExtractionPlan(
            sources=(source,),
            output=OutputProfile(combination[3] if combination else "", output_path),
            destination_path=destination,
            selections=(TrackSelection(reference),),
            external_tracks=(),
            included=included,
            excluded=(),
            preserve_chapters=False,
            chapter_input_index=None,
            preservation=(),
            issues=tuple(issues),
            acknowledged_warnings=acknowledged_warnings,
            acknowledged_revision=acknowledged_revision,
            bitstream_filters=(combination[4],) if combination and combination[4] else (),
        )
        if plan.intrinsically_valid and not plan.pending_warnings:
            plan = replace(plan, arguments=extraction_arguments(plan))
        return plan


class ExtractionExecutionService(RemuxExecutionService):
    def __init__(
        self,
        *,
        inspector: Inspector | None = None,
        runner: ProcessRunner | None = None,
        staging: StagingStore | None = None,
        ffprobe: str | None = None,
    ) -> None:
        from mediatrack_forge.infrastructure.extraction_validation import ExtractionValidator

        super().__init__(
            inspector=inspector,
            runner=runner,
            staging=staging,
            validator=ExtractionValidator(ffprobe),
        )
        self._validation_ffprobe = ffprobe

    def _validator_for(self, request: ExecutionRequest) -> OutputValidator:
        from mediatrack_forge.infrastructure.extraction_validation import ExtractionValidator

        return ExtractionValidator(request.configuration.ffprobe or self._validation_ffprobe)

    @staticmethod
    def _arguments(plan: OperationPlan) -> tuple[str, ...]:
        if not isinstance(plan, ExtractionPlan):
            raise ExecutionFailure("INVALID_PLAN")
        return extraction_arguments(plan)

    @staticmethod
    def _regenerate(request: ExecutionRequest, inspector: Inspector) -> OperationPlan:
        supplied = request.plan
        if (
            request.confirmed_revision is None
            or request.confirmed_revision != request.reviewed_revision
        ):
            raise ExecutionFailure("UNCONFIRMED_PLAN")
        if (
            not isinstance(supplied, ExtractionPlan)
            or supplied.revision != request.reviewed_revision
        ):
            raise ExecutionFailure("INVALID_PLAN")
        if len(supplied.sources) != 1 or len(supplied.selections) != 1:
            raise ExecutionFailure("INVALID_PLAN")
        source = inspector.inspect(
            supplied.sources[0].source.path,
            timeout_seconds=request.configuration.probe_timeout_seconds,
        )
        if source != supplied.sources[0]:
            raise ExecutionFailure("CHANGED_INPUT")
        plan = ExtractionPlanningService().plan(
            source,
            supplied.selections[0].reference,
            supplied.output.path,
            acknowledged_warnings=supplied.acknowledged_warnings,
            acknowledged_revision=supplied.acknowledged_revision,
        )
        if any(i.code == "DESTINATION_EXISTS" for i in plan.issues):
            raise ExecutionFailure("DESTINATION_COLLISION")
        if plan.revision != request.reviewed_revision or not plan.execution_allowed:
            raise ExecutionFailure("INVALID_PLAN")
        return plan

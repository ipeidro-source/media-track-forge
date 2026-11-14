"""Confirmed remux orchestration: regenerate, stage, run, validate, recheck, publish."""

import math
import os
from pathlib import Path

from mediatrack_forge.application.execution_ports import (
    Inspector,
    OutputValidator,
    OwnedStage,
    ProcessRunner,
    StagingStore,
)
from mediatrack_forge.application.inspection import (
    ExecutableError,
    InspectionError,
    InspectionService,
)
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import (
    ExecutionDiagnostic,
    ExecutionFailure,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    ValidationReport,
)
from mediatrack_forge.domain.planning import OperationPlan
from mediatrack_forge.infrastructure.ffmpeg_arguments import build_arguments
from mediatrack_forge.infrastructure.ffmpeg_process import FFmpegProcessRunner, discover_ffmpeg
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.output_validation import FFprobeOutputValidator
from mediatrack_forge.infrastructure.staging import PrivateStagingStore

MESSAGES = {
    "INVALID_PLAN": "The plan is stale or invalid; regenerate, review and confirm it again.",
    "UNCONFIRMED_PLAN": "Explicit confirmation must match the exact reviewed plan revision.",
    "CHANGED_INPUT": "An input changed or is unavailable; inspect and review it again.",
    "INVALID_TIMEOUT": "Execution and probe timeouts must be finite positive seconds.",
    "EXTERNAL_IMPORT_DEFERRED": "External track execution/import is not available yet.",
    "INVALID_DESTINATION": "Choose a free local destination in an existing directory.",
    "MISSING_EXECUTABLE": "Install trusted FFmpeg/ffprobe executables or select their paths.",
    "PROCESS_LAUNCH_FAILED": "FFmpeg could not be launched; check the executable configuration.",
    "PROCESS_CONTAINMENT_FAILED": "Process containment failed; safe cleanup is unverified.",
    "PROCESS_TIMEOUT": "FFmpeg exceeded its timeout and the managed process was stopped.",
    "PROCESS_TERMINATION_FAILED": "Termination is unverified; output was not published.",
    "PROCESS_OUTPUT_LIMIT": "FFmpeg diagnostics exceeded the capture safety limit.",
    "FFMPEG_FAILED": "FFmpeg processing failed; no output was published.",
    "PROCESS_FAILED": "Managed processing failed; no output was published.",
    "OUTPUT_VALIDATION_FAILED": "The staged output did not pass independent validation.",
    "DESTINATION_COLLISION": "The destination already exists; it was not overwritten.",
    "PUBLICATION_UNSUPPORTED": "This filesystem does not support exclusive hard-link publication.",
    "PUBLICATION_FAILED": "Exclusive publication failed; no unsafe fallback was attempted.",
    "STAGING_FAILED": "Private staging could not be allocated in the destination directory.",
    "STAGING_OWNERSHIP_LOST": "Staging ownership changed; foreign artifacts will not be deleted.",
    "TEMPORARY_CLEANUP_FAILED": "Temporary cleanup is incomplete; inspect staging privately.",
    "CLEANUP_UNSAFE": "Process termination is unverified; active staging was retained for safety.",
    "EXECUTION_FAILED": "Execution failed unexpectedly; no unvalidated output was published.",
}


class RemuxExecutionService:
    def __init__(
        self,
        *,
        inspector: Inspector | None = None,
        runner: ProcessRunner | None = None,
        staging: StagingStore | None = None,
        validator: OutputValidator | None = None,
    ) -> None:
        self._inspector = inspector
        self._runner = runner if runner is not None else FFmpegProcessRunner()
        self._staging = staging if staging is not None else PrivateStagingStore()
        self._validator = validator if validator is not None else FFprobeOutputValidator()

    @staticmethod
    def _regenerate(request: ExecutionRequest, inspector: Inspector) -> OperationPlan:
        supplied = request.plan
        if (
            request.confirmed_revision is None
            or request.confirmed_revision != request.reviewed_revision
        ):
            raise ExecutionFailure("UNCONFIRMED_PLAN")
        if supplied.revision != request.reviewed_revision:
            raise ExecutionFailure("INVALID_PLAN")
        if supplied.external_tracks:
            raise ExecutionFailure("EXTERNAL_IMPORT_DEFERRED")
        try:
            fresh = tuple(
                inspector.inspect(
                    asset.source.path, timeout_seconds=request.configuration.probe_timeout_seconds
                )
                for asset in supplied.sources
            )
        except ExecutableError as exc:
            raise ExecutionFailure("MISSING_EXECUTABLE") from exc
        except InspectionError as exc:
            raise ExecutionFailure("CHANGED_INPUT") from exc
        if fresh != supplied.sources:
            raise ExecutionFailure("CHANGED_INPUT")
        regenerated = OperationPlanningService().plan(
            fresh,
            supplied.selections,
            supplied.output,
            external_tracks=supplied.external_tracks,
            preserve_chapters=supplied.preserve_chapters,
            acknowledged_warnings=supplied.acknowledged_warnings,
            acknowledged_revision=supplied.acknowledged_revision,
        )
        if (
            regenerated.revision != request.reviewed_revision
            or not regenerated.intrinsically_valid
            or regenerated.pending_warnings
        ):
            if any(issue.code == "DESTINATION_EXISTS" for issue in regenerated.issues):
                raise ExecutionFailure("DESTINATION_COLLISION")
            if any(
                issue.code in ("SOURCE_CHANGED", "INVALID_SOURCE") for issue in regenerated.issues
            ):
                raise ExecutionFailure("CHANGED_INPUT")
            raise ExecutionFailure("INVALID_PLAN")
        return regenerated

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        history: list[ExecutionState] = ["planned"]
        diagnostics: list[ExecutionDiagnostic] = []
        stage: OwnedStage | None = None
        validation: ValidationReport | None = None
        destination: Path | None = None
        published = False
        safe_cleanup = True
        cleanup_complete = True
        try:
            config = request.configuration
            if any(
                not math.isfinite(value) or value <= 0
                for value in (config.timeout_seconds, config.probe_timeout_seconds)
            ):
                raise ExecutionFailure("INVALID_TIMEOUT")
            inspector = (
                self._inspector
                if self._inspector is not None
                else InspectionService(FFprobeAdapter(config.ffprobe))
            )
            plan = self._regenerate(request, inspector)
            destination = plan.destination_path
            if destination is None or not destination.parent.is_dir():
                raise ExecutionFailure("INVALID_DESTINATION")
            executable = discover_ffmpeg(config.ffmpeg)
            stage = self._staging.allocate(destination)
            stage.verify()
            # Regenerate fresh arguments; never consume supplied plan.arguments.
            arguments = list(build_arguments(plan))
            if arguments[-1] != str(destination) or arguments[4] != "-n":
                raise ExecutionFailure("INVALID_PLAN")
            arguments[0] = executable
            arguments[-1] = str(stage.path)
            # Only our exclusively reserved private staging file may be truncated.
            arguments[4] = "-y"
            history.append("running")
            safe_cleanup = False  # An adapter must prove the process can no longer write.
            outcome = self._runner.run(tuple(arguments), config.timeout_seconds)
            safe_cleanup = outcome.safe_to_cleanup
            if not safe_cleanup:
                raise ExecutionFailure("PROCESS_TERMINATION_FAILED")
            if outcome.error_code is not None or outcome.return_code != 0:
                raise ExecutionFailure(outcome.error_code or "FFMPEG_FAILED")
            stage.verify()
            history.append("validating")
            validation = self._validator.validate(
                plan, stage.path, inspector, config.probe_timeout_seconds
            )
            if not validation.passed:
                raise ExecutionFailure("OUTPUT_VALIDATION_FAILED")
            stage.verify()
            stage.flush()
            # Reinspect/rebuild again after output validation, before the final link.
            self._regenerate(request, inspector)
            if os.path.lexists(destination):
                raise ExecutionFailure("DESTINATION_COLLISION")
            history.append("publishing")
            stage.publish(destination)
            published = True
        except ExecutionFailure as exc:
            diagnostics.append(
                ExecutionDiagnostic(exc.code, MESSAGES.get(exc.code, MESSAGES["EXECUTION_FAILED"]))
            )
        except Exception:
            diagnostics.append(
                ExecutionDiagnostic("EXECUTION_FAILED", MESSAGES["EXECUTION_FAILED"])
            )
        finally:
            if stage is not None:
                if safe_cleanup:
                    try:
                        stage.cleanup()
                    except Exception:
                        cleanup_complete = False
                        diagnostics.append(
                            ExecutionDiagnostic(
                                "TEMPORARY_CLEANUP_FAILED", MESSAGES["TEMPORARY_CLEANUP_FAILED"]
                            )
                        )
                else:
                    cleanup_complete = False
                    try:
                        stage.release()
                    except Exception:
                        pass  # CLEANUP_UNSAFE already reports incomplete resource/artifact cleanup.
                    diagnostics.append(
                        ExecutionDiagnostic("CLEANUP_UNSAFE", MESSAGES["CLEANUP_UNSAFE"])
                    )
        if published and not diagnostics:
            history.append("completed")
        elif any(item.code == "PROCESS_TIMEOUT" for item in diagnostics):
            history.append("timed_out")
        else:
            history.append("failed")
        return ExecutionResult(
            history[-1],
            tuple(history),
            tuple(diagnostics),
            validation,
            destination if published else None,
            published,
            cleanup_complete,
        )

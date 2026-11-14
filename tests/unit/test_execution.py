"""Deterministic failure/authorization tests with injected inspection and process ports."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_planning import acknowledged, asset, select, stream

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import (
    ExecutionFailure,
    ExecutionRequest,
    ProcessConfiguration,
    ProcessOutcome,
    ValidationReport,
)
from mediatrack_forge.domain.planning import MetadataIntent, OutputProfile
from mediatrack_forge.infrastructure.output_validation import FFprobeOutputValidator
from mediatrack_forge.infrastructure.staging import PrivateStagingStore


@pytest.fixture
def execution_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ExecutionRequest:
    monkeypatch.setattr(
        "mediatrack_forge.application.execution.discover_ffmpeg", lambda _: "ffmpeg"
    )
    source = asset(tmp_path, [stream(0, "video", "h264"), stream(2, "audio", "aac")])
    plan = acknowledged(
        OperationPlanningService().plan(
            (source,),
            (select(source, 0), select(source, 2)),
            OutputProfile("mkv", str(tmp_path / "final.mkv")),
        )
    )
    return ExecutionRequest(plan, plan.revision, plan.revision)


def service(
    execution_request: ExecutionRequest,
    *,
    runner: Mock | None = None,
    staging: Mock | None = None,
    validator: Mock | None = None,
) -> RemuxExecutionService:
    inspector = Mock()
    inspector.inspect.return_value = execution_request.plan.sources[0]
    if runner is None:
        runner = Mock()

        def write(arguments: tuple[str, ...], timeout: float) -> ProcessOutcome:
            target = Path(arguments[-1])
            assert execution_request.plan.destination_path is not None
            assert target != execution_request.plan.destination_path
            assert target.parent.name.startswith(".mediatrack-")
            assert not execution_request.plan.destination_path.exists()
            Path(arguments[-1]).write_bytes(b"synthetic validated output")
            return ProcessOutcome(0)

        runner.run.side_effect = write
    if validator is None:
        validator = Mock()

        def validate(
            plan: object, path: Path, inspector: object, timeout: float
        ) -> ValidationReport:
            assert path.stat().st_size > 0
            assert execution_request.plan.destination_path is not None
            assert not execution_request.plan.destination_path.exists()
            return ValidationReport((), None, ())

        validator.validate.side_effect = validate
    return RemuxExecutionService(
        inspector=inspector, runner=runner, staging=staging, validator=validator
    )


def test_success_uses_fresh_arguments_and_truthful_state_history(
    execution_request: ExecutionRequest,
) -> None:
    forged = replace(execution_request.plan, arguments=("malicious", "-y", "source"))
    result = service(execution_request).execute(replace(execution_request, plan=forged))
    assert result.state == "completed" and result.published and result.cleanup_complete
    assert result.history == ("planned", "running", "validating", "publishing", "completed")
    assert result.validation is not None and result.validation.passed
    assert (
        result.destination is not None
        and result.destination == execution_request.plan.destination_path
    )
    assert execution_request.plan.sources[0].source.path.read_bytes() == b"synthetic unit source"
    assert not list(result.destination.parent.glob(".mediatrack-*"))


@pytest.mark.parametrize(
    "change", ["confirmation", "reviewed", "selection", "order", "metadata", "output"]
)
def test_unconfirmed_or_changed_intent_cannot_execute(
    execution_request: ExecutionRequest, change: str
) -> None:
    modified = execution_request
    if change == "confirmation":
        modified = replace(execution_request, confirmed_revision=None)
    elif change == "reviewed":
        modified = replace(execution_request, reviewed_revision="wrong")
    elif change == "selection":
        modified = replace(
            execution_request,
            plan=replace(execution_request.plan, selections=execution_request.plan.selections[:1]),
        )
    elif change == "order":
        modified = replace(
            execution_request,
            plan=replace(
                execution_request.plan,
                selections=tuple(reversed(execution_request.plan.selections)),
            ),
        )
    elif change == "metadata":
        selections = (
            replace(execution_request.plan.selections[0], metadata=MetadataIntent(title="changed")),
        )
        modified = replace(
            execution_request, plan=replace(execution_request.plan, selections=selections)
        )
    else:
        modified = replace(
            execution_request,
            plan=replace(execution_request.plan, output=OutputProfile("mp4", "other.mp4")),
        )
    runner = Mock()
    result = service(execution_request, runner=runner).execute(modified)
    assert result.state == "failed" and not result.published
    runner.run.assert_not_called()
    assert execution_request.plan.destination_path is not None
    assert not execution_request.plan.destination_path.exists()


def test_modified_derived_plan_cannot_be_confirmed_through_regeneration(
    execution_request: ExecutionRequest,
) -> None:
    modified = replace(
        execution_request.plan,
        included=(replace(execution_request.plan.included[0], target_codec="hevc"),),
    )
    runner = Mock()
    result = service(execution_request, runner=runner).execute(
        ExecutionRequest(modified, modified.revision, modified.revision)
    )
    assert result.state == "failed"
    runner.run.assert_not_called()


def test_reinspection_rejects_changed_content_even_with_same_size_mtime(
    execution_request: ExecutionRequest,
) -> None:
    inspector = Mock()
    source = execution_request.plan.sources[0]
    inspector.inspect.return_value = replace(
        source, streams=(replace(source.streams[0], codec="unknown"),)
    )
    runner = Mock()
    result = RemuxExecutionService(inspector=inspector, runner=runner).execute(execution_request)
    assert result.diagnostics[0].code == "CHANGED_INPUT"
    runner.run.assert_not_called()


@pytest.mark.parametrize(
    "code,safe",
    [
        ("FFMPEG_FAILED", True),
        ("PROCESS_LAUNCH_FAILED", True),
        ("PROCESS_TIMEOUT", True),
        ("PROCESS_TERMINATION_FAILED", False),
        ("PROCESS_OUTPUT_LIMIT", True),
    ],
)
def test_process_failures_never_publish_and_clean_only_when_safe(
    execution_request: ExecutionRequest,
    code: str,
    safe: bool,
) -> None:
    runner = Mock()
    runner.run.return_value = ProcessOutcome(1, code, safe)
    result = service(execution_request, runner=runner).execute(execution_request)
    assert not result.published and result.diagnostics[0].code == code
    assert result.state == ("timed_out" if code == "PROCESS_TIMEOUT" else "failed")
    parent = execution_request.plan.sources[0].source.path.parent
    assert bool(list(parent.glob(".mediatrack-*"))) is not safe
    if not safe:
        assert not result.cleanup_complete and result.diagnostics[-1].code == "CLEANUP_UNSAFE"
        # The fake never launched a process. Test-only cleanup of the retained allocation.
        for directory in parent.glob(".mediatrack-*"):
            for path in directory.iterdir():
                path.unlink()
            directory.rmdir()


def test_post_execution_input_change_blocks_publication(
    execution_request: ExecutionRequest,
) -> None:
    runner = Mock()

    def change(arguments: tuple[str, ...], timeout: float) -> ProcessOutcome:
        execution_request.plan.sources[0].source.path.write_bytes(
            b"modified source by external actor"
        )
        Path(arguments[-1]).write_bytes(b"output")
        return ProcessOutcome(0)

    runner.run.side_effect = change
    result = service(execution_request, runner=runner).execute(execution_request)
    assert result.state == "failed" and not result.published
    assert not list(execution_request.plan.sources[0].source.path.parent.glob(".mediatrack-*"))


def test_validation_exception_and_missing_executable_cleanup(
    execution_request: ExecutionRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    validator = Mock()
    validator.validate.side_effect = RuntimeError("private diagnostic")
    result = service(execution_request, validator=validator).execute(execution_request)
    assert result.diagnostics[0].code == "EXECUTION_FAILED" and result.cleanup_complete
    assert "private diagnostic" not in result.diagnostics[0].message
    monkeypatch.setattr(
        "mediatrack_forge.application.execution.discover_ffmpeg",
        Mock(side_effect=ExecutionFailure("MISSING_EXECUTABLE")),
    )
    result = service(execution_request).execute(execution_request)
    assert result.diagnostics[0].code == "MISSING_EXECUTABLE"


def test_publication_cleanup_failure_is_explicit(execution_request: ExecutionRequest) -> None:
    real_store = PrivateStagingStore()
    stage = (
        real_store.allocate(execution_request.plan.destination_path)
        if execution_request.plan.destination_path
        else None
    )
    assert stage is not None
    store = Mock()
    proxy = Mock(wraps=stage)
    proxy.path = stage.path
    proxy.cleanup.side_effect = PermissionError()
    store.allocate.return_value = proxy
    result = service(execution_request, staging=store).execute(execution_request)
    assert result.published and result.state == "failed" and not result.cleanup_complete
    assert result.diagnostics[-1].code == "TEMPORARY_CLEANUP_FAILED"
    stage.cleanup()


@pytest.mark.parametrize("seconds", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_timeout_never_stages_or_runs(
    execution_request: ExecutionRequest, seconds: float
) -> None:
    runner = Mock()
    store = Mock()
    configured = replace(
        execution_request, configuration=ProcessConfiguration(timeout_seconds=seconds)
    )
    result = service(execution_request, runner=runner, staging=store).execute(configured)
    assert result.diagnostics[0].code == "INVALID_TIMEOUT"
    runner.run.assert_not_called()
    store.allocate.assert_not_called()


def test_forged_warning_set_cannot_be_confirmed(execution_request: ExecutionRequest) -> None:
    from mediatrack_forge.domain.planning import CompatibilityIssue

    modified = replace(
        execution_request.plan,
        issues=(CompatibilityIssue("FORGED", "warning", "Different diagnostics"),),
    )
    modified = replace(
        modified,
        acknowledged_revision=modified.revision,
        acknowledged_warnings=frozenset({"FORGED"}),
    )
    runner = Mock()
    result = service(execution_request, runner=runner).execute(
        ExecutionRequest(modified, modified.revision, modified.revision)
    )
    assert result.diagnostics[0].code == "INVALID_PLAN"
    runner.run.assert_not_called()


def test_external_subtitle_cannot_bypass_scope_by_omitting_external_record(
    execution_request: ExecutionRequest,
    tmp_path: Path,
) -> None:
    source = execution_request.plan.sources[0]
    subtitle = asset(tmp_path, [stream(0, "subtitle", "subrip")], name="external.srt")
    plan = acknowledged(
        OperationPlanningService().plan(
            (source, subtitle),
            (select(source, 0), select(source, 2), select(subtitle, 0)),
            execution_request.plan.output,
        )
    )
    assert plan.intrinsically_valid and not plan.external_tracks
    inspector = Mock()
    inspector.inspect.side_effect = lambda path, **kwargs: (
        source if path == source.source.path else subtitle
    )
    runner = Mock()
    result = RemuxExecutionService(inspector=inspector, runner=runner).execute(
        ExecutionRequest(plan, plan.revision, plan.revision)
    )
    assert result.diagnostics[0].code == "EXTERNAL_IMPORT_DEFERRED"
    runner.run.assert_not_called()


@pytest.mark.parametrize("after", [1.0, None])
def test_required_duration_failure_never_attempts_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after: float | None,
) -> None:
    monkeypatch.setattr(
        "mediatrack_forge.application.execution.discover_ffmpeg", lambda _: "ffmpeg"
    )
    source = asset(tmp_path, [stream(0, "video", "h264") | {"duration": "10"}])
    assert source.streams[0].properties.time_base is None
    plan = acknowledged(
        OperationPlanningService().plan(
            (source,), (select(source, 0),), OutputProfile("mkv", str(tmp_path / "final.mkv"))
        )
    )
    observed = replace(
        source,
        format=replace(source.format, name="matroska", duration_seconds=after),
        streams=(replace(source.streams[0], duration_seconds=after),),
    )
    inspector = Mock()
    inspector.inspect.side_effect = lambda path, **kwargs: (
        source if path == source.source.path else observed
    )
    stage = PrivateStagingStore().allocate(tmp_path / "final.mkv")
    publish = Mock()
    monkeypatch.setattr(stage, "publish", publish)
    store = Mock()
    store.allocate.return_value = stage
    runner = Mock()

    def write(arguments: tuple[str, ...], timeout: float) -> ProcessOutcome:
        Path(arguments[-1]).write_bytes(b"staged output")
        return ProcessOutcome(0)

    runner.run.side_effect = write
    result = RemuxExecutionService(
        inspector=inspector, runner=runner, staging=store, validator=FFprobeOutputValidator()
    ).execute(ExecutionRequest(plan, plan.revision, plan.revision))
    assert result.state == "failed" and not result.published and result.cleanup_complete
    assert result.diagnostics[0].code == "OUTPUT_VALIDATION_FAILED"
    assert result.validation is not None and not result.validation.passed
    code = "DURATION_UNVERIFIABLE" if after is None else "DURATION_TOLERANCE_UNAVAILABLE"
    assert any(check.code == code and check.status == "error" for check in result.validation.checks)
    publish.assert_not_called()
    assert not (tmp_path / "final.mkv").exists() and not stage.directory.exists()
    assert source.source.path.read_bytes() == b"synthetic unit source"

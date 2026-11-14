"""Offline SRT, extraction, cancellation/commit races and bounded progress regressions."""

import json
import sys
import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_execution import execution_request as execution_request
from test_execution import service
from test_planning import asset, stream

from mediatrack_forge.application.control import CancellationToken, ExecutionControl, ProgressEvent
from mediatrack_forge.application.external_subtitles import ExternalSubtitleService
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import snapshot_source
from mediatrack_forge.domain.execution import ExecutionFailure, ExecutionRequest, ProcessOutcome
from mediatrack_forge.domain.extraction import EXTRACTION_MATRIX
from mediatrack_forge.domain.planning import StreamReference
from mediatrack_forge.infrastructure.ffmpeg_process import FFmpegProcessRunner
from mediatrack_forge.infrastructure.ffmpeg_progress import ProgressParser
from mediatrack_forge.infrastructure.srt import validate_srt
from mediatrack_forge.ui.extraction_json import extraction_document, serialize_extraction

VALID = "1\n00:00:00,000 --> 00:00:00,300\nUnicode 日本語\n"


@pytest.mark.parametrize(
    "text",
    [
        VALID,
        "\ufeff" + VALID,
        VALID.replace("\n", "\r\n"),
        VALID.replace("1\n", ""),
        VALID.replace(" --> ", "-->"),
        VALID + "\n42\n00:00:00,200 --> 00:00:00,400\nOverlap is valid\n",
    ],
)
def test_srt_harmless_variations(tmp_path: Path, text: str) -> None:
    path = tmp_path / "sub.srt"
    path.write_bytes(text.encode("utf-8"))
    assert validate_srt(path)[0].text == "Unicode 日本語"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xff",
        b"\x00",
        b"not srt",
        VALID.replace("000 -->", "300 -->").encode(),
        VALID.replace(",300", ",000").encode(),
        VALID.replace(",300", ",3").encode(),
        VALID.replace("00:00:00,300", "00:70:00,300").encode(),
        VALID.replace("Unicode 日本語", "").encode(),
        VALID.replace("00:00:00,300", "1000:00:00,300").encode(),
    ],
)
def test_srt_rejects_malformed_timing_encoding_and_content(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "sub.srt"
    path.write_bytes(data)
    with pytest.raises(ExecutionFailure, match="INVALID_EXTERNAL_SRT"):
        validate_srt(path)


def test_srt_resource_limit_and_source_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sub.srt"
    path.write_text(VALID, encoding="utf-8")
    monkeypatch.setattr("mediatrack_forge.infrastructure.srt.MAX_SRT_BYTES", 2)
    with pytest.raises(ExecutionFailure):
        validate_srt(path)
    monkeypatch.setattr("mediatrack_forge.infrastructure.srt.MAX_SRT_BYTES", 1024)
    before = snapshot_source(path)
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.srt.snapshot_source",
        Mock(side_effect=[before, replace(before, size_bytes=1)]),
    )
    with pytest.raises(ExecutionFailure):
        validate_srt(path)


def test_srt_multiple_blank_separators_and_markup(tmp_path: Path) -> None:
    path = tmp_path / "sub.srt"
    path.write_text(
        VALID + "\n \n\n2\n00:00:00,300 --> 00:00:00,600\n<i>Text</i>\n", encoding="utf-8"
    )
    cues = validate_srt(path)
    assert len(cues) == 2 and cues[1].text == "<i>Text</i>"


@pytest.mark.parametrize("kind,codec,index", [("subtitle", "subrip", 7), ("audio", "aac", 0)])
def test_import_requires_genuine_inspected_stream(
    tmp_path: Path, kind: str, codec: str, index: int
) -> None:
    source = asset(tmp_path, [stream(index, kind, codec)], name="sub.srt")
    source.source.path.write_text(VALID, encoding="utf-8")
    source = replace(
        source,
        source=snapshot_source(source.source.path),
        format=replace(source.format, name="srt"),
    )
    inspector = Mock()
    inspector.inspect.return_value = source
    if kind == "audio":
        with pytest.raises(ExecutionFailure):
            ExternalSubtitleService(inspector).import_srt(source.source.path)
    else:
        actual, record = ExternalSubtitleService(inspector).import_srt(source.source.path)
        assert actual == source and record.stream_index == 7 and record.validated


@pytest.mark.parametrize("row", EXTRACTION_MATRIX)
def test_extraction_exact_policy_and_maps(
    tmp_path: Path, row: tuple[str, str, str, str, str | None]
) -> None:
    codec, family, extension, muxer, filter_name = row
    properties = {"profile": "LC"} if codec == "aac" else {}
    kind = (
        "video" if codec in ("h264", "hevc") else "audio" if codec in ("aac", "mp3") else "subtitle"
    )
    source = asset(tmp_path, [stream(7, kind, codec) | properties])
    source = replace(source, format=replace(source.format, name=family))
    reference = StreamReference(source.source, 7)
    planner = ExtractionPlanningService()
    path = str(tmp_path / f"out.{extension}")
    plan = planner.plan(source, reference, path)
    assert plan.intrinsically_valid and plan.arguments is None
    plan = planner.plan(
        source,
        reference,
        path,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    assert plan.arguments is not None and plan.execution_allowed
    assert plan.arguments[plan.arguments.index("-map") + 1] == "0:7"
    assert plan.output.container == muxer
    assert plan.bitstream_filters == ((filter_name,) if filter_name else ())
    assert not {"libx264", "libx265", "aac", "libmp3lame"} & set(plan.arguments)
    changed = planner.plan(
        source,
        reference,
        str(tmp_path / f"changed.{extension}"),
        acknowledged_revision=plan.revision,
        acknowledged_warnings=plan.acknowledged_warnings,
    )
    assert changed.pending_warnings and changed.arguments is None
    assert json.loads(serialize_extraction(plan)) == extraction_document(plan)
    assert "plan_version" not in extraction_document(plan)


@pytest.mark.parametrize(
    "codec,format_name,extension",
    [
        ("ac3", "matroska", "ac3"),
        ("h264", "matroska", "h264"),
        ("aac", "mp4", "mp3"),
        ("ass", "matroska", "srt"),
        ("hevc", "avi", "h265"),
        ("unknown", "mp4", "bin"),
    ],
)
def test_unsupported_extraction_has_no_arguments(
    tmp_path: Path, codec: str, format_name: str, extension: str
) -> None:
    source = asset(tmp_path, [stream(0, "audio", codec)])
    source = replace(source, format=replace(source.format, name=format_name))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 0), str(tmp_path / f"out.{extension}")
    )
    assert not plan.intrinsically_valid and plan.arguments is None


@pytest.mark.parametrize("phase", ["preparing", "running", "validating", "publishing"])
def test_cancellation_at_safe_phase_boundaries(
    execution_request: ExecutionRequest, phase: str
) -> None:
    control = ExecutionControl()

    def listener(event: ProgressEvent) -> None:
        if event.phase == phase:
            control.cancellation.cancel()

    control.listener = listener
    result = service(execution_request).execute(execution_request, control=control)
    assert result.state == "cancelled" and not result.published and result.cleanup_complete
    assert result.destination is None


def test_cancel_during_validation_and_callback_failure(execution_request: ExecutionRequest) -> None:
    control = ExecutionControl()
    validator = Mock()

    def validate(*args: object) -> object:
        control.cancellation.cancel()
        raise RuntimeError("failure after cancellation")

    validator.validate.side_effect = validate
    result = service(execution_request, validator=validator).execute(
        execution_request, control=control
    )
    assert not result.published and result.state == "failed"  # Failed validation is not hidden.
    calls = []

    def bad_listener(event: ProgressEvent) -> None:
        calls.append(event)
        raise ValueError("observer cannot bypass validation")

    result = service(execution_request).execute(
        execution_request, control=ExecutionControl(listener=bad_listener)
    )
    assert result.published and result.state == "completed" and len(calls) == 1
    assert result.diagnostics[-1].code == "PROGRESS_LISTENER_FAILED"


@pytest.mark.parametrize("commit_first", [True, False])
def test_concurrent_publication_cancellation_linearization(commit_first: bool) -> None:
    token = CancellationToken()
    entered = threading.Event()
    release = threading.Event()
    requested = threading.Event()
    published = []
    outcomes = []

    def publish() -> None:
        def action() -> None:
            entered.set()
            assert release.wait(3)
            published.append(True)

        try:
            token.publish(action)
        except ExecutionFailure:
            pass

    def cancel() -> None:
        requested.set()
        outcomes.append(token.cancel())

    publisher = threading.Thread(target=publish)
    canceller = threading.Thread(target=cancel)
    if commit_first:
        publisher.start()
        assert entered.wait(3)
        canceller.start()
        assert requested.wait(3)
        release.set()
    else:
        canceller.start()
        canceller.join(3)
        release.set()
        publisher.start()
    publisher.join(3)
    canceller.join(3)
    assert not publisher.is_alive() and not canceller.is_alive()
    assert bool(published) == commit_first and outcomes == [not commit_first]


def test_progress_parser_partial_invalid_and_bounded() -> None:
    parser = ProgressParser()
    for chunk in (
        b"out_time_",
        b"us=2000000\n",
        b"out_time_us=1000000\n",
        b"out_time_us=nan\n",
        b"out_time_us=-3\n",
        b"out_time_ms=N/A\n",
        b"unknown=anything\n",
    ):
        parser.feed(chunk)
    assert parser.seconds == 2
    with pytest.raises(ValueError):
        parser.feed(b"x" * 4097)


@pytest.mark.parametrize("duration", [None, 10.0])
def test_progress_monotonic_indeterminate_and_no_early_completion(duration: float | None) -> None:
    events: list[ProgressEvent] = []
    control = ExecutionControl(listener=events.append)
    control.expected_seconds = duration
    for seconds in (None, 0, 2, 1, float("inf"), 200):
        control.emit("running", seconds)
    values = [event.percent for event in events if event.percent is not None]
    assert values == sorted(values) and all(value < 100 for value in values)
    assert all(e.determinate == (duration is not None) for e in events)
    control.emit("completed")
    assert events[-1].percent == 100 and events[-1].terminal


def test_cancel_real_python_process_and_ordinary_child(tmp_path: Path) -> None:
    heartbeat = tmp_path / "child.txt"
    child = (
        "import pathlib,time; p=pathlib.Path(" + repr(str(heartbeat)) + "); "
        "[(p.write_text(str(i)),time.sleep(.02)) for i in range(1000)]"
    )
    parent = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
        + repr(child)
        + "]); time.sleep(30)"
    )
    control = ExecutionControl()
    outcome: list[ProcessOutcome] = []
    worker = threading.Thread(
        target=lambda: outcome.append(
            FFmpegProcessRunner().run_controlled((sys.executable, "-c", parent), 10, control)
        )
    )
    worker.start()
    import time

    deadline = time.monotonic() + 5
    while not heartbeat.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert heartbeat.exists()
    control.cancellation.cancel()
    worker.join(10)
    assert not worker.is_alive() and outcome[0].safe_to_cleanup
    assert outcome[0].error_code == "PROCESS_CANCELLED"
    content = heartbeat.read_bytes()
    time.sleep(0.1)
    assert heartbeat.read_bytes() == content
    assert not CancellationToken().requested


def test_extraction_rejects_stale_confirmation(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264")])
    source = replace(source, format=replace(source.format, name="mp4"))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 0), str(tmp_path / "out.h264")
    )
    inspector = Mock()
    with pytest.raises(ExecutionFailure, match="UNCONFIRMED_PLAN"):
        ExtractionExecutionService._regenerate(ExecutionRequest(plan, plan.revision), inspector)
    inspector.inspect.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "wrong_codec",
        "wrong_format",
        "extra_stream",
        "empty",
        "truncated",
        "technical",
        "packet_error",
    ],
)
def test_extraction_validator_rejects_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from mediatrack_forge.infrastructure.extraction_validation import ExtractionValidator

    source = asset(tmp_path, [stream(4, "video", "h264") | {"width": 64}])
    source = replace(source, format=replace(source.format, name="mp4"))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 4), str(tmp_path / "out.h264")
    )
    path = tmp_path / "reserved.part"
    path.write_bytes(b"" if failure == "empty" else b"staged output")
    actual = replace(
        source,
        format=replace(source.format, name="wrong" if failure == "wrong_format" else "h264"),
        streams=(
            replace(
                source.streams[0], index=0, codec="hevc" if failure == "wrong_codec" else "h264"
            ),
        ),
    )
    if failure == "extra_stream":
        actual = replace(actual, streams=actual.streams + actual.streams)
    if failure == "technical":
        actual = replace(
            actual,
            streams=(
                replace(
                    actual.streams[0], properties=replace(actual.streams[0].properties, width=32)
                ),
            ),
        )
    inspector = Mock()
    inspector.inspect.return_value = actual
    counter = Mock(
        side_effect=ValueError
        if failure == "packet_error"
        else [10, 5 if failure == "truncated" else 10]
    )
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.packet_count", counter
    )
    report = ExtractionValidator().validate(plan, path, inspector, 30)
    assert not report.passed and report.checks[-1].code == "EXTRACTION_INVALID"


@pytest.mark.parametrize("mutation", ["reference", "filter", "destination", "source"])
def test_extraction_regeneration_rejects_forged_or_changed_intent(
    tmp_path: Path, mutation: str
) -> None:
    source = asset(tmp_path, [stream(4, "video", "h264")])
    source = replace(source, format=replace(source.format, name="mp4"))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 4), str(tmp_path / "out.h264")
    )
    plan = replace(
        plan,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    inspector = Mock()
    inspector.inspect.return_value = source
    if mutation == "reference":
        plan = replace(
            plan,
            selections=(replace(plan.selections[0], reference=StreamReference(source.source, 88)),),
        )
    elif mutation == "filter":
        plan = replace(plan, bitstream_filters=("arbitrary_filter",))
    elif mutation == "destination":
        assert plan.destination_path is not None
        plan.destination_path.write_bytes(b"existing")
    else:
        inspector.inspect.return_value = replace(source, streams=())
    with pytest.raises(ExecutionFailure):
        ExtractionExecutionService._regenerate(
            ExecutionRequest(plan, plan.revision, plan.revision), inspector
        )


@pytest.mark.parametrize("unsafe", [False, True])
def test_cancel_outcome_does_not_claim_unverified_termination(
    execution_request: ExecutionRequest, unsafe: bool
) -> None:
    runner = Mock()
    runner.run.return_value = ProcessOutcome(-1, "PROCESS_CANCELLED", not unsafe)
    result = service(execution_request, runner=runner).execute(execution_request)
    assert result.state == ("failed" if unsafe else "cancelled")
    assert result.cleanup_complete != unsafe and not result.published


def test_cancel_after_validator_returns_prevents_publication(
    execution_request: ExecutionRequest,
) -> None:
    from mediatrack_forge.domain.execution import ValidationReport

    control = ExecutionControl()
    validator = Mock()

    def validate(*args: object) -> ValidationReport:
        control.cancellation.cancel()
        return ValidationReport((), None, ())

    validator.validate.side_effect = validate
    result = service(execution_request, validator=validator).execute(
        execution_request, control=control
    )
    assert result.state == "cancelled" and not result.published and result.cleanup_complete


def test_runner_cancel_before_launch_and_timeout_race() -> None:
    control = ExecutionControl()
    control.cancellation.cancel()
    outcome = FFmpegProcessRunner().run_controlled(("nonexistent",), 1, control)
    assert outcome.error_code == "PROCESS_CANCELLED" and outcome.safe_to_cleanup
    # Both become observable together: cancellation is checked before the deadline.
    outcome = FFmpegProcessRunner().run_controlled((sys.executable, "-c", "pass"), 0.0001, control)
    assert outcome.error_code == "PROCESS_CANCELLED"

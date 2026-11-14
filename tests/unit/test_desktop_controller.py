"""Display-free orchestration, identity, review and lifecycle regressions."""

import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_planning import asset, stream

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.application.inspection import ProbeFailedError
from mediatrack_forge.domain.execution import ExecutionResult, ProgressEvent
from mediatrack_forge.domain.planning import ExternalTrack, MetadataIntent, StreamReference
from mediatrack_forge.ui.presentation_model import DesktopBackend, DesktopController, result_text
from mediatrack_forge.ui.worker import Worker, WorkerReply


def settle(controller: DesktopController) -> None:
    deadline = time.monotonic() + 5
    while controller.worker.busy and time.monotonic() < deadline:
        controller.poll()
        time.sleep(0.001)
    assert not controller.worker.busy


@pytest.fixture
def model(tmp_path: Path) -> DesktopController:
    controller = DesktopController()
    source = asset(
        tmp_path,
        [
            stream(5, "video", "h264"),
            stream(8, "audio", "aac"),
            stream(12, "audio", "aac"),
            stream(23, "data", "bin_data"),
        ],
    )
    source = replace(source, format=replace(source.format, tags=(("title", "Synthetic"),)))
    controller.apply(WorkerReply(0, "inspect", source))
    controller.change(destination=str(tmp_path / "out.mkv"))
    return controller


def test_empty_and_backend_imports_do_not_load_gui() -> None:
    controller = DesktopController()
    assert not controller.intent.sources and not controller.can_execute
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from mediatrack_forge.ui.presentation_model import DesktopController; "
            "DesktopController(); assert 'tkinter' not in sys.modules; "
            "assert 'customtkinter' not in sys.modules",
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "kind,codec,family,extension",
    [("audio", "aac", "mp4", "aac"), ("subtitle", "subrip", "matroska", "srt")],
)
def test_desktop_extraction_does_not_require_video(
    tmp_path: Path, kind: str, codec: str, family: str, extension: str
) -> None:
    source = asset(tmp_path, [stream(7, kind, codec) | {"profile": "LC"}])
    source = replace(source, format=replace(source.format, name=family))
    controller = DesktopController()
    controller.apply(WorkerReply(0, "inspect", source))
    reference = controller.intent.selections[0].reference
    controller.change(
        mode="Extract", extraction_target=reference, destination=str(tmp_path / f"out.{extension}")
    )
    controller.generate_plan()
    settle(controller)
    assert controller.plan is not None and controller.plan.intrinsically_valid
    controller.acknowledge(frozenset(controller.plan.pending_warnings), controller.plan.revision)
    settle(controller)
    assert controller.can_execute and controller.plan.included[0].reference.index == 7


def test_all_streams_visible_and_explicit_edits_keep_original_identity(
    model: DesktopController,
) -> None:
    original = model.intent.sources[0]
    assert [s.reference.index for s in model.intent.selections] == [5, 8, 12, 23]
    reference = model.intent.selections[1].reference
    model.edit_track(
        reference,
        include=False,
        metadata=MetadataIntent(language="", title="", default=False, forced=True),
    )
    assert model.intent.selections[1].metadata == MetadataIntent("", "", False, True)
    assert not model.intent.selections[1].include
    assert model.intent.sources[0] == original
    model.move(model.intent.selections[2].reference, -1)
    assert [s.reference.index for s in model.intent.selections] == [5, 12, 8, 23]
    model.move(model.intent.selections[0].reference, 1)
    assert model.intent.selections[0].reference.index == 5  # Cannot cross kinds.
    with pytest.raises(ValueError):
        model.move(reference, 2)


def ready(model: DesktopController) -> None:
    model.edit_track(model.intent.selections[-1].reference, include=False)
    model.generate_plan()
    settle(model)
    assert model.plan is not None and model.plan.intrinsically_valid
    assert model.progress is None  # A finished review must not remain visibly preparing.
    model.acknowledge(frozenset(model.plan.pending_warnings), model.plan.revision)
    settle(model)
    assert model.can_execute


def test_warning_acknowledgement_and_final_confirmation_are_separate(
    model: DesktopController,
) -> None:
    model.edit_track(model.intent.selections[-1].reference, include=False)
    model.edit_track(model.intent.selections[0].reference, metadata=MetadataIntent(language="und"))
    model.generate_plan()
    settle(model)
    assert model.plan is not None and model.plan.pending_warnings and not model.can_execute
    revision = model.plan.revision
    warnings = frozenset(model.plan.pending_warnings)
    assert len(warnings) >= 2
    model.acknowledge(frozenset({sorted(warnings)[0]}), revision)
    settle(model)
    assert not model.can_execute and model.confirmed_revision is None
    assert model.plan.effective_acknowledged_warnings and model.plan.pending_warnings
    model.acknowledge(warnings, revision)
    settle(model)
    assert model.can_execute and model.confirmed_revision is None
    with pytest.raises(ValueError):
        model.execute("another revision")
    assert not model.worker.busy


@pytest.mark.parametrize(
    "change",
    [
        "destination",
        "container",
        "mode",
        "preserve_chapters",
        "metadata",
        "order",
        "include",
        "target",
    ],
)
def test_every_intent_change_invalidates_review(model: DesktopController, change: str) -> None:
    ready(model)
    assert model.plan is not None
    old = model.plan
    reference = model.intent.selections[1].reference
    if change == "metadata":
        model.edit_track(reference, metadata=MetadataIntent(title="Changed"))
    elif change == "order":
        model.move(reference, 1)
    elif change == "include":
        model.edit_track(reference, include=False)
    elif change == "target":
        model.change(extraction_target=reference)
    elif change == "destination":
        model.change(destination="changed.mkv")
    elif change == "container":
        model.change(container="mp4")
    elif change == "mode":
        model.change(mode="Extract")
    else:
        model.change(preserve_chapters=False)
    model.apply(WorkerReply(model.generation - 1, "plan", old))
    assert model.plan is None and not model.can_execute and model.confirmed_revision is None
    with pytest.raises(ValueError):
        model.acknowledge(frozenset(old.pending_warnings), old.revision)


def test_changed_plan_during_acknowledgement_requires_fresh_review(
    model: DesktopController,
) -> None:
    ready(model)
    assert model.plan is not None
    changed = replace(model.plan, preserve_chapters=False)
    model.apply(WorkerReply(model.generation, "acknowledge", changed))
    assert model.error and model.plan is None and not model.can_execute


def test_external_add_edit_remove_and_primary_replacement(
    model: DesktopController, tmp_path: Path
) -> None:
    source = asset(tmp_path, [stream(7, "subtitle", "subrip")], name="external.srt")
    track = ExternalTrack(source.source, "subtitle", 7, "subrip", "srt", validated=True)
    model.apply(WorkerReply(model.generation, "subtitles", ((source, track), (source, track))))
    assert len(model.intent.sources) == 2
    reference = StreamReference(source.source, 7)
    model.edit_track(
        reference, metadata=MetadataIntent(language="eng", title="Caption", default=False)
    )
    assert model.intent.external_tracks[0].metadata == model.intent.selections[-1].metadata
    model.remove_external(reference)
    assert len(model.intent.sources) == 1 and source.source.path.exists()
    backend = Mock(spec=DesktopBackend)
    backend.inspect.return_value = source
    model.backend = backend
    model.open_media(str(source.source.path))
    assert model.plan is None and not model.intent.sources
    settle(model)
    assert model.intent.sources == (source,) and not model.intent.external_tracks
    model.apply(WorkerReply(model.generation - 1, "inspect", model.intent.sources[0]))
    assert model.intent.sources == (source,)


@pytest.mark.parametrize(
    "error", [RuntimeError("private vendor output"), ProbeFailedError("private path")]
)
def test_worker_errors_are_safe_recoverable_and_bounded(
    model: DesktopController, error: Exception
) -> None:
    original = model.intent.sources[0]
    backend = Mock(spec=DesktopBackend)
    backend.inspect.side_effect = error
    model.backend = backend
    model.open_media("input")
    settle(model)
    assert model.error and "private" not in model.error and not model.can_execute
    backend.inspect.side_effect = None
    backend.inspect.return_value = original
    model.open_media("input")
    settle(model)
    assert model.error is None and model.intent.sources == (original,)


def test_worker_single_task_latest_progress_and_safe_close() -> None:
    worker = Worker()
    release = threading.Event()
    control = ExecutionControl(listener=worker.progress)
    worker.start(7, "execute", lambda: release.wait(3), control=control)
    with pytest.raises(ValueError):
        worker.start(8, "inspect", lambda: None)
    for n in range(10000):
        worker.progress(ProgressEvent("running", True, min(n, 99)))
    event, reply = worker.poll()
    assert event is not None and event.percent == 99 and reply is None
    assert worker.cancel() and control.cancellation.requested
    release.set()
    deadline = time.monotonic() + 3
    while worker.busy and time.monotonic() < deadline:
        _, reply = worker.poll()
        time.sleep(0.001)
    assert reply is not None and reply.generation == 7
    assert worker.poll() == (None, None)


@pytest.mark.parametrize(
    "published,cleanup", [(False, True), (True, True), (True, False), (False, False)]
)
def test_terminal_result_and_shutdown_are_truthful(
    model: DesktopController, published: bool, cleanup: bool
) -> None:
    result = ExecutionResult(
        "completed" if published and cleanup else "failed",
        (),
        (),
        destination=Path("out.mkv") if published else None,
        published=published,
        cleanup_complete=cleanup,
    )
    model.close_pending = True
    model.apply(WorkerReply(model.generation, "execute", result))
    assert ("Published: yes" in result_text(result)) == published
    assert model.safe_to_close == cleanup
    assert model.request_close(False) == cleanup
    if not cleanup:
        with pytest.raises(ValueError):
            model.change(destination="another.mkv")


def test_close_active_worker_waits_for_terminal_result(model: DesktopController) -> None:
    release = threading.Event()
    control = ExecutionControl(listener=model.worker.progress)
    model.worker.start(
        model.generation,
        "execute",
        lambda: (release.wait(3), ExecutionResult("cancelled", (), ()))[1],
        control=control,
    )
    assert not model.request_close(False) and not model.close_pending
    assert not model.request_close(True) and model.close_pending and control.cancellation.requested
    assert not model.safe_to_close
    release.set()
    settle(model)
    assert model.safe_to_close
    model.closed = True
    previous = model.intent
    model.apply(WorkerReply(model.generation, "inspect", object()))
    assert model.intent == previous and not model.poll()

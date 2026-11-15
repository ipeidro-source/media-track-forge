"""Explicit native-display tests; never silently skipped when invoked."""

import gc
import hashlib
import json
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.application.inspection import InvalidInputError, snapshot_source
from mediatrack_forge.domain.execution import ExecutionRequest, ExecutionResult
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.infrastructure.ffprobe_json import parse_response
from mediatrack_forge.ui.language_dialog import LanguageDialog
from mediatrack_forge.ui.presentation_model import DesktopBackend, DesktopController
from mediatrack_forge.ui.window import DesktopWindow
from mediatrack_forge.ui.wizard import Step


def pump(window: DesktopWindow, *, idle: bool = True) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        window.root.update()
        if not idle or not window.controller.worker.busy:
            window.root.update()
            return
        time.sleep(0.01)
    raise AssertionError("GUI worker did not finish within the smoke-test deadline")


class FakeBackend(DesktopBackend):
    def __init__(self, source: MediaAsset) -> None:
        super().__init__()
        self.source = source
        self.started = threading.Event()

    def inspect(self, path: str) -> MediaAsset:
        return self.source

    def execute(self, request: ExecutionRequest, control: ExecutionControl) -> ExecutionResult:
        control.expected_seconds = 1
        control.emit("running", 0.25)
        self.started.set()
        deadline = time.monotonic() + 5
        while not control.cancellation.requested and time.monotonic() < deadline:
            time.sleep(0.01)
        control.emit("cancelled")
        return ExecutionResult("cancelled", ("planned", "running", "cancelling", "cancelled"), ())


@pytest.fixture
def window(tmp_path: Path) -> Iterator[DesktopWindow]:
    path = tmp_path / "synthetic 日本語.mp4"
    path.write_bytes(b"synthetic fake inspection input")
    source = parse_response(
        json.dumps(
            {
                "format": {
                    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                    "tags": {"major_brand": "isom"},
                },
                "streams": [
                    {
                        "index": 3,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "disposition": {"default": 0, "forced": 0},
                    },
                    {
                        "index": 17,
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "profile": "LC",
                        "tags": {"language": "eng", "title": "Original audio"},
                        "disposition": {"default": 0, "forced": 0},
                    },
                ],
            }
        ).encode(),
        snapshot_source(path),
    )
    app = DesktopWindow(DesktopController(FakeBackend(source)))
    yield app
    if app.controller.worker.busy:
        app.controller.cancel()
        pump(app)
    if not app._destroyed:
        app.destroy()


def open_fake(window: DesktopWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.filedialog.askopenfilename", lambda **kwargs: "synthetic"
    )
    window.open_media()
    pump(window)
    assert len(window.table.get_children()) == 2


def advance_to_operation(window: DesktopWindow) -> None:
    if int(window.wizard.step) == Step.MEDIA:
        window.next()
    if int(window.wizard.step) == Step.METADATA:
        window.next()
    window.root.update()
    assert int(window.wizard.step) == Step.OPERATION


def enter_review(window: DesktopWindow) -> None:
    advance_to_operation(window)
    window.review()
    pump(window)
    assert int(window.wizard.step) == Step.REVIEW
    assert window.controller.plan is not None


def test_native_window_track_identity_metadata_review_and_cancel(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert window.root.title() == "MediaTrack Forge"
    assert window.next_button.cget("state") == "disabled"
    assert int(window.wizard.step) == Step.MEDIA
    assert not hasattr(window, "tabs") and not hasattr(window, "review_button")
    open_fake(window, monkeypatch)
    assert not window.track_frame.winfo_viewable()
    window.next()
    assert int(window.wizard.step) == Step.METADATA
    reference = next(ref for ref in window._rows.values() if ref.index == 17)
    window._select_reference(reference)
    window.track_title.set("Edited audio")
    window.next()
    assert int(window.wizard.step) == Step.OPERATION
    window.back()
    assert window.track_title.get() == "Edited audio"
    window.next()
    window._select_reference(reference)
    window.toggle()
    window.destination.set(str(tmp_path / "output.mkv"))
    enter_review(window)
    assert window.controller.plan and window.controller.plan.pending_warnings
    assert "Accept warnings" in window.execute_button.cget("text")
    assert not window.controller.worker.busy
    assert not window.controller.confirmed_revision
    assert "original index 3" in window.review_text.get("1.0", "end")
    # Any extra confirmation popup is a regression.
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.messagebox.askyesno",
        lambda *a, **kw: pytest.fail("Unexpected confirmation"),
    )
    window.execute()
    assert not window._guard(window.execute)  # A second decision cannot authorize twice.
    deadline = time.monotonic() + 5
    while window.controller.worker.control is None and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    assert int(window.wizard.step) == Step.EXECUTION
    assert not window.back_button.winfo_ismapped()
    window.cancel()
    pump(window)
    assert window.controller.result and window.controller.result.state == "cancelled"
    assert "Published: no" in window.result_text.get("1.0", "end")
    assert window.restart_button.cget("state") == "normal"


def test_native_review_invalidated_by_unapplied_metadata_and_destination(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_fake(window, monkeypatch)
    window.next()
    reference = next(ref for ref in window._rows.values() if ref.index == 17)
    window._select_reference(reference)
    window.language.set("invalid-code")
    assert not window._guard(window.next)
    assert int(window.wizard.step) == Step.METADATA and window.metadata_error.get()
    window.reset_metadata()
    window.next()
    window.destination.set(str(tmp_path / "output.mkv"))
    enter_review(window)
    window.back()
    assert int(window.wizard.step) == Step.OPERATION
    window.destination.set(str(tmp_path / "different.mkv"))
    assert window.controller.plan is None and window.controller.reviewed_revision is None
    window.review()
    pump(window)
    assert (
        window.controller.plan
        and window.controller.plan.destination_path == tmp_path / "different.mkv"
    )


def test_native_close_waits_for_safe_cancellation(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_fake(window, monkeypatch)
    window.destination.set(str(tmp_path / "output.mkv"))
    enter_review(window)
    window.execute()
    deadline = time.monotonic() + 5
    while window.controller.worker.control is None and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    monkeypatch.setattr("mediatrack_forge.ui.window.messagebox.askyesno", lambda *a, **kw: True)
    window.close()
    assert not window._destroyed
    deadline = time.monotonic() + 5
    while not window._destroyed and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    assert window._destroyed and window.controller.closed


def test_real_gui_to_backend_video_only_remux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    assert ffmpeg and ffprobe, "Real GUI smoke requires installed FFmpeg/ffprobe; no skips"
    source = tmp_path / "synthetic source 日本語.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=s=64x48:r=10:d=0.4",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=0.4:sample_rate=48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    window = DesktopWindow()
    try:
        monkeypatch.setattr(
            "mediatrack_forge.ui.window.filedialog.askopenfilename", lambda **kwargs: str(source)
        )
        window.open_media()
        pump(window)
        audio_row = next(
            row
            for row, ref in window._rows.items()
            if window.controller.stream(ref).kind == "audio"
        )
        window.table.selection_set(audio_row)
        window._select_row()
        window.toggle()
        output = tmp_path / "result 日本語.mp4"
        window.container.set("mp4")
        window.destination.set(str(output))
        enter_review(window)
        monkeypatch.setattr(
            "mediatrack_forge.ui.window.messagebox.askyesno", lambda *args, **kwargs: True
        )
        window.execute()
        pump(window)
        assert window.controller.result is not None and window.controller.result.published, (
            window.controller.status
        )
        actual = window.controller.backend.inspect(str(output))
        assert [s.kind for s in actual.streams] == ["video"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original
        assert "Published: yes" in window.result_text.get("1.0", "end")
        assert not list(tmp_path.glob(".mediatrack-*"))
    finally:
        if window.controller.worker.busy:
            window.controller.cancel()
            pump(window)
        window.destroy()


@pytest.mark.parametrize("appearance,scale", [("Light", 1.0), ("Dark", 1.25), ("Light", 1.5)])
def test_native_theme_scaling_and_resize(
    window: DesktopWindow, appearance: str, scale: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    import customtkinter as ctk

    try:
        window.root.update()
        assert window.root.winfo_width() >= min(1100, window._screen_bounds()[0])
        window.root.geometry("620x600" if scale == 1 else "900x700")
        window.root.update()
        size = window.root.geometry().split("+")[0]
        open_fake(window, monkeypatch)
        assert window.root.geometry().split("+")[0] == size
        window.next()
        ctk.set_appearance_mode(appearance)
        ctk.set_widget_scaling(scale)
        window._select_reference(next(ref for ref in window._rows.values() if ref.index == 17))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            window.root.update()
            if window._appearance == appearance:
                break
            time.sleep(0.01)
        assert window._appearance == appearance
        assert (
            window.reset_button.winfo_x() + window.reset_button.winfo_width()
            <= window.reset_button.master.winfo_width() + 2
        )
        window.reset_button._canvas.focus_force()
        window.root.update()
        assert (
            window.root.winfo_rooty()
            < window.reset_button.winfo_rooty()
            < window.root.winfo_rooty() + window.root.winfo_height()
        )
        window.next()
        window.root.update()
        assert window.table.winfo_viewable() and window.next_button.winfo_ismapped() == 0
        assert window.remux_button.winfo_viewable()
    finally:
        ctk.set_widget_scaling(1)
        ctk.set_appearance_mode("system")


def test_native_failure_preserves_published_cleanup_evidence(window: DesktopWindow) -> None:
    from mediatrack_forge.ui.worker import WorkerReply

    result = ExecutionResult(
        "failed",
        (),
        (),
        destination=Path("synthetic-output.mkv"),
        published=True,
        cleanup_complete=False,
    )
    window.controller.apply(WorkerReply(window.controller.generation, "execute", result))
    window._refresh()
    assert int(window.wizard.step) == Step.EXECUTION
    assert "INCOMPLETE" in window.result_text.get("1.0", "end")
    assert window.restart_button.cget("state") == "disabled"
    assert window.close_button.cget("state") == "disabled"
    assert not window.controller.request_close(False)
    with pytest.raises(ValueError):
        window.start_over()
    assert "INCOMPLETE" in window.result_text.get("1.0", "end")


def test_refined_metadata_extraction_destination_and_recovery(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_fake(window, monkeypatch)
    advance_to_operation(window)
    assert window.extract_button.cget("state") == "disabled"  # No implicit extraction target.
    reference = next(ref for ref in window._rows.values() if ref.index == 17)
    window._select_reference(reference)
    included = window.controller.intent.selections
    window.mode.set("Extract")
    assert window.controller.intent.extraction_target == reference
    assert window.format_menu.cget("values") == ["aac"]
    assert window.controller.intent.selections == included
    assert "original index 17" in window.extraction_description.get()
    existing = tmp_path / "occupied.aac"
    existing.write_bytes(b"untouched")
    options = {}

    def save_dialog(**kwargs: object) -> str:
        options.update(kwargs)
        return str(existing)

    monkeypatch.setattr("mediatrack_forge.ui.window.filedialog.asksaveasfilename", save_dialog)
    window.choose_destination()
    assert options["confirmoverwrite"] is False
    window._check_destination()
    pump(window)
    assert "exists" in window.destination_error.get()
    window.suggest_destination()
    pump(window)
    assert window.destination.get().endswith(".aac") and Path(window.destination.get()) != existing
    assert existing.read_bytes() == b"untouched" and not Path(window.destination.get()).exists()
    window.back()
    window.back()
    previous = window.controller.intent
    errors = []
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.messagebox.showerror", lambda *a, **kw: errors.append(a)
    )

    def failed(path: str) -> MediaAsset:
        raise InvalidInputError("Source unavailable; choose a readable file.")

    monkeypatch.setattr(window.controller.backend, "inspect", failed)
    window.open_media()
    pump(window)
    window.root.update()
    assert window.controller.intent == previous and window._selected == reference
    assert len(errors) == 1 and errors[0][0] == "Unable to open media"
    assert "preserved" in errors[0][1] and "Source unavailable" not in errors[0][1]
    window.root.update()
    assert len(errors) == 1
    monkeypatch.setattr(window.controller.backend, "inspect", lambda path: previous.sources[0])
    window.open_media()
    pump(window)
    assert window._selected is None and window.controller.intent.mode == "Remux"


def test_refined_progress_repeated_execution_and_variable_teardown(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mediatrack_forge.domain.execution import ProgressEvent
    from mediatrack_forge.ui.worker import WorkerReply

    open_fake(window, monkeypatch)
    window.destination.set(str(tmp_path / "output.mkv"))
    enter_review(window)
    window.controller.worker.start(
        window.controller.generation, "destination", lambda: (gc.collect(), "")[1]
    )
    pump(window)
    starts = []
    monkeypatch.setattr(window.progress_bar, "start", lambda: starts.append(True))
    release = threading.Event()
    window.controller.worker.start(
        window.controller.generation, "execute", lambda: release.wait(5), control=ExecutionControl()
    )
    window.controller.progress = ProgressEvent("running", False, processed_seconds=65)
    for _ in range(5):
        window._refresh()
    assert len(starts) == 1 and "Media position 00:01:05" in window.phase.get()
    release.set()
    deadline = time.monotonic() + 3
    while window.controller.worker.busy and time.monotonic() < deadline:
        window.controller.worker.poll()
        time.sleep(0.01)
    window.controller.apply(
        WorkerReply(window.controller.generation, "execute", ExecutionResult("cancelled", (), ()))
    )
    window._refresh()
    assert "Cancelled" in window.phase.get() and window.cancel_button.cget("state") == "disabled"
    size = window.root.geometry().split("+")[0]
    original = window.controller.intent.sources[0].source.path
    window.start_over()
    window.root.update()
    assert int(window.wizard.step) == Step.MEDIA and not window.controller.intent.sources
    assert window._selected is None and not window.destination.get() and not window.controller.plan
    assert window.root.geometry().split("+")[0] == size and original.exists()
    assert "cancelled" not in window.result_text.get("1.0", "end")
    open_fake(window, monkeypatch)
    window.destination.set(str(tmp_path / "second.mkv"))
    enter_review(window)
    window.execute()
    deadline = time.monotonic() + 5
    while window.controller.worker.control is None and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    window.cancel()
    pump(window)


def test_refined_external_subtitle_group_and_duplicate_feedback(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mediatrack_forge.domain.planning import ExternalTrack

    open_fake(window, monkeypatch)
    advance_to_operation(window)
    path = tmp_path / "external.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\nSynthetic\n", encoding="utf-8")
    source = parse_response(
        json.dumps(
            {
                "format": {"format_name": "srt"},
                "streams": [{"index": 0, "codec_type": "subtitle", "codec_name": "subrip"}],
            }
        ).encode(),
        snapshot_source(path),
    )
    external = ExternalTrack(source.source, "subtitle", 0, "subrip", "srt", validated=True)
    monkeypatch.setattr(
        window.controller.backend,
        "import_subtitles",
        lambda paths: ((source, external), (source, external)),
    )
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.filedialog.askopenfilenames",
        lambda **kwargs: (str(path), str(path)),
    )
    window.add_subtitles()
    pump(window)
    assert window._selected and window._selected.source == source.source
    assert "Skipped 1" in window.status.get() and window.extract_button.cget("state") == "disabled"
    assert not window.metadata_area.winfo_viewable()
    window.edit_external_metadata()
    assert int(window.wizard.step) == Step.METADATA
    window.track_title.set("Imported title")
    window.next()
    assert window.controller.intent.external_tracks[0].metadata.title == "Imported title"
    window.remove_external()
    assert path.exists() and len(window.controller.intent.sources) == 1


def test_native_language_search_clear_unknown_and_keyboard(
    window: DesktopWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = window.controller.backend
    assert isinstance(backend, FakeBackend)
    video, audio = backend.source.streams
    backend.source = replace(backend.source, streams=(video, replace(audio, language="zzz")))
    open_fake(window, monkeypatch)
    window.next()
    reference = next(ref for ref in window._rows.values() if ref.index == 17)
    window._select_reference(reference)
    assert window.language.get() == "zzz"
    window.track_title.set("Keep unknown language")
    window._save_metadata()
    assert window.controller.intent.selections[1].metadata.language is None
    window.language.set("")
    window._save_metadata()
    assert window.controller.intent.selections[1].metadata.language == ""
    window.reset_metadata()
    assert window.language.get() == "zzz"
    chosen: list[str] = []
    dialog = LanguageDialog(window.root, "zzz", "zzz", chosen.append)
    window.root.update()
    assert any(code == "zzz" for code, _ in dialog.choices)
    dialog.search.insert(0, "Japanese")
    dialog.refresh()
    assert dialog.choices == [("jpn", "Japanese (jpn)")]
    dialog.focus_list()
    dialog.accept()
    assert chosen == ["jpn"]
    dialog = LanguageDialog(window.root, "zzz", "zzz", chosen.append)
    dialog.search.insert(0, "Unspecified")
    dialog.refresh()
    dialog.accept()
    assert chosen[-1] == ""
    assert window.root.bind("<Alt-Left>") and window.root.bind("<Alt-Right>")


def test_native_keyboard_navigation_and_exact_selected_extraction(
    window: DesktopWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    open_fake(window, monkeypatch)
    window.next_button._canvas.focus_force()
    window.next_button._canvas.event_generate("<Return>")
    window.root.update()
    assert int(window.wizard.step) == Step.METADATA
    reference = next(ref for ref in window._rows.values() if ref.index == 17)
    row = next(row for row, ref in window._rows.items() if ref == reference)
    window.metadata_table.selection_set(row)
    window.metadata_table.event_generate("<<TreeviewSelect>>")
    window.root.update()
    window.next_button.invoke()
    window.root.update()
    assert int(window.wizard.step) == Step.OPERATION
    included = window.controller.intent.selections
    window.mode.set("Extract")
    assert window.controller.intent.extraction_target == reference
    assert window.controller.intent.selections == included
    window.table.selection_set("group-audio")
    window.table.event_generate("<<TreeviewSelect>>")
    window.root.update()
    assert window._selected is None and window.controller.intent.extraction_target is None
    assert window.extract_button.cget("state") == "disabled"
    window._select_reference(reference)
    assert window.extract_button.cget("state") == "normal"
    window.destination.set(str(tmp_path / "selected.aac"))
    window.extract_button.invoke()
    assert "Preparing" in window.review_text.get("1.0", "end")
    pump(window)
    assert window.controller.plan and window.controller.plan.included[0].reference == reference
    assert len(window.controller.plan.included) == 1


def test_native_invalid_plan_blocks_explicit_execute(
    window: DesktopWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_fake(window, monkeypatch)
    advance_to_operation(window)
    # All-excluded intent must remain visible as a blocker, never auto-repaired.
    for ref in tuple(window._rows.values()):
        window.controller.edit_track(ref, include=False)
    window.review_mode("Remux")
    pump(window)
    assert int(window.wizard.step) == Step.REVIEW
    assert window.controller.plan and not window.controller.plan.intrinsically_valid
    assert window.execute_button.cget("state") == "disabled"
    assert not window._guard(window.execute)
    assert not window.controller.worker.busy

"""Explicit native-display tests; never silently skipped when invoked."""

import gc
import hashlib
import json
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.application.inspection import InvalidInputError, snapshot_source
from mediatrack_forge.domain.execution import ExecutionRequest, ExecutionResult
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.infrastructure.ffprobe_json import parse_response
from mediatrack_forge.ui.presentation_model import DesktopBackend, DesktopController
from mediatrack_forge.ui.window import DesktopWindow


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


def acknowledge(window: DesktopWindow) -> None:
    window.review()
    pump(window)
    assert window.controller.plan is not None
    assert window._warning_vars
    assert str(window.execute_button.cget("state")) == "disabled"
    for variable in window._warning_vars.values():
        variable.set(True)
    window.acknowledge()
    pump(window)
    assert window.controller.can_execute


def test_native_window_track_identity_metadata_review_and_cancel(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert window.root.title() == "MediaTrack Forge"
    assert [window.tabs.tab(name) for name in ("1. Media", "2. Operation", "3. Execution")]
    open_fake(window, monkeypatch)
    window.sort_table("codec")
    audio_row = next(row for row, ref in window._rows.items() if ref.index == 17)
    window.table.selection_set(audio_row)
    window._select_row()
    assert window._selected is not None and window._selected.index == 17
    window.track_title.set("")
    window.default.set("No")
    window._save_metadata()
    assert (
        next(
            s for s in window.controller.intent.selections if s.reference.index == 17
        ).metadata.title
        == ""
    )
    window.toggle()
    assert not next(
        s for s in window.controller.intent.selections if s.reference.index == 17
    ).include
    window.destination.set(str(tmp_path / "output.mkv"))
    acknowledge(window)
    assert "original index 3" in window.review_text.get("1.0", "end")
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.messagebox.askyesno", lambda *args, **kwargs: False
    )
    window.execute()
    assert not window.controller.worker.busy and window.controller.confirmed_revision is None
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.messagebox.askyesno", lambda *args, **kwargs: True
    )
    window.execute()
    backend = window.controller.backend
    assert isinstance(backend, FakeBackend) and backend.started.wait(2)
    pump(window, idle=False)
    window.cancel()
    pump(window)
    assert window.controller.result is not None and window.controller.result.state == "cancelled"
    assert "Published: no" in window.result_text.get("1.0", "end")


def test_native_review_invalidated_by_unapplied_metadata_and_destination(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_fake(window, monkeypatch)
    window.destination.set(str(tmp_path / "output.mkv"))
    acknowledge(window)
    window.table.selection_set("track-0")
    window._select_row()
    window.language.set("eng")
    assert window.controller.plan is None and not window.controller.can_execute
    window.destination.set(str(tmp_path / "different.mkv"))
    assert window.controller.reviewed_revision is None
    window.extract_selected()
    assert window.mode.get() == "Extract" and window.format_menu.cget("values") == ["h264"]


def test_native_close_waits_for_safe_cancellation(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_fake(window, monkeypatch)
    window.destination.set(str(tmp_path / "output.mkv"))
    acknowledge(window)
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.messagebox.askyesno", lambda *args, **kwargs: True
    )
    window.execute()
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
        acknowledge(window)
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
        open_fake(window, monkeypatch)
        ctk.set_appearance_mode(appearance)
        ctk.set_widget_scaling(scale)
        window._select_reference(next(ref for ref in window._rows.values() if ref.index == 17))
        window.root.geometry("620x600" if scale == 1.0 else "900x700")
        window.tabs.set("1. Media")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            window.root.update()
            if window.table.winfo_width() > 100 and window._appearance == appearance:
                break
            time.sleep(0.01)
        assert window._appearance == appearance
        assert window.table.winfo_width() > 100 and window.table.winfo_height() > 20
        assert (
            window.reset_button.winfo_x() + window.reset_button.winfo_width()
            <= window.reset_button.master.winfo_width() + 2
        )
        if scale == 1.0:
            assert window.media._parent_canvas.yview()[1] < 1
            window.reset_button._canvas.focus_force()
            window.root.update()
            assert (
                window.root.winfo_rooty()
                < window.reset_button.winfo_rooty()
                < window.root.winfo_rooty() + window.root.winfo_height()
            )
        window.tabs.set("2. Operation")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            window.root.update()
            if window.review_text.winfo_width() > 100:
                break
            time.sleep(0.01)
        assert window.review_text.winfo_width() > 100
    finally:
        ctk.set_widget_scaling(1.0)
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
    text = window.result_text.get("1.0", "end")
    assert "Published: yes" in text and "INCOMPLETE" in text
    assert not window.controller.request_close(False)
    assert window.root.bind("<Alt-Key-1>") and window.root.bind("<Alt-Key-2>")


def test_refined_metadata_extraction_destination_and_recovery(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.root.update()
    assert not window.track_frame.winfo_ismapped()
    assert not window.metadata_area.winfo_viewable()
    initial = (window.root.winfo_width(), window.root.winfo_height())
    open_fake(window, monkeypatch)
    window.root.update()
    assert window.root.winfo_height() >= initial[1]
    assert window.table.item("group-audio", "text") == "Audio"
    reference = next(ref for ref in window._rows.values() if ref.index == 17)
    window._select_reference(reference)
    assert window.language.get() == "eng" and window.track_title.get() == "Original audio"
    window.track_title.set("Edited")
    window._save_metadata()
    row = next(row for row, ref in window._rows.items() if ref == reference)
    assert window.table.set(row, "title") == "* Edited"
    assert "changed" in window.table.item(row, "tags")
    window.track_title.set("Original audio")
    window._save_metadata()
    assert window.table.set(row, "title") == "Original audio"
    window.track_title.set("")
    window._save_metadata()
    assert (
        next(
            s for s in window.controller.intent.selections if s.reference == reference
        ).metadata.title
        == ""
    )
    window.reset_metadata()
    assert window.track_title.get() == "Original audio"
    window.language.set("invalid-code")
    with pytest.raises(ValueError, match="three-letter"):
        window._save_metadata()
    window.reset_metadata()
    window.mode.set("Extract")
    assert window.controller.intent.extraction_target is None
    assert window.format_menu.cget("values") == ["Unsupported selection"]
    window.tabs.set("2. Operation")
    window.root.update()
    window.extraction_menu._canvas.focus_force()
    window.extraction_menu._canvas.event_generate("<Right>")
    window.root.update()
    assert window.controller.intent.extraction_target is not None
    assert window.controller.intent.extraction_target.index == 3
    window.extraction_menu._canvas.event_generate("<Right>")
    window.root.update()
    assert window.controller.intent.extraction_target == reference
    label = next(label for label, ref in window._extraction_rows.items() if ref == reference)
    window.extraction_selection.set(label)
    window._choose_extraction()
    assert window.controller.intent.extraction_target == reference
    assert window.format_menu.cget("values") == ["aac"]
    assert "original index 17" in window.extraction_description.get()
    existing = tmp_path / "occupied.aac"
    existing.write_bytes(b"untouched")
    options: dict[str, object] = {}

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
    assert not Path(window.destination.get()).exists() and existing.read_bytes() == b"untouched"
    previous = window.controller.intent

    def failed_inspection(path: str) -> MediaAsset:
        raise InvalidInputError("Source unavailable; choose a readable file.")

    monkeypatch.setattr(window.controller.backend, "inspect", failed_inspection)
    window.open_media()
    pump(window)
    assert window.controller.intent == previous and window._selected == reference
    assert "Source unavailable" in window.controller.error
    window.root.geometry("780x560")
    window.root.update()
    dimensions = (window.root.winfo_width(), window.root.winfo_height())
    monkeypatch.setattr(window.controller.backend, "inspect", lambda path: previous.sources[0])
    window.open_media()
    pump(window)
    window.root.update()
    assert (window.root.winfo_width(), window.root.winfo_height()) == dimensions
    assert window._selected is None and window.controller.intent.mode == "Remux"


def test_refined_progress_repeated_execution_and_variable_teardown(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mediatrack_forge.domain.execution import ProgressEvent
    from mediatrack_forge.ui.worker import WorkerReply

    open_fake(window, monkeypatch)
    window.destination.set(str(tmp_path / "output.mkv"))
    acknowledge(window)
    # Force collection in a worker after the old warning controls have been destroyed.
    window.controller.worker.start(
        window.controller.generation, "destination", lambda: (gc.collect(), "")[1]
    )
    pump(window)
    starts: list[bool] = []
    monkeypatch.setattr(window.progress_bar, "start", lambda: starts.append(True))
    control = ExecutionControl()
    release = threading.Event()
    window.controller.worker.start(
        window.controller.generation, "execute", lambda: release.wait(5), control=control
    )
    window.controller.progress = ProgressEvent("running", False, processed_seconds=65)
    for _ in range(5):
        window._refresh()
    assert len(starts) == 1 and "Media position 00:01:05" in window.phase.get()
    release.set()
    # Consume the deliberately controlled worker directly; its value is not a product result.
    deadline = time.monotonic() + 3
    while window.controller.worker.busy and time.monotonic() < deadline:
        window.controller.worker.poll()
        time.sleep(0.01)
    result = ExecutionResult("cancelled", (), ())
    window.controller.apply(WorkerReply(window.controller.generation, "execute", result))
    window._refresh()
    assert "Cancelled" in window.phase.get() and "indeterminate" not in window.phase.get()
    assert window.cancel_button.cget("state") == "disabled"
    window.review()
    pump(window)
    for variable in window._warning_vars.values():
        variable.set(True)
    window.acknowledge()
    pump(window)
    monkeypatch.setattr(
        "mediatrack_forge.ui.window.messagebox.askyesno", lambda *args, **kwargs: True
    )
    window.execute()
    assert "Result: cancelled" not in window.result_text.get("1.0", "end")
    window.cancel()
    pump(window)


def test_refined_external_subtitle_group_and_duplicate_feedback(
    window: DesktopWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mediatrack_forge.domain.planning import ExternalTrack

    open_fake(window, monkeypatch)
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
    assert window.table.item("group-subtitle", "text") == "Subtitles"
    assert window._selected is not None and window._selected.source == source.source
    assert "Skipped 1" in window.status.get()
    window._copy_source_path()
    assert window.root.clipboard_get() == str(path)
    window.mode.set("Extract")
    label = next(
        label for label, ref in window._extraction_rows.items() if ref.source == source.source
    )
    window.extraction_selection.set(label)
    window._choose_extraction()
    assert "already an independent file" in window.extraction_description.get()
    assert window.format_menu.cget("values") == ["Unsupported selection"]
    window.remove_external()
    assert path.is_file() and len(window.controller.intent.sources) == 1
    assert not window.metadata_area.winfo_viewable()

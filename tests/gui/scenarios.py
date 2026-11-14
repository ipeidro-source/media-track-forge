"""Explicit native-display tests; never silently skipped when invoked."""

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
from mediatrack_forge.application.inspection import snapshot_source
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
    assert [window.tabs.tab(name) for name in ("Media", "Operation", "Execution")]
    open_fake(window, monkeypatch)
    window.sort_table("codec")
    audio_row = next(row for row, ref in window._rows.items() if ref.index == 17)
    window.table.selection_set(audio_row)
    window._select_row()
    assert window._selected is not None and window._selected.index == 17
    window.title_mode.set("Set value")
    window.track_title.set("")
    window.default.set("Off")
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
    window.language_mode.set("Set value")
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
    window: DesktopWindow, appearance: str, scale: float
) -> None:
    import customtkinter as ctk

    try:
        ctk.set_appearance_mode(appearance)
        ctk.set_widget_scaling(scale)
        window.root.geometry("900x700")
        window.tabs.set("Media")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            window.root.update()
            if window.table.winfo_width() > 100 and window._appearance == appearance:
                break
            time.sleep(0.01)
        assert window._appearance == appearance
        assert window.table.winfo_width() > 100 and window.table.winfo_height() > 20
        window.tabs.set("Operation")
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

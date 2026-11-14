"""Real backend user journeys through the display-free desktop controller."""

import hashlib
import time
from pathlib import Path

import pytest

from mediatrack_forge.domain.execution import ProcessConfiguration
from mediatrack_forge.ui.presentation_model import DesktopBackend, DesktopController

from .test_execution_e2e import media
from .test_planning_mux import planning_tools as planning_tools
from .test_pr05_e2e import RealtimeRunner

pytestmark = pytest.mark.integration


def settle(controller: DesktopController) -> None:
    deadline = time.monotonic() + 45
    while controller.worker.busy and time.monotonic() < deadline:
        controller.poll()
        time.sleep(0.005)
    assert not controller.worker.busy, controller.status


@pytest.mark.parametrize(
    "scenario",
    [
        "video_only",
        "one_audio",
        "avi_srt",
        "mp4_srt",
        "silent_srt",
        "incompatible",
        "same_path",
        "one_video",
        "bad_srt",
        "existing",
        "extract",
    ],
)
def test_desktop_user_journeys(
    tmp_path: Path, planning_tools: tuple[str, str], scenario: str
) -> None:
    kind = {
        "one_audio": "multiaudio",
        "avi_srt": "avi",
        "incompatible": "avi",
        "one_video": "multivideo",
    }.get(scenario, "mp4")
    if scenario == "silent_srt":
        from .conftest import VIDEO, generate

        silent = tmp_path / "silent 日本語.mp4"
        generate(
            planning_tools[0], [*VIDEO, "-map", "0:v:0", "-c:v", "libx264", "-threads", "1"], silent
        )
        asset = DesktopBackend().inspect(str(silent))
        assert not any(s.kind == "audio" for s in asset.streams)
    else:
        asset = media(tmp_path, planning_tools, kind)
    original = hashlib.sha256(asset.source.path.read_bytes()).hexdigest()
    controller = DesktopController(
        DesktopBackend(ProcessConfiguration(ffmpeg=planning_tools[0], ffprobe=planning_tools[1]))
    )
    controller.open_media(str(asset.source.path))
    settle(controller)
    assert controller.intent.sources == (asset,) and controller.error is None
    if scenario in ("video_only", "silent_srt"):
        for item in controller.intent.selections:
            if controller.stream(item.reference).kind == "audio":
                controller.edit_track(item.reference, include=False)
    if scenario in ("one_audio", "one_video"):
        kind = "audio" if scenario == "one_audio" else "video"
        chosen = [
            s for s in controller.intent.selections if controller.stream(s.reference).kind == kind
        ][-1]
        for item in controller.intent.selections:
            if controller.stream(item.reference).kind == kind and item != chosen:
                controller.edit_track(item.reference, include=False)
            if scenario == "one_audio" and controller.stream(item.reference).kind == "subtitle":
                controller.edit_track(item.reference, include=False)
    subtitle = tmp_path / "captions 日本語.srt"
    if scenario.endswith("srt"):
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:00,300\nSynthetic\n"
            if scenario != "bad_srt"
            else "malformed",
            encoding="utf-8",
        )
        controller.add_subtitles((str(subtitle),))
        settle(controller)
        if scenario == "bad_srt":
            assert controller.error and "INVALID_EXTERNAL_SRT" in controller.error
            assert not list(tmp_path.glob("output*"))
            return
        assert len(controller.intent.sources) == 2
    container = "mp4" if scenario in ("video_only", "mp4_srt", "incompatible") else "mkv"
    destination = tmp_path / f"output space 日本語.{container}"
    if scenario == "same_path":
        destination = asset.source.path
    if scenario == "existing":
        destination.write_bytes(b"existing unchanged")
    controller.change(container=container, destination=str(destination))
    if scenario == "extract":
        controller.change(
            mode="Extract",
            extraction_target=controller.intent.selections[0].reference,
            destination=str(tmp_path / "output 日本語.h264"),
        )
    controller.generate_plan()
    settle(controller)
    assert controller.plan is not None, controller.error
    if scenario in ("incompatible", "same_path", "existing"):
        assert not controller.plan.intrinsically_valid and not controller.can_execute
        assert controller.plan.arguments is None
        if scenario == "existing":
            assert destination.read_bytes() == b"existing unchanged"
        return
    assert controller.plan.intrinsically_valid, controller.plan.issues
    revision = controller.plan.revision
    controller.acknowledge(frozenset(controller.plan.pending_warnings), revision)
    settle(controller)
    assert controller.can_execute and controller.confirmed_revision is None
    controller.execute(revision)
    settle(controller)
    assert controller.result is not None and controller.result.published, controller.status
    assert controller.result.cleanup_complete and controller.result.state == "completed"
    assert controller.result.destination is not None
    output = controller.backend.inspect(str(controller.result.destination))
    if scenario in ("video_only", "silent_srt"):
        assert not any(s.kind == "audio" for s in output.streams)
    if scenario in ("avi_srt", "mp4_srt", "silent_srt"):
        assert output.streams[-1].codec == ("mov_text" if scenario == "mp4_srt" else "subrip")
    if scenario == "one_audio":
        assert sum(s.kind == "audio" for s in output.streams) == 1
    if scenario == "one_video":
        assert sum(s.kind == "video" for s in output.streams) == 1
    assert hashlib.sha256(asset.source.path.read_bytes()).hexdigest() == original
    assert not list(tmp_path.glob(".mediatrack-*"))


def test_cancel_through_desktop_controller(tmp_path: Path, planning_tools: tuple[str, str]) -> None:
    from mediatrack_forge.application.control import ExecutionControl
    from mediatrack_forge.application.execution import RemuxExecutionService
    from mediatrack_forge.domain.execution import ExecutionRequest, ExecutionResult

    from .conftest import generate

    class PacedBackend(DesktopBackend):
        def execute(self, request: ExecutionRequest, control: ExecutionControl) -> ExecutionResult:
            return RemuxExecutionService(runner=RealtimeRunner()).execute(request, control=control)

    path = tmp_path / "long.mp4"
    generate(
        planning_tools[0],
        [
            "-f",
            "lavfi",
            "-i",
            "color=s=64x48:r=10:d=8",
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-threads",
            "1",
        ],
        path,
    )
    original = path.read_bytes()
    controller = DesktopController(PacedBackend())
    controller.open_media(str(path))
    settle(controller)
    controller.change(destination=str(tmp_path / "out.mkv"))
    controller.generate_plan()
    settle(controller)
    assert controller.plan is not None
    revision = controller.plan.revision
    controller.acknowledge(frozenset(controller.plan.pending_warnings), revision)
    settle(controller)
    controller.execute(revision)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        controller.poll()
        if controller.progress is not None and controller.progress.processed_seconds is not None:
            break
        time.sleep(0.01)
    assert controller.worker.busy
    controller.cancel()
    settle(controller)
    assert controller.result is not None and controller.result.state == "cancelled"
    assert not controller.result.published and controller.result.cleanup_complete
    assert path.read_bytes() == original and not (tmp_path / "out.mkv").exists()

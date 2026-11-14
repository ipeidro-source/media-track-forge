"""Product execution E2E scenarios with real synthetic media and owned publication."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import ExecutionRequest, ProcessConfiguration, ProcessOutcome
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import OutputProfile, StreamReference, TrackSelection
from mediatrack_forge.infrastructure.ffmpeg_process import FFmpegProcessRunner
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.staging import PrivateStage, PrivateStagingStore

from .conftest import AUDIO, VIDEO, generate
from .test_planning_mux import planning_tools as planning_tools

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def publication_filesystem_evidence(tmp_path_factory: pytest.TempPathFactory) -> None:
    parent = tmp_path_factory.getbasetemp()
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_volume = kernel.GetVolumeInformationW
        get_volume.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        get_volume.restype = wintypes.BOOL
        name = ctypes.create_unicode_buffer(64)
        assert get_volume(parent.drive + "\\", None, 0, None, None, None, name, len(name))
        filesystem = name.value
    else:
        filesystem = subprocess.run(
            ["stat", "-f", "-c", "%T", str(parent)],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    print(f"Exclusive publication filesystem: {filesystem}; platform={os.name}")


def media(tmp_path: Path, tools: tuple[str, str], kind: str) -> MediaAsset:
    extension = "avi" if kind == "avi" else "mp4" if kind == "mp4" else "mkv"
    source = tmp_path / f"source space 日本語.{extension}"
    arguments = [*VIDEO, *AUDIO]
    if kind in ("subtitle", "multiaudio"):
        subtitle = tmp_path / "subtitle.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:00,300\nSynthetic\n", encoding="utf-8")
        arguments += ["-i", str(subtitle)]
    if kind == "metadata":
        metadata = tmp_path / "chapter.ffmeta"
        metadata.write_text(
            ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=400\ntitle=Opening\n",
            encoding="utf-8",
        )
        attachment = tmp_path / "note.txt"
        attachment.write_text("Synthetic attachment", encoding="utf-8")
        arguments += ["-f", "ffmetadata", "-i", str(metadata)]
    arguments += ["-map", "0:v:0", "-map", "1:a:0"]
    if kind == "multivideo":
        arguments += ["-map", "0:v:0"]
    if kind == "multiaudio":
        arguments += ["-map", "1:a:0"]
    if kind in ("multiaudio", "subtitle"):
        arguments += ["-map", "2:s:0", "-c:s", "srt"]
    arguments += [
        "-c:v",
        "mpeg4" if kind == "avi" else "libx264",
        "-threads",
        "1",
        "-c:a",
        "libmp3lame" if kind == "avi" else "aac",
    ]
    if kind != "avi":
        arguments += ["-preset", "ultrafast"]
    if kind == "multiaudio":
        arguments += [
            "-metadata:s:a:0",
            "title=First",
            "-metadata:s:a:1",
            "title=Chosen",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "0",
        ]
    if kind == "multivideo":
        arguments += [
            "-metadata:s:v:0",
            "title=First",
            "-metadata:s:v:1",
            "title=Chosen",
            "-disposition:v:0",
            "default",
            "-disposition:v:1",
            "0",
        ]
    if kind == "metadata":
        arguments += [
            "-map_chapters",
            "2",
            "-attach",
            str(attachment),
            "-metadata:s:t:0",
            "mimetype=text/plain",
            "-metadata:s:t:0",
            "filename=note.txt",
            "-metadata:s:a:0",
            "language=qzz",
            "-metadata:s:a:0",
            "title=日本語",
        ]
    generate(tools[0], arguments, source)
    return InspectionService(FFprobeAdapter(tools[1])).inspect(source)


def confirmed(
    source: MediaAsset,
    destination: Path,
    tools: tuple[str, str],
    selected: tuple[int, ...] | None = None,
) -> ExecutionRequest:
    selections = tuple(
        TrackSelection(
            StreamReference(source.source, s.index), selected is None or s.index in selected
        )
        for s in source.streams
    )
    output = OutputProfile(destination.suffix[1:], str(destination))
    planner = OperationPlanningService()
    reviewed = planner.plan((source,), selections, output)
    accepted = planner.plan(
        (source,),
        selections,
        output,
        acknowledged_warnings=frozenset(reviewed.pending_warnings),
        acknowledged_revision=reviewed.revision,
    )
    return ExecutionRequest(
        accepted,
        reviewed.revision,
        reviewed.revision,
        ProcessConfiguration(tools[0], tools[1], 20, 10),
    )


@pytest.mark.parametrize(
    "scenario", ["video_only", "multiaudio", "avi", "subtitle", "multivideo", "metadata"]
)
def test_e2e_01_02_03_04_05_10_14(
    tmp_path: Path, planning_tools: tuple[str, str], scenario: str
) -> None:
    source = media(tmp_path, planning_tools, "mp4" if scenario == "video_only" else scenario)
    destination = tmp_path / (
        "final space 日本語.mp4"
        if scenario in ("video_only", "subtitle")
        else "final space 日本語.mkv"
    )
    selected: tuple[int, ...] | None = None
    if scenario == "video_only":
        selected = (0,)
    elif scenario == "multiaudio":
        selected = (0, 2)
    elif scenario == "multivideo":
        selected = (2,)
    before = hashlib.sha256(source.source.path.read_bytes()).digest()
    execution_request = confirmed(source, destination, planning_tools, selected)
    result = RemuxExecutionService().execute(execution_request)
    assert result.state == "completed", (result.diagnostics, result.validation)
    assert result.published and result.cleanup_complete and result.validation is not None
    assert result.validation.passed and result.validation.observed is not None
    observed = result.validation.observed
    expected = execution_request.plan.included
    assert [(s.kind, s.codec) for s in observed.streams] == [
        (s.source_stream.kind, s.target_codec) for s in expected
    ]
    assert destination.exists() and not list(tmp_path.glob(".mediatrack-*"))
    assert hashlib.sha256(source.source.path.read_bytes()).digest() == before
    assert (
        InspectionService(FFprobeAdapter(planning_tools[1])).inspect(source.source.path).source
        == source.source
    )
    assert (
        result.history.index("validating")
        < result.history.index("publishing")
        < result.history.index("completed")
    )
    if scenario in ("video_only", "avi"):

        def packets(path: Path) -> list[str]:
            probe = subprocess.run(
                [
                    planning_tools[1],
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_packets",
                    "-show_data_hash",
                    "sha256",
                    "-show_entries",
                    "packet=data_hash",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return [str(item["data_hash"]) for item in json.loads(probe.stdout)["packets"]]

        assert packets(source.source.path) == packets(destination)
    if scenario == "multiaudio":
        assert observed.streams[1].title == "Chosen"
    if scenario == "multivideo":
        assert observed.streams[0].title == "Chosen"


@pytest.mark.parametrize("scenario", ["incompatible", "same_path", "existing"])
def test_e2e_06_07_08_no_execution(
    tmp_path: Path, planning_tools: tuple[str, str], scenario: str
) -> None:
    source = media(tmp_path, planning_tools, "avi" if scenario == "incompatible" else "mp4")
    destination = source.source.path if scenario == "same_path" else tmp_path / "out.mp4"
    if scenario == "existing":
        destination.write_bytes(b"competitor")
    before = source.source.path.read_bytes()
    runner = Mock()
    result = RemuxExecutionService(runner=runner).execute(
        confirmed(source, destination, planning_tools)
    )
    assert result.state == "failed" and not result.published
    runner.run.assert_not_called()
    assert source.source.path.read_bytes() == before and not list(tmp_path.glob(".mediatrack-*"))
    if scenario == "existing":
        assert destination.read_bytes() == b"competitor"


def test_e2e_09_last_moment_exclusive_publication(
    tmp_path: Path, planning_tools: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = media(tmp_path, planning_tools, "mp4")
    destination = tmp_path / "out.mp4"
    original_allocate = PrivateStagingStore.allocate

    def allocate(store: PrivateStagingStore, target: Path) -> PrivateStage:
        stage = original_allocate(store, target)
        publish = stage.publish

        def competing(path: Path) -> None:
            path.write_bytes(b"competitor")
            publish(path)

        monkeypatch.setattr(stage, "publish", competing)
        return stage

    monkeypatch.setattr(PrivateStagingStore, "allocate", allocate)
    result = RemuxExecutionService().execute(confirmed(source, destination, planning_tools))
    assert result.diagnostics[0].code == "DESTINATION_COLLISION"
    assert destination.read_bytes() == b"competitor" and result.cleanup_complete
    assert not list(tmp_path.glob(".mediatrack-*"))


@pytest.mark.parametrize("scenario", ["failure", "timeout", "validation"])
def test_e2e_11_12_13_failure_timeout_validation(
    tmp_path: Path, planning_tools: tuple[str, str], scenario: str
) -> None:
    source = media(tmp_path, planning_tools, "mp4")
    destination = tmp_path / "out.mp4"
    execution_request = confirmed(source, destination, planning_tools)
    before = source.source.path.read_bytes()

    class InjectedRunner:
        def run(self, arguments: tuple[str, ...], timeout_seconds: float) -> ProcessOutcome:
            if scenario == "timeout":
                return FFmpegProcessRunner().run(
                    (sys.executable, "-c", "import time;time.sleep(60)"), 0.2
                )
            Path(arguments[-1]).write_bytes(b"incorrect staged media")
            return (
                ProcessOutcome(1, "FFMPEG_FAILED") if scenario == "failure" else ProcessOutcome(0)
            )

    result = RemuxExecutionService(runner=InjectedRunner()).execute(execution_request)
    expected = {
        "failure": "FFMPEG_FAILED",
        "timeout": "PROCESS_TIMEOUT",
        "validation": "OUTPUT_VALIDATION_FAILED",
    }
    assert result.diagnostics[0].code == expected[scenario]
    assert not destination.exists() and result.cleanup_complete
    assert not list(tmp_path.glob(".mediatrack-*")) and source.source.path.read_bytes() == before

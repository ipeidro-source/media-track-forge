"""Real compatibility evidence; FFmpeg execution exists strictly in the test harness."""

import hashlib
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.compatibility import COPY_CODECS
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import (
    MetadataIntent,
    OutputProfile,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter

from .conftest import AUDIO, VIDEO, generate

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def planning_tools(media_tools: tuple[str, str]) -> tuple[str, str]:
    result = subprocess.run(
        [media_tools[0], "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    for encoder in ("libx264", "libx265", "libmp3lame", "mov_text"):
        assert re.search(rf"\s{encoder}\s", result.stdout), (
            f"Required fixture encoder missing: {encoder}"
        )
    return media_tools


def inspect(path: Path, tools: tuple[str, str]) -> MediaAsset:
    return InspectionService(FFprobeAdapter(tools[1])).inspect(path)


def execute_test_plan(
    source: MediaAsset,
    destination: Path,
    tools: tuple[str, str],
    selections: tuple[TrackSelection, ...] | None = None,
    *,
    preserve_chapters: bool = True,
) -> MediaAsset:
    """Regenerate with explicitly acknowledged test warnings; no product runner exists."""
    before = hashlib.sha256(source.source.path.read_bytes()).digest()
    requested = (
        selections
        if selections is not None
        else tuple(TrackSelection(StreamReference(source.source, s.index)) for s in source.streams)
    )
    service = OperationPlanningService()
    output = OutputProfile(destination.suffix[1:], str(destination))
    plan = service.plan((source,), requested, output, preserve_chapters=preserve_chapters)
    assert plan.intrinsically_valid, plan.issues
    plan = service.plan(
        (source,),
        requested,
        output,
        preserve_chapters=preserve_chapters,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    assert plan.execution_allowed and plan.arguments is not None
    assert [plan.arguments[i + 1] for i, arg in enumerate(plan.arguments) if arg == "-map"] == [
        f"0:{item.reference.index}" for item in plan.included
    ]
    for item in plan.included:
        value = plan.arguments[plan.arguments.index(f"-c:{item.output_index}") + 1]
        assert value == ("mov_text" if item.action == "convert_subtitle" else "copy")
        if item.source_stream.kind in ("video", "audio"):
            assert value == "copy"
    # This is the only execution site: a temporary integration-test output, not application code.
    result = subprocess.run([tools[0], *plan.arguments[1:]], capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr[:2000].decode("utf-8", errors="replace")
    observed = inspect(destination, tools)
    assert [s.kind for s in observed.streams] == [s.source_stream.kind for s in plan.included]
    assert [s.codec for s in observed.streams] == [s.target_codec for s in plan.included]
    assert [s.index for s in observed.streams] == list(range(len(plan.included)))
    assert hashlib.sha256(source.source.path.read_bytes()).digest() == before
    assert inspect(source.source.path, tools).source == source.source
    return observed


CASES = [
    ("h264", "aac", "mp4"),
    ("h264", "aac", "mkv"),
    ("hevc", "aac", "mp4"),
    ("hevc", "aac", "mkv"),
    ("h264", "mp3", "mp4"),
    ("h264", "mp3", "mkv"),
    ("mpeg4", "mp3", "mkv"),
]


@pytest.mark.parametrize("video,audio,target", CASES)
def test_enabled_video_audio_copy_matrix(
    tmp_path: Path, planning_tools: tuple[str, str], video: str, audio: str, target: str
) -> None:
    source_path = tmp_path / ("source.avi" if video == "mpeg4" else "source.mkv")
    encoder = {"h264": "libx264", "hevc": "libx265", "mpeg4": "mpeg4"}[video]
    args = [
        *VIDEO,
        *AUDIO,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        encoder,
        "-threads",
        "1",
        "-c:a",
        "libmp3lame" if audio == "mp3" else "aac",
    ]
    if video in ("h264", "hevc"):
        args += ["-preset", "ultrafast"]
    if video == "hevc":
        args += ["-x265-params", "pools=1:frame-threads=1:log-level=error"]
    generate(planning_tools[0], args, source_path)
    source = inspect(source_path, planning_tools)
    assert [s.codec for s in source.streams] == [video, audio]
    if video == "mpeg4":
        blocked = OperationPlanningService().plan(
            (source,),
            tuple(TrackSelection(StreamReference(source.source, s.index)) for s in source.streams),
            OutputProfile("mp4", str(tmp_path / "blocked.mp4")),
        )
        assert any(issue.code == "UNSUPPORTED_CODEC_FOR_CONTAINER" for issue in blocked.issues)
        assert blocked.arguments is None and not (tmp_path / "blocked.mp4").exists()
    execute_test_plan(source, tmp_path / f"copy.{target}", planning_tools)


@pytest.mark.parametrize(
    "codec,target", [("subrip", "mkv"), ("subrip", "mp4"), ("mov_text", "mp4")]
)
def test_enabled_subtitle_matrix(
    tmp_path: Path, planning_tools: tuple[str, str], codec: str, target: str
) -> None:
    subtitle = tmp_path / "synthetic.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,300\nSubtitle\n", encoding="utf-8")
    path = tmp_path / ("source.mp4" if codec == "mov_text" else "source.mkv")
    generate(
        planning_tools[0],
        [
            *VIDEO,
            "-i",
            str(subtitle),
            "-map",
            "0:v:0",
            "-map",
            "1:s:0",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:s",
            "mov_text" if codec == "mov_text" else "srt",
            "-metadata:s:s:0",
            "language=eng",
            "-disposition:s:0",
            "forced",
        ],
        path,
    )
    source = inspect(path, planning_tools)
    observed = execute_test_plan(source, tmp_path / f"subtitle.{target}", planning_tools)
    assert observed.streams[1].codec == ("subrip" if target == "mkv" else "mov_text")
    if target == "mkv":
        assert dict(observed.streams[1].disposition)["forced"] == 1


def test_mkv_chapters_attachment_and_metadata(
    tmp_path: Path, planning_tools: tuple[str, str]
) -> None:
    attachment = tmp_path / "note.txt"
    attachment.write_text("Synthetic attachment", encoding="utf-8")
    chapters = tmp_path / "chapter.ffmeta"
    chapters.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=400\ntitle=Opening\n",
        encoding="utf-8",
    )
    path = tmp_path / "source.mkv"
    generate(
        planning_tools[0],
        [
            *VIDEO,
            *AUDIO,
            "-f",
            "ffmetadata",
            "-i",
            str(chapters),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "1:a:0",
            "-map_chapters",
            "2",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            "-attach",
            str(attachment),
            "-metadata:s:t:0",
            "mimetype=text/plain",
            "-metadata:s:a:0",
            "language=und",
            "-metadata:s:a:0",
            "title=Original",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "0",
        ],
        path,
    )
    source = inspect(path, planning_tools)
    selections = tuple(
        TrackSelection(StreamReference(source.source, s.index)) for s in source.streams
    )
    selections = (
        selections[0],
        replace(selections[2], metadata=MetadataIntent("qzz", "日本語", True)),
        replace(selections[1], metadata=MetadataIntent(default=False)),
        selections[3],
    )
    observed = execute_test_plan(source, tmp_path / "metadata.mkv", planning_tools, selections)
    assert [s.title for s in observed.streams[1:3]] == ["日本語", "Original"]
    assert [s.language for s in observed.streams[1:3]] == ["qzz", source.streams[1].language]
    assert [dict(s.disposition)["default"] for s in observed.streams[1:3]] == [1, 0]
    assert dict(observed.streams[3].tags)["filename"] == dict(source.streams[3].tags)["filename"]
    assert dict(observed.streams[3].tags)["mimetype"] == "text/plain"
    assert len(observed.chapters) == 1 and observed.chapters[0].title == "Opening"
    # FFmpeg 6.1 shifts this AAC/H.264 fixture by approximately one AAC frame.
    # The plan discloses this uncertainty; this bound is fixture evidence, not a
    # general-purpose output-validation policy.
    assert observed.chapters[0].start_seconds == pytest.approx(
        source.chapters[0].start_seconds, abs=0.05
    )
    assert observed.chapters[0].end_seconds == pytest.approx(
        source.chapters[0].end_seconds, abs=0.05
    )


@pytest.mark.parametrize("target", ["mkv", "mp4"])
def test_multiple_video_and_video_only(
    tmp_path: Path, planning_tools: tuple[str, str], target: str
) -> None:
    path = tmp_path / "two-video.mkv"
    generate(
        planning_tools[0],
        [
            *VIDEO,
            "-map",
            "0:v:0",
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-disposition:v:0",
            "default",
            "-disposition:v:1",
            "0",
        ],
        path,
    )
    source = inspect(path, planning_tools)
    selections = tuple(
        TrackSelection(StreamReference(source.source, s.index)) for s in reversed(source.streams)
    )
    execute_test_plan(source, tmp_path / f"multiple.{target}", planning_tools, selections)
    # AC-01 planning: retaining only video is a valid main-video output.
    execute_test_plan(
        source,
        tmp_path / f"single.{target}",
        planning_tools,
        (selections[0], replace(selections[1], include=False)),
    )


def test_allowlist_has_an_executed_matrix_case() -> None:
    covered = {
        (target, kind, codec)
        for video, audio, target in CASES
        for kind, codec in (("video", video), ("audio", audio))
    }
    covered |= {("mkv", "subtitle", "subrip"), ("mp4", "subtitle", "mov_text")}
    assert {
        (target, kind, codec)
        for target, kinds in COPY_CODECS.items()
        for kind, codecs in kinds.items()
        for codec in codecs
    } == covered

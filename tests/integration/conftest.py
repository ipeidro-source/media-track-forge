"""Required external tools and explicit synthetic fixture generation."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def media_tools() -> tuple[str, str]:
    tools = [shutil.which(name) for name in ("ffmpeg", "ffprobe")]
    if any(tool is None for tool in tools):
        pytest.fail(
            "Integration tests require external FFmpeg and ffprobe on PATH; none are skipped."
        )
    ffmpeg, ffprobe = tools
    assert ffmpeg is not None and ffprobe is not None
    for tool in (ffmpeg, ffprobe):
        version = subprocess.run(
            [tool, "-version"], capture_output=True, text=True, check=True, timeout=10
        )
        print(version.stdout.splitlines()[0])
    encoders = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout
    for encoder in ("mpeg4", "aac", "pcm_s16le", "ffv1", "srt"):
        assert re.search(rf"\s{encoder}\s", encoders), (
            f"Required synthetic encoder missing: {encoder}"
        )
    return ffmpeg, ffprobe


def generate(ffmpeg: str, arguments: list[str], destination: Path) -> None:
    """Generate a tiny local fixture, never overwrite an existing path."""
    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-n",
            *arguments,
            str(destination),
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr[:2000].decode("utf-8", errors="replace")


VIDEO = ["-f", "lavfi", "-i", "color=c=blue:s=64x48:r=10:d=0.4"]
AUDIO = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.4"]


@pytest.fixture
def multitrack_mkv(tmp_path: Path, media_tools: tuple[str, str]) -> Path:
    subtitle = tmp_path / "subtitle.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,300\nSynthetic subtitle\n", encoding="utf-8")
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("Synthetic attachment", encoding="utf-8")
    metadata = tmp_path / "chapters.ffmeta"
    metadata.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=400\ntitle=Opening\n",
        encoding="utf-8",
    )
    destination = tmp_path / "múltiples 日本語 tracks.mkv"
    generate(
        media_tools[0],
        [
            *VIDEO,
            *AUDIO,
            "-i",
            str(subtitle),
            "-f",
            "ffmetadata",
            "-i",
            str(metadata),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "1:a:0",
            "-map",
            "2:s:0",
            "-map_chapters",
            "3",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            "-c:s",
            "srt",
            "-attach",
            str(attachment),
            "-metadata:s:t:0",
            "mimetype=text/plain",
            "-metadata",
            "title=日本語 fixture",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:0",
            "title=Main",
            "-metadata:s:a:1",
            "language=qzz",
            "-metadata:s:a:1",
            "title=Other",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "0",
        ],
        destination,
    )
    return destination

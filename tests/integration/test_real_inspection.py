"""Real, read-only ffprobe inspection of short locally generated media."""

import hashlib
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from mediatrack_forge.application.inspection import (
    InspectionService,
    ProbeFailedError,
    snapshot_source,
)
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.ui.inspection_json import inspection_document

from .conftest import AUDIO, VIDEO, generate

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "extension,audio,audio_codec,format_name",
    [
        ("mp4", True, "aac", "mp4"),
        ("mp4", False, "aac", "mp4"),
        ("avi", True, "pcm_s16le", "avi"),
        ("mov", True, "pcm_s16le", "mov"),
    ],
)
def test_local_containers(
    tmp_path: Path,
    media_tools: tuple[str, str],
    extension: str,
    audio: bool,
    audio_codec: str,
    format_name: str,
) -> None:
    path = tmp_path / f"synthetic Unicode 日本語 with spaces.{extension}"
    arguments = [*VIDEO, *(AUDIO if audio else []), "-map", "0:v:0", "-c:v", "mpeg4"]
    if audio:
        arguments += ["-map", "1:a:0", "-c:a", audio_codec]
    generate(media_tools[0], arguments, path)
    identity = snapshot_source(path)
    digest = hashlib.sha256(path.read_bytes()).digest()
    asset = InspectionService(FFprobeAdapter(media_tools[1])).inspect(path)
    assert snapshot_source(path) == identity == asset.source
    assert hashlib.sha256(path.read_bytes()).digest() == digest
    assert [s.kind for s in asset.streams] == (["video", "audio"] if audio else ["video"])
    assert [s.index for s in asset.streams] == list(range(len(asset.streams)))
    assert asset.streams[0].codec == "mpeg4"
    assert asset.streams[0].properties.width == 64
    assert asset.streams[0].properties.height == 48
    if audio:
        assert asset.streams[1].codec == audio_codec
        assert asset.streams[1].properties.sample_rate_hz == 48000
    assert asset.format.name is not None and format_name in asset.format.name.split(",")
    assert asset.format.duration_seconds is not None and 0 < asset.format.duration_seconds < 1


@pytest.mark.parametrize("entry_point", ["module", "console"])
def test_multitrack_metadata_and_cli(
    multitrack_mkv: Path,
    media_tools: tuple[str, str],
    tmp_path: Path,
    entry_point: str,
) -> None:
    before = multitrack_mkv.read_bytes()
    asset = InspectionService(FFprobeAdapter()).inspect(multitrack_mkv)
    assert [s.kind for s in asset.streams] == ["video", "audio", "audio", "subtitle", "attachment"]
    assert [s.index for s in asset.streams] == [0, 1, 2, 3, 4]
    assert [s.codec for s in asset.streams[:4]] == ["ffv1", "pcm_s16le", "pcm_s16le", "subrip"]
    assert [s.language for s in asset.streams[1:3]] == ["eng", "qzz"]
    assert [s.title for s in asset.streams[1:3]] == ["Main", "Other"]
    assert dict(asset.streams[1].disposition)["default"] == 1
    assert dict(asset.streams[2].disposition)["default"] == 0
    assert dict(asset.format.tags)["title"] == "日本語 fixture"
    assert len(asset.chapters) == 1
    assert asset.chapters[0].title == "Opening"
    assert asset.chapters[0].start_seconds == 0
    assert asset.chapters[0].end_seconds == pytest.approx(0.4)
    prefix = [sys.executable, "-m", "mediatrack_forge"]
    if entry_point == "console":
        executable = "mediatrack-forge.exe" if os.name == "nt" else "mediatrack-forge"
        prefix = [str(Path(sysconfig.get_path("scripts")) / executable)]
    result = subprocess.run(
        [
            *prefix,
            "inspect",
            str(multitrack_mkv),
            "--ffprobe",
            media_tools[1],
            "--timeout-seconds",
            "10",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    assert result.stderr == ""
    assert json.loads(result.stdout) == inspection_document(asset)
    assert multitrack_mkv.read_bytes() == before


def test_invalid_media_is_controlled(tmp_path: Path, media_tools: tuple[str, str]) -> None:
    path = tmp_path / "invalid.mp4"
    path.write_bytes(b"not a media file")
    with pytest.raises(ProbeFailedError):
        InspectionService(FFprobeAdapter(media_tools[1])).inspect(path)
    assert path.read_bytes() == b"not a media file"


def test_remote_reference_is_blocked(tmp_path: Path, media_tools: tuple[str, str]) -> None:
    playlist = tmp_path / "blocked.m3u8"
    playlist.write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXTINF:1,\nhttp://127.0.0.1:9/blocked.ts\n#EXT-X-ENDLIST\n",
        encoding="ascii",
    )
    with pytest.raises(ProbeFailedError):
        InspectionService(FFprobeAdapter(media_tools[1])).inspect(playlist)
    # Verify the real binary rejects the protocol before attempting a connection.
    result = subprocess.run(
        [
            media_tools[1],
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-of",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-i",
            str(playlist),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "not on whitelist" in result.stderr

"""Synthetic ffprobe responses and application/CLI contracts without media tools."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock

import pytest

from mediatrack_forge.application.inspection import (
    ExecutableError,
    InspectionError,
    InspectionService,
    InvalidInputError,
    ProbeFailedError,
    ProbeResponseError,
    ProbeTimeoutError,
    snapshot_source,
)
from mediatrack_forge.domain.media import MediaSource
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.ffprobe_json import parse_response
from mediatrack_forge.ui.cli import main
from mediatrack_forge.ui.inspection_json import inspection_document, serialize_inspection


@pytest.fixture
def source(tmp_path: Path) -> MediaSource:
    path = tmp_path / "source with spaces.mkv"
    path.write_bytes(b"synthetic source")
    return snapshot_source(path)


def response(streams: list[dict[str, object]]) -> bytes:
    return json.dumps({"format": {}, "streams": streams}).encode()


@pytest.mark.parametrize(
    "kinds",
    [
        ["video"],
        ["video", "audio"],
        ["video", "audio", "audio"],
        ["video", "video"],
        ["video", "audio", "subtitle"],
        ["attachment", "data", "future-type"],
        [],
    ],
)
def test_stream_kinds_order_and_original_indices(source: MediaSource, kinds: list[str]) -> None:
    indices = [9, 2, 17][: len(kinds)]
    asset = parse_response(
        response(
            [
                {"index": index, "codec_type": kind}
                for index, kind in zip(indices, kinds, strict=True)
            ]
        ),
        source,
    )
    assert [s.index for s in asset.streams] == indices
    assert [s.kind for s in asset.streams] == [
        kind if kind != "future-type" else "unknown" for kind in kinds
    ]
    for stream in asset.streams:
        assert stream.language is stream.title is stream.codec is None
        assert stream.duration_seconds is None
        assert stream.disposition == ()
    assert asset.chapters == ()


@pytest.mark.parametrize("language", ["eng", "und", "qzz", "日本語"])
def test_language_and_unicode_preserved(source: MediaSource, language: str) -> None:
    asset = parse_response(
        response([{"index": 8, "tags": {"language": language, "title": "Español 日本語"}}]), source
    )
    assert asset.streams[0].language == language
    assert asset.streams[0].title == "Español 日本語"


def test_complete_stable_json_contract(source: MediaSource) -> None:
    payload = {
        "format": {
            "format_name": "matroska,webm",
            "format_long_name": "Matroska / WebM",
            "duration": "1.250",
            "bit_rate": "1024",
            "tags": {"title": "日本語"},
            "future": {"ignored": True},
        },
        "streams": [
            {
                "index": 7,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 64,
                "height": 48,
                "pix_fmt": "yuv420p",
                "codec_long_name": "H.264",
                "profile": "High",
                "time_base": "1/1000",
                "avg_frame_rate": "25/1",
                "duration": "1.25",
                "tags": {"language": "und", "title": "日本語"},
                "disposition": {"default": 1, "forced": 0, "future_flag": 1},
            },
            {
                "index": 3,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "channel_layout": "stereo",
                "bit_rate": "96000",
            },
        ],
        "chapters": [
            {"id": 4, "start_time": "0", "end_time": "1.25", "tags": {"title": "Opening"}}
        ],
    }
    asset = parse_response(json.dumps(payload).encode(), source)
    empty_properties: dict[str, object] = {
        "width": None,
        "height": None,
        "channels": None,
        "sample_rate_hz": None,
        "channel_layout": None,
        "pixel_format": None,
        "bit_rate_bps": None,
        "codec_long_name": None,
        "profile": None,
        "time_base": None,
        "average_frame_rate": None,
    }
    expected = {
        "schema_version": 1,
        "source": {
            "path": str(source.path),
            "size_bytes": source.size_bytes,
            "modified_time_ns": source.modified_time_ns,
        },
        "format": {
            "name": "matroska,webm",
            "long_name": "Matroska / WebM",
            "duration_seconds": 1.25,
            "bit_rate_bps": 1024,
            "tags": {"title": "日本語"},
        },
        "streams": [
            {
                "index": 7,
                "kind": "video",
                "codec": "h264",
                "language": "und",
                "title": "日本語",
                "disposition": {"default": 1, "forced": 0, "future_flag": 1},
                "duration_seconds": 1.25,
                "tags": {"language": "und", "title": "日本語"},
                "properties": empty_properties
                | {
                    "width": 64,
                    "height": 48,
                    "pixel_format": "yuv420p",
                    "codec_long_name": "H.264",
                    "profile": "High",
                    "time_base": "1/1000",
                    "average_frame_rate": "25/1",
                },
            },
            {
                "index": 3,
                "kind": "audio",
                "codec": "aac",
                "language": None,
                "title": None,
                "disposition": {},
                "duration_seconds": None,
                "tags": {},
                "properties": empty_properties
                | {
                    "channels": 2,
                    "sample_rate_hz": 48000,
                    "channel_layout": "stereo",
                    "bit_rate_bps": 96000,
                },
            },
        ],
        "chapters": [
            {
                "id": 4,
                "start_seconds": 0.0,
                "end_seconds": 1.25,
                "title": "Opening",
                "tags": {"title": "Opening"},
            }
        ],
    }
    assert inspection_document(asset) == expected
    assert json.loads(serialize_inspection(asset)) == expected
    assert serialize_inspection(asset) == serialize_inspection(asset)
    assert serialize_inspection(asset).isascii()
    with pytest.raises(FrozenInstanceError):
        asset.streams[0].__setattr__("index", 99)
    # Editing presentation dictionaries cannot mutate the domain snapshot.
    document = inspection_document(asset)
    document["streams"] = []
    assert len(asset.streams) == 2


@pytest.mark.parametrize("value", ["N/A", "nan", "inf", "1e9999", None, {}, True])
def test_unavailable_optional_numbers_are_null(source: MediaSource, value: object) -> None:
    payload = {"format": {"duration": value, "bit_rate": value}, "streams": []}
    asset = parse_response(json.dumps(payload).encode(), source)
    assert asset.format.duration_seconds is None
    assert asset.format.bit_rate_bps is None


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"\xff",
        b"[]",
        b"{}",
        b'{"format": {}}',
        b'{"streams": []}',
        b'{"format": {}, "streams": {}}',
        response([{}]),
        response([{"index": -1}]),
        response([{"index": True}]),
        response([{"index": "1"}]),
        response([{"index": 0}, {"index": 0}]),
        response([{"index": 0, "disposition": {"default": "yes"}}]),
        b'{"format": {}, "streams": [], "chapters": [{}]}',
    ],
)
def test_malformed_or_unusable_response(source: MediaSource, payload: bytes) -> None:
    with pytest.raises(ProbeResponseError):
        parse_response(payload, source)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "http://example.invalid/a.mp4",
        "file:movie.mp4",
        "pipe:0",
        "\\\\server\\share\\file.mkv",
        "//server/file",
        "\x00",
    ],
)
def test_nonlocal_input_is_rejected(path: str) -> None:
    with pytest.raises(InvalidInputError):
        snapshot_source(path)


def test_missing_file_and_directory_are_rejected(tmp_path: Path) -> None:
    for path in (tmp_path, tmp_path / "missing"):
        with pytest.raises(InvalidInputError):
            snapshot_source(path)


def test_adapter_safe_arguments(source: MediaSource, monkeypatch: pytest.MonkeyPatch) -> None:
    which = Mock(return_value="C:/tools with spaces/ffprobe.exe")
    run = Mock(return_value=response([]))
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.shutil.which", which)
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.run_bounded", run)
    FFprobeAdapter("chosen ffprobe.exe").inspect(source, timeout_seconds=7)
    which.assert_called_once_with("chosen ffprobe.exe")
    run.assert_called_once_with(
        [
            "C:/tools with spaces/ffprobe.exe",
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
            str(source.path),
        ],
        7,
    )


def test_missing_executable(source: MediaSource, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.shutil.which", lambda _: None)
    with pytest.raises(ExecutableError):
        FFprobeAdapter().inspect(source)


def test_invalid_executable_path_is_controlled(
    source: MediaSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.ffprobe.shutil.which", Mock(side_effect=ValueError)
    )
    with pytest.raises(ExecutableError):
        FFprobeAdapter("invalid").inspect(source)


def test_path_discovery_and_default_timeout(
    source: MediaSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    which = Mock(return_value="ffprobe.exe")
    run = Mock(return_value=response([]))
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.shutil.which", which)
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.run_bounded", run)
    InspectionService(FFprobeAdapter()).inspect(source.path)
    which.assert_called_once_with("ffprobe")
    assert run.call_args.args[1] == 30.0


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf")])
def test_service_rejects_bad_timeout_before_probing(source: MediaSource, timeout: float) -> None:
    probe = Mock()
    with pytest.raises(InvalidInputError):
        InspectionService(probe).inspect(source.path, timeout_seconds=timeout)
    probe.inspect.assert_not_called()


def test_unreadable_path(source: MediaSource, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "open", Mock(side_effect=PermissionError))
    with pytest.raises(InvalidInputError):
        snapshot_source(source.path)


def test_source_disappears_during_inspection(source: MediaSource) -> None:
    probe = Mock()

    def remove(source: MediaSource, *, timeout_seconds: float) -> object:
        source.path.unlink()
        return parse_response(response([]), source)

    probe.inspect.side_effect = remove
    with pytest.raises(ProbeFailedError, match="unavailable"):
        InspectionService(probe).inspect(source.path)


def test_source_changes_are_rejected(source: MediaSource) -> None:
    probe = Mock()

    def modify(source: MediaSource, *, timeout_seconds: float) -> object:
        source.path.write_bytes(b"changed")
        return parse_response(response([]), source)

    probe.inspect.side_effect = modify
    with pytest.raises(ProbeFailedError, match="changed"):
        InspectionService(probe).inspect(source.path)


@pytest.mark.parametrize(
    "error",
    [InvalidInputError, ExecutableError, ProbeFailedError, ProbeTimeoutError, ProbeResponseError],
)
def test_cli_error_codes_and_empty_stdout(
    error: type[InspectionError],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: MediaSource,
) -> None:
    monkeypatch.setattr(
        InspectionService, "inspect", Mock(side_effect=error("Actionable failure."))
    )
    assert main(["inspect", str(source.path)]) == error.exit_code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: Actionable failure.\n"


def test_cli_success_is_json_only(
    source: MediaSource,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asset = parse_response(response([{"index": 12}]), source)
    inspect = Mock(return_value=asset)
    monkeypatch.setattr(InspectionService, "inspect", inspect)
    assert (
        main(["inspect", str(source.path), "--ffprobe", "custom.exe", "--timeout-seconds", "2"])
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == inspection_document(asset)
    inspect.assert_called_once_with(str(source.path), timeout_seconds=2.0)


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "text"])
def test_cli_invalid_timeout(timeout: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["inspect", "file.mkv", "--timeout-seconds", timeout])
    assert exc.value.code == 2
    assert capsys.readouterr().out == ""

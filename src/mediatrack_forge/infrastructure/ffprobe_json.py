"""Normalize a bounded ffprobe response into the inspection domain."""

import json
import math
from typing import cast

from mediatrack_forge.application.inspection import ProbeResponseError
from mediatrack_forge.domain.media import (
    Chapter,
    MediaAsset,
    MediaFormat,
    MediaSource,
    Stream,
    StreamKind,
    StreamProperties,
    Tags,
)


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ProbeResponseError("ffprobe returned an invalid metadata object.")
    return cast(dict[str, object], value)


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ProbeResponseError("ffprobe returned an invalid stream or chapter collection.")
    return cast(list[object], value)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    return None


def _nonnegative_integer(value: object) -> int | None:
    number = _integer(value)
    return number if number is not None and number >= 0 else None


def _seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _tags(value: object) -> Tags:
    return tuple(sorted((key, val) for key, val in _object(value).items() if isinstance(val, str)))


def _stream(value: object) -> Stream:
    data = _object(value)
    index = data.get("index")
    if type(index) is not int or index < 0:
        raise ProbeResponseError("ffprobe returned a stream without a valid original index.")
    kind = data.get("codec_type")
    if kind not in ("video", "audio", "subtitle", "attachment", "data"):
        kind = "unknown"
    tags = _tags(data.get("tags", {}))
    dispositions = _object(data.get("disposition", {}))
    if any(type(v) is not int or v not in (0, 1) for v in dispositions.values()):
        raise ProbeResponseError("ffprobe returned invalid disposition flags.")
    properties = StreamProperties(
        width=_nonnegative_integer(data.get("width")),
        height=_nonnegative_integer(data.get("height")),
        channels=_nonnegative_integer(data.get("channels")),
        sample_rate_hz=_nonnegative_integer(data.get("sample_rate")),
        channel_layout=_text(data.get("channel_layout")),
        pixel_format=_text(data.get("pix_fmt")),
        bit_rate_bps=_nonnegative_integer(data.get("bit_rate")),
        codec_long_name=_text(data.get("codec_long_name")),
        profile=_text(data.get("profile")),
        time_base=_text(data.get("time_base")),
        average_frame_rate=_text(data.get("avg_frame_rate")),
    )
    return Stream(
        index=index,
        kind=cast(StreamKind, kind),
        codec=_text(data.get("codec_name")),
        language=dict(tags).get("language"),
        title=dict(tags).get("title"),
        disposition=tuple(sorted((k, cast(int, v)) for k, v in dispositions.items())),
        duration_seconds=_seconds(data.get("duration")),
        properties=properties,
        tags=tags,
    )


def _chapter(value: object) -> Chapter:
    data = _object(value)
    chapter_id = data.get("id")
    if type(chapter_id) is not int:
        raise ProbeResponseError("ffprobe returned a chapter without an integer ID.")
    tags = _tags(data.get("tags", {}))
    return Chapter(
        chapter_id,
        _seconds(data.get("start_time")),
        _seconds(data.get("end_time")),
        dict(tags).get("title"),
        tags,
    )


def parse_response(payload: bytes, source: MediaSource) -> MediaAsset:
    """Require format and streams, ignore unknown fields, and preserve source order."""
    try:
        data = _object(json.loads(payload.decode("utf-8")))
        fmt = _object(data.get("format"))
        streams = tuple(_stream(value) for value in _array(data.get("streams")))
        if len({stream.index for stream in streams}) != len(streams):
            raise ProbeResponseError("ffprobe returned duplicate stream indices.")
        chapters = tuple(_chapter(value) for value in _array(data.get("chapters", [])))
        return MediaAsset(
            source,
            MediaFormat(
                _text(fmt.get("format_name")),
                _text(fmt.get("format_long_name")),
                _seconds(fmt.get("duration")),
                _nonnegative_integer(fmt.get("bit_rate")),
                _tags(fmt.get("tags", {})),
            ),
            streams,
            chapters,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProbeResponseError(
            "ffprobe returned malformed JSON; check the executable and media."
        ) from exc

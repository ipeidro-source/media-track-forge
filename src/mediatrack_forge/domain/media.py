"""Immutable inspection snapshots, independent of process and presentation adapters."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

StreamKind = Literal["video", "audio", "subtitle", "attachment", "data", "unknown"]
Tags = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MediaSource:
    """Local source identity at inspection time; timestamps are nanoseconds."""

    path: Path
    size_bytes: int
    modified_time_ns: int


@dataclass(frozen=True)
class MediaFormat:
    name: str | None
    long_name: str | None
    duration_seconds: float | None
    bit_rate_bps: int | None
    tags: Tags


@dataclass(frozen=True)
class StreamProperties:
    """Optional technical values in pixels, Hz, bits/s and ffprobe rational notation."""

    width: int | None
    height: int | None
    channels: int | None
    sample_rate_hz: int | None
    channel_layout: str | None
    pixel_format: str | None
    bit_rate_bps: int | None
    codec_long_name: str | None
    profile: str | None
    time_base: str | None
    average_frame_rate: str | None


@dataclass(frozen=True)
class Stream:
    index: int
    kind: StreamKind
    codec: str | None
    language: str | None
    title: str | None
    disposition: tuple[tuple[str, int], ...]
    duration_seconds: float | None
    properties: StreamProperties
    tags: Tags


@dataclass(frozen=True)
class Chapter:
    id: int
    start_seconds: float | None
    end_seconds: float | None
    title: str | None
    tags: Tags


@dataclass(frozen=True)
class MediaAsset:
    source: MediaSource
    format: MediaFormat
    streams: tuple[Stream, ...]
    chapters: tuple[Chapter, ...]

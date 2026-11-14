"""Extraction-specific intent with the shared immutable execution-plan primitives."""

from dataclasses import dataclass

from mediatrack_forge.domain.planning import OperationPlan


@dataclass(frozen=True)
class ExtractionPlan(OperationPlan):
    extraction_version: int = 1
    bitstream_filters: tuple[str, ...] = ()


# Codec, source family, extension, muxer, filter. Separate from remux policy.
EXTRACTION_MATRIX = (
    ("h264", "mp4", "h264", "h264", "h264_mp4toannexb"),
    ("hevc", "mp4", "h265", "hevc", "hevc_mp4toannexb"),
    ("aac", "mp4", "aac", "adts", None),
    ("mp3", "avi", "mp3", "mp3", None),
    ("subrip", "matroska", "srt", "srt", None),
    ("mov_text", "mp4", "srt", "srt", None),
)

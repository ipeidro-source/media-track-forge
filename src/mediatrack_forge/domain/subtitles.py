"""Normalized, structurally validated subtitle cue evidence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str

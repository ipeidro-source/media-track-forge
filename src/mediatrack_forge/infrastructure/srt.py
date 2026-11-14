"""Bounded strict UTF-8 SRT structural validation, independent of ffprobe."""

import re
from pathlib import Path

from mediatrack_forge.application.inspection import snapshot_source
from mediatrack_forge.domain.execution import ExecutionFailure
from mediatrack_forge.domain.subtitles import SubtitleCue

MAX_SRT_BYTES = 8 * 1024 * 1024
MAX_CUES = 100_000
TIMESTAMP = re.compile(r"(\d{1,3}):([0-5]\d):([0-5]\d),(\d{3})")


def validate_srt(path: Path, *, require_suffix: bool = True) -> tuple[SubtitleCue, ...]:
    try:
        before = snapshot_source(path)
        if (
            require_suffix and path.suffix.lower() != ".srt"
        ) or not 0 < before.size_bytes <= MAX_SRT_BYTES:
            raise ValueError
        with path.open("rb") as file:
            data = file.read(MAX_SRT_BYTES + 1)
        if len(data) > MAX_SRT_BYTES:
            raise ValueError
        text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if "\x00" in text:
            raise ValueError
        cues: list[SubtitleCue] = []
        for block in re.split(r"\n[ \t]*\n", text.strip()):
            lines = block.splitlines()
            if lines and lines[0].strip().isdigit():
                lines = lines[1:]
            if len(lines) < 2 or len(cues) >= MAX_CUES:
                raise ValueError
            parts = re.split(r"[ \t]*-->[ \t]*", lines[0].strip())
            if len(parts) != 2:
                raise ValueError
            times = []
            for part in parts:
                match = TIMESTAMP.fullmatch(part)
                if match is None:
                    raise ValueError
                h, m, s, ms = map(int, match.groups())
                times.append(((h * 60 + m) * 60 + s) * 1000 + ms)
            content = "\n".join(lines[1:]).strip()
            if times[0] >= times[1] or not content:
                raise ValueError
            cues.append(SubtitleCue(times[0], times[1], content))
        if not cues or snapshot_source(path) != before:
            raise ValueError
        return tuple(cues)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ExecutionFailure("INVALID_EXTERNAL_SRT") from exc

"""Bounded independent text-packet evidence for SubRip and mov_text extraction."""

import json
import math
import os
import re
import shutil
from pathlib import Path

from mediatrack_forge.application.control import CancellationToken
from mediatrack_forge.domain.subtitles import SubtitleCue
from mediatrack_forge.infrastructure.ffprobe import run_bounded
from mediatrack_forge.infrastructure.srt import MAX_CUES


def subtitle_cues(
    path: Path,
    index: int,
    codec: str,
    executable: str | None,
    timeout: float,
    *,
    cancellation: CancellationToken | None = None,
) -> tuple[SubtitleCue, ...]:
    binary = shutil.which(executable or "ffprobe")
    if binary is None or (os.name == "nt" and Path(binary).suffix.lower() not in (".exe", ".com")):
        raise ValueError("Packet probe unavailable")
    arguments = [
        binary,
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-select_streams",
        str(index),
        "-show_packets",
        "-show_data",
        "-show_entries",
        "packet=pts_time,duration_time,data,size",
        "-of",
        "json",
        "-i",
        str(path),
    ]
    raw = (
        run_bounded(arguments, timeout, cancellation=cancellation)
        if cancellation is not None
        else run_bounded(arguments, timeout)
    )
    cues: list[SubtitleCue] = []
    for packet in json.loads(raw)["packets"]:
        # ffprobe hex dump has a fixed-width 39-character hex column, followed by ASCII.
        data = b"".join(
            bytes.fromhex(line.split(":", 1)[1][1:40])
            for line in packet["data"].splitlines()
            if ":" in line
        )
        if len(data) != int(packet["size"]):
            raise ValueError("Incomplete packet payload")
        if codec == "mov_text":
            if len(data) < 2:
                raise ValueError("Missing text length")
            length = int.from_bytes(data[:2], "big")
            if length > len(data) - 2:
                raise ValueError("Invalid text length")
            data = data[2 : 2 + length]
        elif codec != "subrip":
            raise ValueError("Unsupported subtitle packet")
        if not data and codec == "mov_text":
            # MP4 clear samples describe gaps rather than SRT cues.
            continue
        text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").strip()
        start = float(packet["pts_time"]) * 1000
        duration = float(packet["duration_time"]) * 1000
        if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0:
            raise ValueError("Unverifiable subtitle timing")
        if not text or len(cues) >= MAX_CUES:
            raise ValueError("Invalid subtitle text or cue limit")
        cues.append(SubtitleCue(round(start), round(start + duration), text))
    if not cues:
        raise ValueError("No subtitle cues")
    return tuple(cues)


def plain_text(text: str) -> str:
    """Compare text independently of the supported SRT presentation markup."""
    return re.sub(r"</?(?:b|i|u|font)(?:\s[^>]*)?>", "", text, flags=re.IGNORECASE)

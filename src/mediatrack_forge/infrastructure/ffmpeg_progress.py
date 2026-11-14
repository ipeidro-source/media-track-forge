"""Incremental bounded parser for FFmpeg key/value progress, never stderr text."""

import math


class ProgressParser:
    def __init__(self) -> None:
        self._line = bytearray()
        self.seconds: float | None = None

    def feed(self, data: bytes) -> None:
        for value in data:
            if value == 10:
                line = self._line.decode("ascii", errors="replace").strip()
                self._line.clear()
                key, _, text = line.partition("=")
                if key in ("out_time_us", "out_time_ms"):
                    try:
                        number = float(text) / 1_000_000  # Both keys use microseconds.
                        if math.isfinite(number) and number >= 0:
                            self.seconds = max(self.seconds or 0, number)
                    except ValueError:
                        pass
            else:
                if len(self._line) >= 4096:
                    raise ValueError("Progress line exceeded limit")
                self._line.append(value)

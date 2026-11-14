"""Per-operation cancellation and bounded, synchronous progress delivery."""

import math
import threading
from collections.abc import Callable

from mediatrack_forge.domain.execution import ExecutionFailure, ExecutionState
from mediatrack_forge.domain.execution import ProgressEvent as ProgressEvent


class CancellationToken:
    """Linearize cancellation requests against the short publication commitment."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._requested = threading.Event()
        self._committed = False

    def cancel(self) -> bool:
        with self._lock:
            if self._committed:
                return False
            self._requested.set()
            return True

    @property
    def requested(self) -> bool:
        return self._requested.is_set()

    def check(self) -> None:
        if self.requested:
            raise ExecutionFailure("PROCESS_CANCELLED")

    def publish(self, action: Callable[[], None]) -> None:
        with self._lock:
            self.check()
            action()
            self._committed = True


ProgressListener = Callable[[ProgressEvent], None]


class ExecutionControl:
    """One worker emits synchronously; listeners must return promptly, with no queue."""

    def __init__(
        self,
        cancellation: CancellationToken | None = None,
        listener: ProgressListener | None = None,
    ) -> None:
        self.cancellation = cancellation if cancellation is not None else CancellationToken()
        self.listener = listener
        self.expected_seconds: float | None = None
        self.callback_failed = False
        self._percent = 0.0

    def emit(self, phase: ExecutionState, seconds: float | None = None) -> None:
        if seconds is not None and (not math.isfinite(seconds) or seconds < 0):
            seconds = None
        duration = self.expected_seconds
        determinate = duration is not None and math.isfinite(duration) and duration > 0
        if determinate and seconds is not None and duration is not None:
            self._percent = max(self._percent, min(99.0, seconds / duration * 99.0))
        if phase == "completed":
            self._percent = 100.0
            determinate = True
        event = ProgressEvent(
            phase,
            determinate,
            self._percent if determinate else None,
            seconds,
            phase in ("completed", "failed", "timed_out", "cancelled"),
        )
        if self.listener is not None and not self.callback_failed:
            try:
                self.listener(event)
            except Exception:
                self.callback_failed = True

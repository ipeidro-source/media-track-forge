"""One background task, one discrete reply and one coalesced progress value; no Tk."""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.application.inspection import InspectionError
from mediatrack_forge.domain.execution import ExecutionFailure, ProgressEvent


@dataclass(frozen=True)
class WorkerReply:
    generation: int
    kind: str
    value: object = None
    error: str | None = None


class Worker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._reply: WorkerReply | None = None
        self._progress: ProgressEvent | None = None
        self.control: ExecutionControl | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def progress(self, event: ProgressEvent) -> None:
        with self._lock:
            self._progress = event

    def start(
        self,
        generation: int,
        kind: str,
        task: Callable[[], object],
        *,
        control: ExecutionControl | None = None,
    ) -> None:
        if self.busy:
            raise ValueError("Wait for the active operation to finish.")
        self.control = control

        def run() -> None:
            try:
                reply = WorkerReply(generation, kind, task())
            except ExecutionFailure as exc:
                reply = WorkerReply(
                    generation,
                    kind,
                    error=f"{exc.code}: Check the selected input and review the operation.",
                )
            except InspectionError as exc:
                reply = WorkerReply(
                    generation,
                    kind,
                    error=f"Inspection error ({exc.exit_code}): Check the local file and ffprobe.",
                )
            except Exception:
                reply = WorkerReply(
                    generation,
                    kind,
                    error="Unexpected failure. Verify the inputs and tools, then try again.",
                )
            with self._lock:
                self._reply = reply

        self._thread = threading.Thread(target=run, name="MediaTrack-worker", daemon=False)
        self._thread.start()

    def poll(self) -> tuple[ProgressEvent | None, WorkerReply | None]:
        with self._lock:
            progress, self._progress = self._progress, None
            reply = None
            if self._thread is not None and not self._thread.is_alive():
                self._thread.join()
                self._thread = None
                self.control = None
                reply, self._reply = self._reply, None
            return progress, reply

    def cancel(self) -> bool:
        return self.control.cancellation.cancel() if self.control is not None else False

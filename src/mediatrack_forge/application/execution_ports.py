"""Small injectable boundaries for inspection, process, validation and owned storage."""

from pathlib import Path
from typing import Protocol

from mediatrack_forge.domain.execution import ProcessOutcome, ValidationReport
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import OperationPlan


class Inspector(Protocol):
    def inspect(self, path: str | Path, *, timeout_seconds: float = 30.0) -> MediaAsset: ...


class ProcessRunner(Protocol):
    def run(self, arguments: tuple[str, ...], timeout_seconds: float) -> ProcessOutcome: ...


class OwnedStage(Protocol):
    @property
    def path(self) -> Path: ...
    def verify(self) -> None: ...
    def flush(self) -> None: ...
    def publish(self, destination: Path) -> None: ...
    def cleanup(self) -> None: ...
    def release(self) -> None: ...


class StagingStore(Protocol):
    def allocate(self, destination: Path) -> OwnedStage: ...


class OutputValidator(Protocol):
    def validate(
        self, plan: OperationPlan, path: Path, inspector: Inspector, timeout_seconds: float
    ) -> ValidationReport: ...

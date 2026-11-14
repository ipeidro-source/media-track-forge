"""Immutable execution requests, state histories and validation evidence."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import OperationPlan

ExecutionState = Literal[
    "planned", "running", "validating", "publishing", "completed", "failed", "timed_out"
]


@dataclass(frozen=True)
class ProcessConfiguration:
    ffmpeg: str | None = None
    ffprobe: str | None = None
    timeout_seconds: float = 300.0
    probe_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ExecutionRequest:
    plan: OperationPlan
    reviewed_revision: str
    confirmed_revision: str | None = None
    configuration: ProcessConfiguration = ProcessConfiguration()


@dataclass(frozen=True)
class ExecutionDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ProcessOutcome:
    return_code: int | None
    error_code: str | None = None
    safe_to_cleanup: bool = True
    stdout_bytes: int = 0
    stderr_bytes: int = 0


@dataclass(frozen=True)
class ValidationCheck:
    code: str
    status: Literal["passed", "warning", "error"]
    detail: str
    output_index: int | None = None
    expected_seconds: float | None = None
    observed_seconds: float | None = None
    tolerance_seconds: float | None = None


@dataclass(frozen=True)
class ValidationReport:
    expected_streams: tuple[tuple[str, str | None], ...]
    observed: MediaAsset | None
    checks: tuple[ValidationCheck, ...]

    @property
    def passed(self) -> bool:
        return not any(check.status == "error" for check in self.checks)


@dataclass(frozen=True)
class ExecutionResult:
    state: ExecutionState
    history: tuple[ExecutionState, ...]
    diagnostics: tuple[ExecutionDiagnostic, ...]
    validation: ValidationReport | None = None
    destination: Path | None = None
    published: bool = False
    cleanup_complete: bool = True


class ExecutionFailure(Exception):
    """Stable code only; infrastructure exceptions never become raw user diagnostics."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

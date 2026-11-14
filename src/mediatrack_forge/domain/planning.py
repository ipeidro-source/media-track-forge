"""Immutable, versioned planning intent; no process execution or filesystem writes."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from mediatrack_forge.domain.media import MediaAsset, MediaSource, Stream, StreamKind, Tags


@dataclass(frozen=True)
class StreamReference:
    source: MediaSource
    index: int


@dataclass(frozen=True)
class MetadataIntent:
    """None preserves source values; empty text clears a tag, False clears a flag."""

    language: str | None = None
    title: str | None = None
    default: bool | None = None
    forced: bool | None = None


@dataclass(frozen=True)
class TrackSelection:
    reference: StreamReference
    include: bool = True
    metadata: MetadataIntent = MetadataIntent()


@dataclass(frozen=True)
class ExternalTrack:
    """Caller-supplied validation claim must match a supplied inspected snapshot."""

    source: MediaSource
    intended_kind: StreamKind
    stream_index: int | None = None
    codec: str | None = None
    format_name: str | None = None
    metadata: MetadataIntent = MetadataIntent()
    validated: bool = False


@dataclass(frozen=True)
class OutputProfile:
    container: str
    path: str


@dataclass(frozen=True)
class CompatibilityIssue:
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    suggestion: str | None = None
    reference: StreamReference | None = None


@dataclass(frozen=True)
class PreservationDecision:
    category: str
    status: Literal["preserve", "modify", "exclude", "unsupported", "uncertain"]
    detail: str
    reference: StreamReference | None = None


@dataclass(frozen=True)
class PlannedStream:
    reference: StreamReference
    source_stream: Stream
    input_index: int
    output_index: int
    action: Literal["copy", "convert_subtitle"]
    target_codec: str | None
    output_tags: Tags
    output_disposition: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ExcludedStream:
    reference: StreamReference
    source_stream: Stream
    explicit: bool
    action: Literal["exclude"] = "exclude"


@dataclass(frozen=True)
class OperationPlan:
    sources: tuple[MediaAsset, ...]
    output: OutputProfile
    destination_path: Path | None
    selections: tuple[TrackSelection, ...]
    external_tracks: tuple[ExternalTrack, ...]
    included: tuple[PlannedStream, ...]
    excluded: tuple[ExcludedStream, ...]
    preserve_chapters: bool
    chapter_input_index: int | None
    preservation: tuple[PreservationDecision, ...]
    issues: tuple[CompatibilityIssue, ...]
    acknowledged_warnings: frozenset[str]
    acknowledged_revision: str | None = None
    arguments: tuple[str, ...] | None = None
    plan_version: int = 1
    confirmation_required: bool = True

    def __post_init__(self) -> None:
        # Also keep dataclasses.replace() from retaining a stale proposed command.
        if self.arguments is not None and (not self.intrinsically_valid or self.pending_warnings):
            object.__setattr__(self, "arguments", None)

    @property
    def revision(self) -> str:
        """Fingerprint all intent, snapshots and diagnostics, excluding review state."""
        content = asdict(self)
        for key in ("acknowledged_warnings", "acknowledged_revision", "arguments"):
            del content[key]
        encoded = json.dumps(
            content,
            default=str,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def effective_acknowledged_warnings(self) -> frozenset[str]:
        """Codes alone, or codes bound to another revision, grant no acknowledgement."""
        if not self.acknowledged_warnings or self.acknowledged_revision != self.revision:
            return frozenset()
        return self.acknowledged_warnings

    @property
    def intrinsically_valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def pending_warnings(self) -> tuple[str, ...]:
        acknowledged = self.effective_acknowledged_warnings
        return tuple(
            sorted(
                {
                    issue.code
                    for issue in self.issues
                    if issue.severity == "warning" and issue.code not in acknowledged
                }
            )
        )

    @property
    def execution_allowed(self) -> bool:
        """Eligible for future confirmation/revalidation, never authorization to run now."""
        return self.intrinsically_valid and not self.pending_warnings and self.arguments is not None

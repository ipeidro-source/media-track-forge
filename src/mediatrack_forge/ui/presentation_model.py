"""Display-independent immutable editing intent and generation-safe UI orchestration."""

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, TypedDict, Unpack, cast

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.external_subtitles import ExternalSubtitleService
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    ProcessConfiguration,
    ProgressEvent,
)
from mediatrack_forge.domain.extraction import ExtractionPlan
from mediatrack_forge.domain.media import MediaAsset, Stream
from mediatrack_forge.domain.planning import (
    ExternalTrack,
    MetadataIntent,
    OperationPlan,
    OutputProfile,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.planning_paths import destination_path
from mediatrack_forge.ui.worker import Worker, WorkerReply


@dataclass(frozen=True)
class EditingIntent:
    sources: tuple[MediaAsset, ...] = ()
    selections: tuple[TrackSelection, ...] = ()
    external_tracks: tuple[ExternalTrack, ...] = ()
    mode: Literal["Remux", "Extract"] = "Remux"
    container: str = "mkv"
    destination: str = ""
    preserve_chapters: bool = True
    extraction_target: StreamReference | None = None


class IntentChanges(TypedDict, total=False):
    sources: tuple[MediaAsset, ...]
    selections: tuple[TrackSelection, ...]
    external_tracks: tuple[ExternalTrack, ...]
    mode: Literal["Remux", "Extract"]
    container: str
    destination: str
    preserve_chapters: bool
    extraction_target: StreamReference | None


class DesktopBackend:
    """Compose existing application APIs; no window or display initialization."""

    def __init__(self, configuration: ProcessConfiguration | None = None) -> None:
        self.configuration = configuration if configuration is not None else ProcessConfiguration()
        self.inspector = InspectionService(FFprobeAdapter(self.configuration.ffprobe))

    def inspect(self, path: str) -> MediaAsset:
        return self.inspector.inspect(
            path, timeout_seconds=self.configuration.probe_timeout_seconds
        )

    @staticmethod
    def destination_feedback(intent: EditingIntent, extension: str) -> str:
        try:
            path = destination_path(intent.destination)
            if path.suffix.lower() != "." + extension:
                return "The filename extension must match the selected output format."
            if os.path.lexists(path):
                return "Destination exists. Choose a new filename; overwriting is unavailable."
            if any(path == asset.source.path for asset in intent.sources):
                return "Choose a filename different from every source."
            if not path.parent.is_dir():
                return "Choose an existing local output folder."
            return ""
        except (OSError, ValueError, RuntimeError):
            return "Choose a supported local output path. Network destinations are unavailable."

    @staticmethod
    def suggest_destination(intent: EditingIntent, filename: str) -> str:
        parent = Path(intent.destination).parent if intent.destination else Path.home()
        name = Path(filename)
        for number in range(1, 101):
            candidate = parent / f"{name.stem}{'' if number == 1 else f'-{number}'}{name.suffix}"
            try:
                path = destination_path(str(candidate))
                if not os.path.lexists(path) and path.parent.is_dir():
                    return str(path)
            except (OSError, ValueError, RuntimeError):
                break
        return ""

    def import_subtitles(
        self, paths: tuple[str, ...]
    ) -> tuple[tuple[MediaAsset, ExternalTrack], ...]:
        return tuple(
            ExternalSubtitleService(self.inspector).import_srt(
                path, timeout_seconds=self.configuration.probe_timeout_seconds
            )
            for path in paths
        )

    def plan(
        self,
        intent: EditingIntent,
        *,
        codes: frozenset[str] = frozenset(),
        revision: str | None = None,
    ) -> OperationPlan:
        if not intent.sources:
            raise ValueError("Open media first.")
        if intent.mode == "Extract":
            if intent.extraction_target is None:
                raise ValueError("Select exactly one extraction target.")
            source = next(a for a in intent.sources if a.source == intent.extraction_target.source)
            return ExtractionPlanningService().plan(
                source,
                intent.extraction_target,
                intent.destination,
                acknowledged_warnings=codes,
                acknowledged_revision=revision,
            )
        return OperationPlanningService().plan(
            intent.sources,
            intent.selections,
            OutputProfile(intent.container, intent.destination),
            external_tracks=intent.external_tracks,
            preserve_chapters=intent.preserve_chapters,
            acknowledged_warnings=codes,
            acknowledged_revision=revision,
        )

    def execute(self, request: ExecutionRequest, control: ExecutionControl) -> ExecutionResult:
        service = (
            ExtractionExecutionService()
            if isinstance(request.plan, ExtractionPlan)
            else RemuxExecutionService()
        )
        return service.execute(request, control=control)


class DesktopController:
    def __init__(self, backend: DesktopBackend | None = None, worker: Worker | None = None) -> None:
        self.backend = backend if backend is not None else DesktopBackend()
        self.worker = worker if worker is not None else Worker()
        self.intent = EditingIntent()
        self.generation = 0
        self.plan: OperationPlan | None = None
        self.reviewed_revision: str | None = None
        self.confirmed_revision: str | None = None
        self.result: ExecutionResult | None = None
        self.progress: ProgressEvent | None = None
        self.error: str | None = None
        self.status = "Open a media file to begin."
        self.close_pending = False
        self.closed = False
        self.recovery_required = False
        self.destination_feedback = ""
        self.inspection_revision = 0
        self._authorization: tuple[int, EditingIntent, OperationPlan, frozenset[str]] | None = None

    def invalidate(self) -> None:
        self._authorization = None
        self.generation += 1
        self.plan = None
        self.reviewed_revision = None
        self.confirmed_revision = None
        self.error = None
        self.result = None
        self.progress = None
        self.destination_feedback = ""

    def _editable(self) -> None:
        if self.worker.busy or self.closed or self.recovery_required:
            raise ValueError("Wait for the active operation before editing.")

    def change(self, **values: Unpack[IntentChanges]) -> None:
        self._editable()
        self.intent = replace(self.intent, **values)
        self.invalidate()

    def _start(
        self, kind: str, task: Callable[[], object], *, control: ExecutionControl | None = None
    ) -> None:
        self.error = None
        self.progress = ProgressEvent("preparing", False)
        self.status = f"{kind.capitalize()} in progress..."
        self.worker.start(self.generation, kind, task, control=control)

    def open_media(self, path: str) -> None:
        self._editable()
        self.invalidate()
        self._start("inspect", lambda: self.backend.inspect(path))

    def add_subtitles(self, paths: tuple[str, ...]) -> None:
        self._editable()
        if not self.intent.sources:
            raise ValueError("Open primary media before adding SRT files.")
        self.invalidate()
        self._start("subtitles", lambda: self.backend.import_subtitles(paths))

    def check_destination(self, extension: str) -> None:
        self._editable()
        intent = self.intent
        self._start("destination", lambda: self.backend.destination_feedback(intent, extension))

    def suggest_destination(self, filename: str) -> None:
        self._editable()
        self.invalidate()
        intent = self.intent
        self._start("suggest", lambda: self.backend.suggest_destination(intent, filename))

    def stream(self, reference: StreamReference) -> Stream:
        return next(
            s
            for a in self.intent.sources
            if a.source == reference.source
            for s in a.streams
            if s.index == reference.index
        )

    def edit_track(
        self,
        reference: StreamReference,
        *,
        include: bool | None = None,
        metadata: MetadataIntent | None = None,
    ) -> None:
        selections = tuple(
            replace(
                s,
                include=s.include if include is None else include,
                metadata=s.metadata if metadata is None else metadata,
            )
            if s.reference == reference
            else s
            for s in self.intent.selections
        )
        tracks = tuple(
            replace(t, metadata=metadata)
            if t.source == reference.source and metadata is not None
            else t
            for t in self.intent.external_tracks
        )
        self.change(selections=selections, external_tracks=tracks)

    def move(self, reference: StreamReference, direction: int) -> None:
        self._editable()
        if direction not in (-1, 1):
            raise ValueError("Move one position within the same track kind.")
        selected = list(self.intent.selections)
        peers = [
            i
            for i, s in enumerate(selected)
            if self.stream(s.reference).kind == self.stream(reference).kind
        ]
        index = next(i for i, s in enumerate(selected) if s.reference == reference)
        target = peers.index(index) + direction
        if not 0 <= target < len(peers):
            return
        other = peers[target]
        selected[index], selected[other] = selected[other], selected[index]
        self.change(selections=tuple(selected))

    def remove_external(self, reference: StreamReference) -> None:
        if not any(t.source == reference.source for t in self.intent.external_tracks):
            raise ValueError("Only external SRT sources can be removed from the session.")
        self.change(
            sources=tuple(a for a in self.intent.sources if a.source != reference.source),
            selections=tuple(
                s for s in self.intent.selections if s.reference.source != reference.source
            ),
            external_tracks=tuple(
                t for t in self.intent.external_tracks if t.source != reference.source
            ),
            extraction_target=None,
        )

    def generate_plan(self) -> None:
        self._editable()
        if not self.intent.sources:
            raise ValueError("Open media before reviewing an operation.")
        if self.intent.mode == "Extract" and self.intent.extraction_target is None:
            raise ValueError("Choose one extraction target in the Media area.")
        self.invalidate()
        intent = self.intent
        self._start("plan", lambda: self.backend.plan(intent))

    def acknowledge(self, codes: frozenset[str], revision: str) -> None:
        self._editable()
        if (
            self.plan is None
            or revision != self.plan.revision
            or revision != self.reviewed_revision
        ):
            raise ValueError("Review the current plan before acknowledging warnings.")
        intent = self.intent
        self._start(
            "acknowledge", lambda: self.backend.plan(intent, codes=codes, revision=revision)
        )

    @property
    def can_authorize(self) -> bool:
        return (
            not self.worker.busy
            and not self.closed
            and not self.recovery_required
            and self.plan is not None
            and self.plan.intrinsically_valid
            and (bool(self.plan.pending_warnings) or self.plan.execution_allowed)
            and self.reviewed_revision == self.plan.revision
            and self._authorization is None
        )

    def accept_and_execute(self) -> None:
        """One explicit user decision; acknowledgement and confirmation stay separate."""
        if not self.can_authorize or self.plan is None:
            raise ValueError("Review the current valid plan before executing.")
        plan = self.plan
        if not plan.pending_warnings:
            self.execute(plan.revision)
            return
        codes = frozenset(plan.pending_warnings)
        self._authorization = (self.generation, self.intent, plan, codes)
        try:
            self.acknowledge(plan.effective_acknowledged_warnings | codes, plan.revision)
        except Exception:
            self._authorization = None
            raise

    def start_over(self) -> None:
        self._editable()
        if (
            self.result is None
            or not self.result.cleanup_complete
            or self.result.state not in ("completed", "cancelled", "failed", "timed_out")
        ):
            raise ValueError("Wait for a verified terminal result before starting over.")
        self.invalidate()
        self.intent = EditingIntent()
        self.close_pending = False
        self.status = "Open a media file to begin."

    @property
    def can_execute(self) -> bool:
        return (
            not self.worker.busy
            and not self.closed
            and not self.recovery_required
            and self.plan is not None
            and self.plan.intrinsically_valid
            and not self.plan.pending_warnings
            and self.reviewed_revision == self.plan.revision
        )

    def execute(self, confirmed_revision: str) -> None:
        if not self.can_execute or self.plan is None or confirmed_revision != self.plan.revision:
            raise ValueError(
                "Review the current plan, acknowledge warnings, then confirm execution."
            )
        self.confirmed_revision = confirmed_revision
        request = ExecutionRequest(
            self.plan,
            cast(str, self.reviewed_revision),
            confirmed_revision,
            self.backend.configuration,
        )
        self.result = None
        control = ExecutionControl(listener=self.worker.progress)
        self._start("execute", lambda: self.backend.execute(request, control), control=control)

    def cancel(self) -> None:
        self._authorization = None
        if self.worker.cancel():
            self.status = "Cancelling; waiting for safe backend termination..."
        elif self.worker.busy:
            self.status = "Waiting for the current step; publication may already be committed."

    def apply(self, reply: WorkerReply) -> None:
        if self.closed or reply.generation != self.generation:
            return
        if reply.error is not None:
            self._authorization = None
            if reply.kind == "execute":
                self.recovery_required = True
            self.error = reply.error
            self.progress = ProgressEvent("failed", False, terminal=True)
            self.status = reply.error
            if self.recovery_required:
                self.status += " Termination/cleanup is unverified; keep recovery details visible."
            return
        if reply.kind == "inspect":
            self.inspection_revision += 1
            asset = cast(MediaAsset, reply.value)
            self.intent = EditingIntent(
                sources=(asset,),
                selections=tuple(
                    TrackSelection(StreamReference(asset.source, s.index)) for s in asset.streams
                ),
            )
            self.status = "Inspected. All streams initially included; review output compatibility."
        elif reply.kind == "destination":
            self.destination_feedback = cast(str, reply.value)
            self.status = (
                self.destination_feedback
                or "New local destination available; execution will recheck it."
            )
        elif reply.kind == "suggest":
            path = cast(str, reply.value)
            if path:
                self.intent = replace(self.intent, destination=path)
                self.status = (
                    "Suggested a free filename. Review before execution; availability is rechecked."
                )
            else:
                self.status = (
                    "Choose an existing supported local output folder, then try a new filename."
                )
        elif reply.kind == "subtitles":
            imported = cast(tuple[tuple[MediaAsset, ExternalTrack], ...], reply.value)
            known = {a.source for a in self.intent.sources}
            unique = []
            for asset, track in imported:
                if asset.source not in known:
                    unique.append((asset, track))
                    known.add(asset.source)
            skipped = len(imported) - len(unique)
            imported = tuple(unique)
            self.intent = replace(
                self.intent,
                sources=self.intent.sources + tuple(a for a, _ in imported),
                external_tracks=self.intent.external_tracks + tuple(t for _, t in imported),
                selections=self.intent.selections
                + tuple(
                    TrackSelection(StreamReference(a.source, a.streams[0].index))
                    for a, _ in imported
                ),
            )
            self.status = f"Added {len(imported)} SRT source(s)."
            if skipped:
                self.status += (
                    f" Skipped {skipped} already-present source(s); files remain untouched."
                )
        elif reply.kind in ("plan", "acknowledge"):
            plan = cast(OperationPlan, reply.value)
            authorization, self._authorization = self._authorization, None
            if reply.kind == "acknowledge" and authorization is not None:
                generation, intent, reviewed, codes = authorization
                if (
                    generation != self.generation
                    or intent != self.intent
                    or self.plan != reviewed
                    or self.reviewed_revision != reviewed.revision
                    or plan.revision != reviewed.revision
                    or plan.issues != reviewed.issues
                    or not plan.intrinsically_valid
                    or not plan.execution_allowed
                    or plan.pending_warnings
                    or plan.effective_acknowledged_warnings
                    != reviewed.effective_acknowledged_warnings | codes
                ):
                    self.invalidate()
                    self.plan = plan
                    self.reviewed_revision = plan.revision
                    self.error = (
                        "The reviewed plan or warnings changed. Review and choose Execute again."
                    )
                    self.status = self.error
                    return
                self.plan = plan
                self.reviewed_revision = plan.revision
                self.execute(reviewed.revision)
                return
            if reply.kind == "acknowledge" and self.reviewed_revision != plan.revision:
                self.invalidate()
                self.error = (
                    "The plan changed during acknowledgement. Generate and review it again."
                )
                self.status = self.error
                return
            self.plan = plan
            self.reviewed_revision = plan.revision
            self.status = (
                "Review the complete plan and its diagnostics before acknowledging or executing."
            )
        elif reply.kind == "execute":
            self.result = cast(ExecutionResult, reply.value)
            self.progress = ProgressEvent(
                self.result.state,
                self.result.state == "completed",
                100.0 if self.result.state == "completed" else None,
                terminal=True,
            )
            self.recovery_required = not self.result.cleanup_complete
            self.status = (
                f"{self.result.state.replace('_', ' ').capitalize()}. See Execution for results."
            )
            self.confirmed_revision = None
            self.reviewed_revision = None
        else:
            self.error = "Unknown background operation result."
        if reply.kind != "execute":
            self.progress = None

    def poll(self) -> bool:
        if self.closed:
            return False
        progress, reply = self.worker.poll()
        if progress is not None:
            self.progress = progress
        if reply is not None:
            self.apply(reply)
        return progress is not None or reply is not None

    def request_close(self, cancel_and_close: bool) -> bool:
        if not cancel_and_close:
            self.close_pending = False
        if not self.worker.busy:
            if self.recovery_required:
                self.status = "Cleanup incomplete. Keep recovery details visible; inspect staging."
                return False
            self.closed = True
            return True
        if cancel_and_close:
            self.close_pending = True
            self.cancel()
        return False

    @property
    def safe_to_close(self) -> bool:
        return (
            self.close_pending
            and not self.worker.busy
            and self.error is None
            and not self.recovery_required
            and (self.result is None or self.result.cleanup_complete)
        )


def result_text(result: ExecutionResult) -> str:
    lines = [
        f"Result: {result.state.replace('_', ' ')}",
        f"Published: {'yes' if result.published else 'no'}",
        f"Output: {result.destination or 'None'}",
        "Temporary cleanup: "
        + ("complete" if result.cleanup_complete else "INCOMPLETE — inspect recovery details"),
    ]
    lines.extend(f"{d.code}: {d.message}" for d in result.diagnostics)
    if result.validation is not None:
        lines.append("Validation: " + ("passed" if result.validation.passed else "failed"))
        lines.extend(f"{c.status.upper()} {c.code}: {c.detail}" for c in result.validation.checks)
        lines.append(
            "Resulting streams: "
            + ", ".join(f"{k}/{c or 'unknown'}" for k, c in result.validation.expected_streams)
        )
    return "\n".join(lines)


def plan_text(plan: OperationPlan) -> str:
    lines = [
        "REVIEW OPERATION",
        f"Revision: {plan.revision}",
        f"Output: {plan.destination_path or plan.output.path}",
        f"Format: {plan.output.container}",
    ]
    lines.extend(f"Source {i}: {a.source.path}" for i, a in enumerate(plan.sources))
    for selection in plan.selections:
        lines.append(
            f"Intent: {selection.reference.source.path.name}, "
            f"index {selection.reference.index}, "
            f"{'include' if selection.include else 'exclude'}, "
            f"metadata {selection.metadata} (None = keep original; empty text = clear)"
        )
    for s in plan.included:
        lines.append(
            f"Output {s.output_index}: input {s.input_index}, original index {s.reference.index}, "
            f"{s.source_stream.kind}/{s.source_stream.codec} → {s.target_codec} ({s.action})"
        )
        lines.append(f"  Metadata: {dict(s.output_tags)}; flags: {dict(s.output_disposition)}")
    lines.extend(
        f"Excluded: {s.reference.source.path.name}, index {s.reference.index} "
        f"({'explicit' if s.explicit else 'implicit'})"
        for s in plan.excluded
    )
    lines.extend(f"{p.category}: {p.status} — {p.detail}" for p in plan.preservation)
    if isinstance(plan, ExtractionPlan):
        lines.append("Bitstream filters: " + (", ".join(plan.bitstream_filters) or "None"))
    lines.extend(
        f"{i.severity.upper()} {i.code}: {i.message}"
        + (f" [{i.reference.source.path.name}, index {i.reference.index}]" if i.reference else "")
        + (f" Suggestion: {i.suggestion}" if i.suggestion else "")
        for i in plan.issues
    )
    return "\n".join(lines)

"""Deterministic planning orchestration with read-only identity and destination checks."""

import os
from dataclasses import replace
from typing import Literal, cast

from mediatrack_forge.application.inspection import InvalidInputError, snapshot_source
from mediatrack_forge.domain.compatibility import codec_action
from mediatrack_forge.domain.media import MediaAsset, Stream
from mediatrack_forge.domain.planning import (
    CompatibilityIssue,
    ExcludedStream,
    ExternalTrack,
    MetadataIntent,
    OperationPlan,
    OutputProfile,
    PlannedStream,
    PreservationDecision,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.ffmpeg_arguments import build_arguments
from mediatrack_forge.infrastructure.planning_paths import destination_path, equivalent_paths


class OperationPlanningService:
    """Consume inspected snapshots and explicit intent; never inspect or write media."""

    def plan(
        self,
        sources: tuple[MediaAsset, ...],
        selections: tuple[TrackSelection, ...],
        output: OutputProfile,
        *,
        external_tracks: tuple[ExternalTrack, ...] = (),
        preserve_chapters: bool = True,
        acknowledged_warnings: frozenset[str] = frozenset(),
    ) -> OperationPlan:
        issues: list[CompatibilityIssue] = []
        preservation: list[PreservationDecision] = []

        def issue(
            code: str,
            severity: Literal["info", "warning", "error"],
            message: str,
            reference: StreamReference | None = None,
            suggestion: str | None = None,
        ) -> None:
            issues.append(CompatibilityIssue(code, severity, message, suggestion, reference))

        lookup: dict[StreamReference, tuple[int, Stream]] = {}
        if not sources:
            issue("NO_SOURCE", "error", "At least one inspected primary source is required.")
        for input_index, asset in enumerate(sources):
            if asset.source in [item.source for item in sources[:input_index]]:
                issue("DUPLICATE_SOURCE", "error", "An input source may only be supplied once.")
            try:
                if snapshot_source(asset.source.path) != asset.source:
                    issue(
                        "SOURCE_CHANGED", "error", "The source identity changed; inspect it again."
                    )
            except InvalidInputError:
                issue("INVALID_SOURCE", "error", "A source is unavailable; inspect it again.")
            for stream in asset.streams:
                reference = StreamReference(asset.source, stream.index)
                if reference in lookup or stream.index < 0:
                    issue(
                        "INVALID_STREAM_IDENTITY", "error", "Source stream identities are invalid."
                    )
                lookup[reference] = input_index, stream
            if asset.format.tags:
                issue(
                    "FORMAT_METADATA_EXCLUDED",
                    "warning",
                    "Global container tags are not copied by the initial planning policy.",
                )
            preservation.append(
                PreservationDecision(
                    f"format_tags:{input_index}",
                    "exclude",
                    "Global metadata auto-copy is disabled.",
                )
            )

        for track in external_tracks:
            external_reference = (
                StreamReference(track.source, track.stream_index)
                if track.stream_index is not None
                else None
            )
            found = lookup.get(external_reference) if external_reference is not None else None
            valid = (
                track.validated
                and found is not None
                and found[1].kind == track.intended_kind
                and found[1].codec == track.codec
                and sources[found[0]].format.name == track.format_name
            )
            if not valid:
                issue(
                    "EXTERNAL_TRACK_NOT_VALIDATED",
                    "error",
                    "External tracks require matching inspected and validated source metadata.",
                    external_reference,
                    "Supply a validated inspection snapshot; import is not implemented.",
                )
            if track.metadata != MetadataIntent():
                matching = [item for item in selections if item.reference == external_reference]
                if not matching or matching[0].metadata != track.metadata:
                    issue(
                        "EXTERNAL_METADATA_CONFLICT",
                        "error",
                        "External metadata intent must match its explicit track selection.",
                        external_reference,
                    )

        destination = None
        if output.container not in ("mkv", "mp4"):
            issue("UNSUPPORTED_OUTPUT_CONTAINER", "error", "Only MKV and MP4 output is supported.")
        try:
            destination = destination_path(output.path)
            if destination.suffix.lower() != f".{output.container}":
                issue(
                    "OUTPUT_EXTENSION_MISMATCH", "error", "Output extension must match container."
                )
            if any(parent.exists() and not parent.is_dir() for parent in destination.parents):
                issue("INVALID_DESTINATION", "error", "An output parent is not a directory.")
            if os.path.lexists(output.path) or destination.exists():
                issue(
                    "DESTINATION_EXISTS", "error", "The output already exists; choose a new path."
                )
            for asset in sources:
                if equivalent_paths(destination, asset.source.path) or (
                    destination.exists()
                    and asset.source.path.exists()
                    and os.path.samefile(destination, asset.source.path)
                ):
                    issue(
                        "SOURCE_DESTINATION_CONFLICT",
                        "error",
                        "The output must differ from every input source.",
                    )
            if any(
                equivalent_paths(destination, track.source.path.resolve())
                for track in external_tracks
            ):
                issue(
                    "SOURCE_DESTINATION_CONFLICT",
                    "error",
                    "The output must differ from every external source.",
                )
        except (OSError, ValueError, RuntimeError):
            issue("INVALID_DESTINATION", "error", "Provide a valid local destination path.")

        seen: set[StreamReference] = set()
        included_selections: list[TrackSelection] = []
        explicit_exclusions: set[StreamReference] = set()
        for selection in selections:
            reference = selection.reference
            if reference in seen:
                issue(
                    "DUPLICATE_SELECTION", "error", "A stream may only be selected once.", reference
                )
                continue
            seen.add(reference)
            if reference not in lookup:
                issue(
                    "UNKNOWN_STREAM_REFERENCE",
                    "error",
                    "Selection does not match an inspected source and original stream index.",
                    reference,
                )
            elif selection.include:
                included_selections.append(selection)
            else:
                explicit_exclusions.add(reference)

        rank = {"video": 0, "audio": 1, "subtitle": 2, "attachment": 3, "data": 4, "unknown": 5}
        included_selections.sort(key=lambda item: rank[lookup[item.reference][1].kind])
        included: list[PlannedStream] = []
        for selection in included_selections:
            reference = selection.reference
            input_index, stream = lookup[reference]
            action = codec_action(stream, output.container)
            if action is None:
                issue(
                    "UNSUPPORTED_CODEC_FOR_CONTAINER",
                    "error",
                    f"The selected {stream.kind} codec {stream.codec!r} is not supported by "
                    f"the current {output.container.upper()} policy.",
                    reference,
                    "Choose a validated MKV combination or exclude this stream.",
                )
                preservation.append(
                    PreservationDecision(
                        "stream", "unsupported", "Selected combination is unvalidated.", reference
                    )
                )
                continue
            intent = selection.metadata
            for value in (intent.language, intent.title):
                if value is not None and "\x00" in value:
                    issue(
                        "INVALID_METADATA",
                        "error",
                        "Metadata cannot contain a NUL byte.",
                        reference,
                    )
            tags = dict(stream.tags)
            kept_tags = {
                key: val
                for key, val in tags.items()
                if key in ("language", "title")
                or (stream.kind == "attachment" and key in ("filename", "mimetype"))
            }
            for key in ("language", "title"):
                requested = getattr(intent, key)
                if requested is not None:
                    kept_tags[key] = requested
                preservation.append(
                    PreservationDecision(
                        key,
                        "modify" if requested is not None else "preserve",
                        "Preserve available value; no missing value is invented."
                        if requested is None
                        else "Explicit requested value, including empty tag clearing.",
                        reference,
                    )
                )
            extra_tags = set(tags) - set(kept_tags)
            if any("\x00" in value for value in kept_tags.values()):
                issue(
                    "INVALID_METADATA", "error", "Output metadata contains a NUL byte.", reference
                )
            if output.container == "mkv" and kept_tags.get("language") == "und":
                issue(
                    "LANGUAGE_UND_UNCERTAIN",
                    "warning",
                    "Matroska may omit the explicit und language tag; intent remains und.",
                    reference,
                )
            if extra_tags:
                issue(
                    "STREAM_METADATA_EXCLUDED",
                    "warning",
                    "Stream tags outside the supported metadata policy will be excluded.",
                    reference,
                )
            preservation.append(
                PreservationDecision(
                    "other_tags",
                    "exclude" if extra_tags else "preserve",
                    "Only language/title and validated attachment filename/MIME tags are copied.",
                    reference,
                )
            )
            flags = {key: val for key, val in stream.disposition if key in ("default", "forced")}
            for key in ("default", "forced"):
                requested_flag = getattr(intent, key)
                if requested_flag is not None:
                    flags[key] = int(requested_flag)
                preservation.append(
                    PreservationDecision(
                        key,
                        "modify" if requested_flag is not None else "preserve",
                        "Explicit flag intent; missing source flags remain absent in the snapshot.",
                        reference,
                    )
                )
            if any(value and key not in ("default", "forced") for key, value in stream.disposition):
                issue(
                    "DISPOSITION_LOSS",
                    "warning",
                    "Non-default/non-forced disposition flags are excluded by this policy.",
                    reference,
                )
            if stream.kind != "attachment" and set(flags) != {"default", "forced"}:
                issue(
                    "DISPOSITION_ABSENCE_UNCERTAIN",
                    "warning",
                    "Absent flags may not stay absent; automatic default selection is disabled.",
                    reference,
                )
            if output.container == "mp4" and (kept_tags or flags):
                issue(
                    "MP4_METADATA_UNCERTAIN",
                    "warning",
                    "MP4 metadata may be normalized; exact preservation is uncertain.",
                    reference,
                )
                preservation.append(
                    PreservationDecision(
                        "container_metadata",
                        "uncertain",
                        "MP4 metadata semantics require output validation.",
                        reference,
                    )
                )
            if action[0] == "convert_subtitle":
                issue(
                    "SUBTITLE_FORMATTING_MAY_CHANGE",
                    "warning",
                    "Explicit SubRip to mov_text subtitle encoding may change formatting.",
                    reference,
                )
            included.append(
                PlannedStream(
                    reference,
                    stream,
                    input_index,
                    len(included),
                    cast(Literal["copy", "convert_subtitle"], action[0]),
                    action[1],
                    tuple(sorted(kept_tags.items())),
                    tuple(sorted(flags.items())),
                )
            )

        if not any(item.source_stream.kind == "video" for item in included):
            issue("VIDEO_REQUIRED", "error", "Select at least one supported video stream.")
        for kind in ("video", "audio", "subtitle"):
            if (
                sum(
                    dict(item.output_disposition).get("default", 0)
                    for item in included
                    if item.source_stream.kind == kind
                )
                > 1
            ):
                issue(
                    "CONFLICTING_DEFAULT_FLAGS",
                    "error",
                    f"Multiple {kind} streams request default; choose at most one explicitly.",
                )

        excluded: list[ExcludedStream] = []
        for reference, (_, stream) in lookup.items():
            if reference not in {item.reference for item in included_selections}:
                explicit = reference in explicit_exclusions
                excluded.append(ExcludedStream(reference, stream, explicit))
                preservation.append(
                    PreservationDecision(
                        "stream",
                        "exclude",
                        "Explicit exclusion."
                        if explicit
                        else "Not selected; omission requires acknowledgement.",
                        reference,
                    )
                )
                if not explicit:
                    issue(
                        "STREAM_IMPLICITLY_OMITTED",
                        "warning",
                        "An unselected source stream will be omitted.",
                        reference,
                        "Select it or explicitly exclude it.",
                    )

        chapter_input = None
        for input_index, asset in enumerate(sources):
            if not asset.chapters:
                continue
            if preserve_chapters and input_index == 0 and output.container == "mkv":
                chapter_input = 0
                if any(key != "title" for chapter in asset.chapters for key, _ in chapter.tags):
                    issue(
                        "CHAPTER_METADATA_EXCLUDED",
                        "warning",
                        "Chapter titles and times are preserved; other tags are excluded.",
                    )
                if any(
                    "\x00" in value
                    for chapter in asset.chapters
                    for key, value in chapter.tags
                    if key == "title"
                ):
                    issue("INVALID_METADATA", "error", "Chapter titles cannot contain a NUL byte.")
                preservation.append(
                    PreservationDecision(
                        "chapters:0", "preserve", "Map primary chapters explicitly."
                    )
                )
            elif preserve_chapters and input_index == 0:
                issue(
                    "CHAPTER_COPY_UNVALIDATED",
                    "error",
                    "Chapter copying is only validated for the primary source into MKV.",
                    suggestion="Explicitly exclude chapters or choose MKV.",
                )
                preservation.append(
                    PreservationDecision(
                        "chapters:0", "unsupported", "Chapter copying into MP4 is unvalidated."
                    )
                )
            else:
                issue(
                    "CHAPTERS_EXCLUDED",
                    "warning",
                    "Source chapters will be excluded; only primary MKV chapters can be preserved.",
                )
                preservation.append(
                    PreservationDecision(
                        f"chapters:{input_index}",
                        "exclude",
                        "Chapter omission requires acknowledgement.",
                    )
                )

        plan = OperationPlan(
            sources,
            output,
            destination,
            selections,
            external_tracks,
            tuple(included),
            tuple(excluded),
            preserve_chapters,
            chapter_input,
            tuple(preservation),
            tuple(issues),
            acknowledged_warnings,
        )
        if plan.intrinsically_valid and not plan.pending_warnings:
            plan = replace(plan, arguments=build_arguments(plan))
        return plan

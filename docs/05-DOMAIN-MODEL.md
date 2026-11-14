# 05 — Domain Model

## Implemented PR-02 inspection entities

`domain/media.py` uses frozen dataclasses. Nested stream/chapter collections,
tags and dispositions are tuples; no mutable raw ffprobe dictionaries are exposed.

| Entity | Implemented fields |
| --- | --- |
| MediaSource | resolved Path, size_bytes, modified_time_ns |
| MediaFormat | name, long_name, duration_seconds, bit_rate_bps, tags |
| MediaAsset | source, format, ordered streams tuple, ordered chapters tuple |
| Stream | original index, normalized kind, codec, language, title, disposition, duration_seconds, properties, tags |
| StreamProperties | width/height, channels, sample_rate_hz, channel_layout, pixel_format, bit_rate_bps, codec_long_name, profile, time_base, average_frame_rate |
| Chapter | original id, start_seconds, end_seconds, title, tags |

The [public contract](13-INSPECTION-CONTRACT.md) defines types and units.
Indices are unique, source-local and unmodified; order is preserved independently
of index order. Attachment/data/unknown streams survive normalization. Zero audio,
zero subtitles and multiple video streams are valid inspection snapshots. Missing
scalar metadata stays None; unknown language codes and Unicode remain unchanged.
Inspection does not require video: future main-video output invariants below apply
to planning, not probing. Source size/mtime is rechecked after successful probing.

## Proposed future operation model

The following broader model is a planning baseline. The PR-03 section below identifies actual planning fields; execution/publication entities remain proposals.

| Entity / value object | Responsibility | Representative fields |
| --- | --- | --- |
| `MediaSource` | Immutable reference to a local input file | path, size, modifiedAt, probeVersion |
| `MediaAsset` | ffprobe inspection snapshot | formatName, duration, streams[], metadata, chapters |
| `Stream` | Identified input stream | sourceId, inputIndex, kind(video/audio/subtitle/attachment/data), codec, language?, title?, disposition, properties |
| `ExternalTrack` | Track from another local file | path, streamIndex, kind, format, metadata |
| `TrackSelection` | Inclusion, ordering and metadata intent | sourceStreamId, included, outputOrder, language?, title?, default?, codecAction |
| `OutputProfile` | Requested file format and destination | container(mkv/mp4), targetPath, overwritePolicy=reject |
| `CompatibilityIssue` | Warning or blocker | severity, streamId?, code, message, suggestedAction |
| `OperationPlan` | Reviewable intended operation | sources, selections[], profile, issues[], expectedStreams, planVersion |
| `ExecutionJob` | Concrete operation execution | jobId, status, progress?, startedAt, finishedAt, logRef?, temporaryPath |
| `ValidationReport` | Output verification evidence | expected/observed, checks[], passed, warnings[] |

## ExecutionJob state machine

`planned → running → validating → completed`

Cancellation: `running → cancelling → cancelled`.

Failures: `running` or `validating → failed`. A failed job may retain temporary output under a documented recovery policy. Never declare completion before validation and safe publication.

## Invariants

- Source files are never modified or deleted.
- A main video output requires at least one video stream in the MVP; **zero audio and zero subtitle streams are valid**. Audio-only output is a separate future decision.
- Every output stream has an explicit source or documented transformation.
- MVP video/audio operations are stream-copy or blocked. Supported text subtitle conversions are explicit.
- Blocking compatibility issues prevent execution. Any source/track/container change invalidates and rebuilds the plan.
- Existing final destinations are not overwritten unless a future approved policy explicitly changes this.
- Language tags should be normalized as appropriate for the output container while preserving unknown (`und`) languages and known metadata limitations.

## Persistence and interfaces

Optional local persistence for GUI preferences only; no relational database and no cloud service in the MVP. Operation plans and validation reports may be serialized to versioned JSON. CI logs must not contain personal media, private URLs, or user paths.

## Future domain extensions

Phase 1 adds `TranscodePlan` and codec/quality settings. Phase 2 adds `BatchJob`, reusable rules, and runtime capabilities. New entities must not make the MVP core depend on a GUI.

## Implemented PR-03 planning entities

| Entity | Actual responsibility |
| --- | --- |
| StreamReference | Full immutable PR-02 source identity plus original stream index |
| MetadataIntent | Optional language/title/default/forced changes; null preserves |
| TrackSelection | Reference, inclusion/exclusion and metadata; request order is explicit |
| ExternalTrack | Source, intended kind, optional inspected index/codec/format, metadata and validation claim |
| OutputProfile | Requested container and destination path |
| CompatibilityIssue | Stable code, severity, reference, message and suggestion |
| PreservationDecision | Category and preserve/modify/exclude/unsupported/uncertain status |
| PlannedStream | Original source stream, input/output indices, action, expected codec/tags/dispositions |
| ExcludedStream | Reference/source stream, explicit versus implicit exclusion, exclude action |
| OperationPlan | Sources, all intent, included/excluded streams, chapters, diagnostics, acknowledgements and proposed arguments |

PlannedStream carries the expected-output responsibilities; a second duplicate
ExpectedOutputStream model is unnecessary. Frozen tuples/frozensets keep snapshots
immutable. ExecutionJob and ValidationReport remain future implementation. Complete
fields, semantics and versioning are defined in [plan contract v1](14-OPERATION-PLAN-CONTRACT.md).

# 05 — Domain Model (Proposal v0.2)

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

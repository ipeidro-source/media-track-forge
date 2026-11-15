# External SRT, extraction, cancellation and progress - PR-05

> **Evolution note:** PR-08 extends compatibility and independent subtitle validation below without changing extraction presentation v1. Historical mentions of PR-06 as future are superseded by its merge; see [document 00](00-CURRENT-STATUS.md). Future safe NAS output requires a separate accepted architecture and genuine SMB tests.

D14-D18 are owner approved. PR-04 is merged at `3bea7ee` with successful main CI
[43614579922](https://github.com/ipeidro-source/media-track-forge/actions/runs/43614579922).
This branch adds backend APIs only. G3 requires independent owner review; GUI and
packaging remain PR-06/PR-07. No new runtime dependencies or media binaries are bundled.

## External SRT API and encoding

```python
inspector = InspectionService(FFprobeAdapter())
subtitle, external = ExternalSubtitleService(inspector).import_srt(
    "captions.srt", MetadataIntent(language="eng", title="English", default=True)
)
# Append subtitle to sources and external to external_tracks. Select its genuine index:
selection = TrackSelection(
    StreamReference(subtitle.source, external.stream_index), metadata=external.metadata
)
```

Imports require a readable regular local `.srt`, strict UTF-8 (optional UTF-8 BOM),
1 byte..8 MiB and at most 100,000 cues. Invalid UTF-8 is rejected, never guessed
as a legacy codepage. CRLF/LF/CR, blank separator whitespace, optional numeric cue
labels, gaps/overlap, nonsequential labels and ordinary inline markup are accepted.
Cue labels are not used as stream indices. Timing is `H..HHH:MM:SS,mmm --> ...`,
minutes/seconds 00..59, hours 0..999, start strictly before end. Every cue requires
nonempty text. NUL, ambiguous timing/settings, empty input and malformed blocks fail
with INVALID_EXTERNAL_SRT. No synchronization, markup interpretation, OCR or language
inference occurs. UTF-16/legacy encodings require explicit user conversion outside
the product. Cue evidence is an immutable domain value, not inspection metadata.

Structural validation and independent ffprobe inspection are both required. Exactly
one genuine subtitle/subrip stream and format `srt` must be inspected. Original stream
indices, source snapshots and source input ordering remain explicit. The importer
returns `(MediaAsset, ExternalTrack)`; it does not automatically select the track.
One or more imported sources can be appended; each is a distinct input. Language,
title, default and forced intent must match the explicit selection. Existing default
conflicts block; unknown language is not inferred from the filename.

Planning remains read-only plan v1, with unchanged ExternalTrack fields and warning
revision binding. Its caller validation claim is not execution authority. Execution
independently repeats SRT validation/inspection and checks the complete external
record before processing and publication. The primary source must have a selected
video; additional subtitle-only sources require validated external records. Audio
imports and raw subtitle-only bypasses remain blocked. Existing additional video
container input behavior remains supported. Every input/source role and ordering
participates in the revision; changed inputs or diagnostics require fresh review.

MKV copies SubRip. MP4 explicitly encodes it as mov_text and requires the existing
SUBTITLE_FORMATTING_MAY_CHANGE and applicable metadata uncertainty acknowledgements.
Video/audio remain copied. Explicit maps and stable within-kind requested order are
unchanged. A selected external cue extending beyond the video contributes its end
time to expected output container duration; it does not fabricate source metadata.

## Extraction matrix and declarative contract

Extraction has a separate `extraction_version: 1` presentation contract. It uses
the immutable OperationPlan primitives internally through ExtractionPlan, with an
explicit bitstream_filters tuple and a distinct revision including extraction_version.
It does not reuse the main-video invariant or broaden MKV/MP4 remux compatibility.

| Inspected source family | Codec/kind | Suffix | Actual muxer | Action/filter |
| --- | --- | --- | --- | --- |
| MP4 alias family, excluding MOV major_brand qt | H.264 video | .h264 | h264 | copy, h264_mp4toannexb |
| MP4 alias family, excluding MOV | HEVC video | .h265 | hevc | copy, hevc_mp4toannexb |
| MP4 alias family, excluding MOV | AAC LC audio | .aac | adts | copy, ADTS packaging |
| AVI / Matroska | MP3 audio | .mp3 | mp3 | copy |
| Matroska | SubRip subtitle | .srt | srt | copy |
| MP4 alias family, excluding MOV | mov_text subtitle | .srt | srt | explicit subtitle conversion |

Only these exact families/codecs/extensions are enabled, subject to mandatory real
tests on both integration platforms. AC-3, other AAC profiles, MKV H.264/HEVC/AAC
extraction, MOV and unknown combinations remain unsupported. The Annex B filters
are specific to the tested MP4-to-elementary paths; no filters are blindly applied
to arbitrary inputs. Bitstream filtering and ADTS framing are not audio/video
encoding. No video/audio encoder option is generated. Styling can change in mov_text
to SRT; its warning must be acknowledged. Elementary extraction explicitly excludes
container metadata, chapters and dispositions, also requiring acknowledgement.

```python
plan = ExtractionPlanningService().plan(asset, original_stream_reference, "output.h264")
# Display plan and obtain acknowledgement before calling again:
plan = ExtractionPlanningService().plan(
    asset,
    original_stream_reference,
    "output.h264",
    acknowledged_revision=plan.revision,
    acknowledged_warnings=frozenset(plan.pending_warnings),
)
# Only after separate final confirmation:
result = ExtractionExecutionService().execute(
    ExecutionRequest(plan, plan.revision, plan.revision), control=control
)
```

`extraction_document`/`serialize_extraction` emit extraction_version, revision, full
sources in inspection v1, one selection, output, included stream, bitstream_filters,
issues, acknowledged_revision, effective acknowledged_warnings, pending_warnings,
intrinsically_valid, execution_allowed, confirmation_required and arguments.
References, included streams, diagnostics and output objects use the field types
defined in document 14; output.container is the actual elementary muxer here.
Additive fields are compatible; renames/types/semantics require a new extraction
version. Deterministic ASCII-safe JSON has a regression round-trip test. Inspection
schema v1 and remux plan v1 serialization and diagnostic meanings are unchanged.

Exactly one selected original source index is mapped, independently of its position
or kind. Both regeneration boundaries independently reinspect and regenerate the
extraction policy/filter/destination/diagnostics and require the reviewed/confirmed
revision. Supplied arguments/derived fields are ignored. Blocked or unacknowledged
plans expose no executable arguments, and changed intent invalidates review.

## Shared execution and elementary validation

PR-08 supersedes subtitle packet equality below: bounded independent packet payload
scans decode SubRip or mov_text text and timing. Only mov_text zero-length text
samples are excluded as screen clears. Every nonempty source cue must match output
text and timing within one millisecond of SRT quantization; output packets must
match structurally valid SRT cues. Unsupported/malformed evidence fails with a
specific invariant code and EXTRACTION_INVALID. Audio/video retain positive equal
packet counts. Matroska MP3 to standalone MP3 is an additional tested extraction pair.
This does not waive timing, cleanup, source reinspection or exclusive publication.

ExtractionExecutionService specializes RemuxExecutionService's regeneration,
argument generation and validator selection. Both use the same staging, process,
timeout, cancellation, progress, confirmation, cleanup and exclusive-publication
implementation. There is no second subprocess-writing stack. Trusted ffprobe/FFmpeg
overrides and all document 15 filesystem/process assumptions apply unchanged.

Elementary validation requires a nonempty probeable regular file, exact actual
format, one expected kind/codec, no chapters and matching available technical
properties. A separate bounded ffprobe full packet scan counts the selected source
index and output index. Counts must be positive and equal; missing counts or a
failed scan block publication. SRT output is structurally validated and cue count
must match. MP4 subtitle clear/empty samples or other packet transformations that
do not satisfy this equality fail conservatively; arbitrary mov_text streams are
not promised. Unknown combinations never receive a misleading extension.

When comparable source/output durations exist, validation retains document 15's
metadata-derived timing check. AAC LC to ADTS additionally allows two 1024-sample
boundaries at the inspected sample rate for MP4 edit-list priming/end padding that
ADTS cannot express. No fixed universal duration tolerance is introduced.

Elementary formats can lack duration entirely. Extraction alone then uses the
independent complete equal packet scan plus exact codec/technical/layout checks as
truncation evidence and reports EXTRACTION_TIMING_PACKET_VERIFIED uncertainty.
This is an explicit operation-specific integrity alternative: simple truncation
loses packets even when raw elementary clocks are absent. It is not full decode,
cryptographic content identity, or a waiver for the remux duration policy. Remux
known duration without observed duration or a reliable budget still fails.

Mandatory extraction E2E additionally compares packet SHA-256 lists against an
independently produced reference with normalized Annex B/ADTS/subtitle framing.
Container edit lists, framing and metadata can differ; complete container bytes
need not match. This test evidence does not promise every profile/player/build.

## Cancellation and atomic commitment

Each operation receives its own ExecutionControl/CancellationToken. `cancel()` is
thread-safe; before commitment it returns true and requests cancellation, after
commitment it returns false. Do not reuse controls/tokens for another job. The
synchronous service can run on a caller worker thread; no GUI/scheduler is imported.

Cancellation is checked before staging/launch, during managed processing, after
processing, around validation and before publication. Blocking probing finishes
or reaches its configured timeout; the pending cancellation prevents publication.
Managed FFmpeg uses Windows Job Objects or Ubuntu process groups, then verifies
termination, reaps the root and joins pipe readers. Existing five-second termination
verification bounds and trust limitations remain. Cancelling/cancelled are distinct
from failed/timed_out; cancellation has precedence when request/deadline are first
observed together. A containment/termination failure wins over cancellation and
retains potentially active staging with cleanup_complete=false. Genuine validation
exceptions remain failed outcomes; they never authorize publication.

A short per-token lock linearizes cancel() against exclusive publication. Cancellation
received before acquiring the publication commitment prevents the link. A concurrent
cancel caller during this critical section waits: successful publication commits and
returns a truthful completed/published result; subsequent cancel returns false. A
failed publication does not commit. There are no callbacks or long media operations
under this lock. Never remove a published output as cancellation rollback. Cleanup
failure after commitment remains published=true/failed, as in PR-04.

## Progress observer

`ExecutionControl(listener=callback)` delivers frozen domain ProgressEvents on the
operation worker thread: phase, determinate, percent (0..100 or None), optional
processed_seconds, and terminal. Preparing/revalidation, running, validating,
publishing and terminal phases are reported; cancelling/cancelled are explicit.
ExecutionResult history retains the previous planned/running sequence for compatibility;
the new preparing phase is emitted to observers without altering successful histories.

FFmpeg runs with controlled `-progress pipe:1 -nostats`. The incremental ASCII parser
uses out_time_us/out_time_ms (both microseconds), handles split lines, ignores invalid/
negative/nonfinite values and caps a line at 4096 bytes. Only the latest valid time
is retained, with no event queue. Stdout is drained concurrently, retaining at most
64 KiB of bytes; stderr retains the existing 64 KiB hard limit. Progress overflow
fails safely. Worker delivery is at most ten periodic events/second plus phase
events. No arbitrary FFmpeg text is exposed. Callback exceptions disable that
observer and add PROGRESS_LISTENER_FAILED, without changing execution safety.

Listeners are trusted, synchronous and must return promptly: blocking callbacks can
delay cancellation/timeout observation. A future GUI should update a bounded latest
value, not block the worker or grow an unbounded queue. No application-owned progress
database/thread pool or callback-created storage is provided.

Reliable selected video/audio stream durations determine remux/extraction percentages;
source container duration is never blindly substituted for selected-stream duration.
Missing timing (including subtitle extraction) is indeterminate. Values are monotonic
within the operation and processing is capped at 99%; only completed after successful
validation, publication and normal cleanup emits 100%. Percent is an approximation,
not permission to publish. Callback failure/indeterminate status does not fabricate
duration or waive validation.

## Diagnostics, evidence and limitations

Existing stable codes keep their meaning. New codes include INVALID_EXTERNAL_SRT,
UNSUPPORTED_EXTRACTION, UNSUPPORTED_AAC_PROFILE, EXTRACTION_METADATA_EXCLUDED,
EXTRACTION_INVALID, EXTRACTION_LAYOUT, EXTRACTION_PACKET_COUNT,
EXTRACTION_TIMING_PACKET_VERIFIED, PROCESS_CANCELLED and PROGRESS_LISTENER_FAILED.
They are contextual bounded English diagnostics, without raw subprocess text.

Offline tests cover encoding/structure/resource limits, genuine references, exact
extraction mappings/policy/revisions, output rejection, cancellation boundaries and
thread races, ordinary descendant termination, bounded parser and observer failure.
Mandatory Windows 2025/Ubuntu 24.04 Python 3.12 E2E covers external SRT AC-03/04/05/11,
multiple subtitles, changed files, all enabled extraction pairs, collisions,
running remux/extraction cancellation AC-08, Unicode AC-09, commitment and progress.
The indeterminate real-remux test injects unavailable source timing while executing
real media; it does not claim the fixture naturally lacks timing. Existing suites
remain mandatory. Exact counts/builds/CI log conclusions belong in the PR evidence.

All PR-04 namespace, same-metadata source-identity, hard-link filesystem, private
ACL/mode, process-containment and crash-durability limitations remain. No OS sandbox,
full decoding, hostile executable containment, GUI, batch, external audio, video/audio
transcoding, packaging, tag or release is implemented. G3 acceptance remains with
the owner after independent review.

## D24 Windows file-share inputs

External SRT validation and independent probing also support trusted Windows UNC/
mapped regular files. Encoding, size/cue limits, genuine indices, source roles and
metadata/review/reinspection semantics are unchanged. Approved remux/extraction
operations may read those inputs and publish to supported local destinations only.
D24 changes input access, not the codec/container matrix (for example MKV H.264
elementary extraction remains outside the existing enabled matrix). No network
staging/publication, credential storage, protocol URLs or automatic mounting/copying.
See document 17 for timeout/cache/session limits and actual-share evidence procedure.

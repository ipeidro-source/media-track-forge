# OperationPlan contract - plan_version 1

PR-03 implements planning only. This contract is separate from inspection
`schema_version: 1`, whose fields and meaning remain unchanged. Domain snapshots
are frozen dataclasses with tuples/frozensets; public JSON uses objects and arrays.
The planning component has no CLI and does not execute FFmpeg or publish output; PR-04 consumes plans through the separate execution contract.

## Application API

```python
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.planning import OutputProfile, StreamReference, TrackSelection

selection = TrackSelection(StreamReference(asset.source, asset.streams[0].index))
plan = OperationPlanningService().plan((asset,), (selection,), OutputProfile("mkv", "output.mkv"))
```

The ordered `sources` tuple contains inspected PR-02 `MediaAsset` snapshots;
position zero is the primary source. Every position is its FFmpeg input index.
The service performs read-only source/destination filesystem checks but never
probes media, creates directories, calls FFmpeg or writes output files. The pure
compatibility policy and pure argument generator are separate components.

## Field definitions

| Field | JSON type | Meaning |
| --- | --- | --- |
| plan_version | integer | Exactly 1; independent of inspection schema version |
| revision | string | Lowercase SHA-256 fingerprint of the exact plan content described below |
| acknowledged_revision | string or null | Caller-supplied reviewed revision; missing/stale values grant no acknowledgement |
| sources | array | Complete, unmodified inspection schema v1 documents in FFmpeg input order |
| output | object | `container`: string mkv/mp4; `requested_path`: original string; `path`: resolved absolute local string or null on invalid input |
| selections | array | Requested order of `{reference, include: boolean, metadata}`; includes explicit exclusions and invalid requests for review |
| external_tracks | array | Extension records defined below; never fabricated from a filename |
| included | array | Supported proposed output streams in final deterministic mapping order; blocked requests remain in selections/issues/sources |
| excluded | array | `{reference, explicit: boolean, action: "exclude"}`; input order, visible omissions even for data/unknown kinds |
| preserve_chapters | boolean | Requested primary chapter preservation, default true |
| chapter_input_index | integer or null | 0 for validated primary-to-MKV chapter mapping, otherwise no chapter mapping |
| preservation | array | `{category: string, status, detail: string, reference: object or null}`; per-category explanation |
| issues | array | `{code, severity, message, suggestion, reference}` described below |
| intrinsically_valid | boolean | No issue of severity error; independent of acknowledgements |
| acknowledged_warnings | array of strings | Effective sorted acknowledged codes; empty when acknowledged_revision does not match revision |
| pending_warnings | array of strings | Sorted unique unacknowledged warning codes |
| execution_allowed | boolean | Intrinsically valid, all warnings acknowledged, and arguments generated; eligibility for a future confirmed/revalidated operation, not authorization to run now |
| confirmation_required | boolean | Always true in PR-03; final execution confirmation workflow is deferred |
| arguments | array of strings or null | Proposed subprocess argument array including ffmpeg executable name; null for errors or pending warnings |

A `reference` is `{source: {path: string, size_bytes: integer,
modified_time_ns: integer}, index: integer}`. Size is bytes; mtime is filesystem
nanoseconds since the Unix epoch. Path/size/mtime together identify the inspected
source snapshot, and index is the original ffprobe stream index. A reference is
never an output index or UI row. Matching requires the complete snapshot identity.

Selection `metadata` is `{language: string or null, title: string or null,
default: boolean or null, forced: boolean or null}`. Null means preserve available
source value, empty strings explicitly clear tags, and false explicitly clears a
flag. Unknown languages and `und` remain unnormalized. NUL bytes are rejected.
Source metadata remains separately available in `sources` and `PlannedStream.source_stream`.

Each `included` entry contains:

| Field | Type | Meaning |
| --- | --- | --- |
| reference | object | Original source snapshot and stream index |
| input_index | integer | Zero-based index in sources, used on the left of `-map` |
| output_index | integer | Zero-based final mapping position, independent of source index |
| kind | string | Original normalized stream kind |
| source_codec | string or null | Inspected codec |
| target_codec | string or null | Copy codec, mov_text for explicit subtitle conversion, null for validated opaque text attachment |
| action | string | copy or convert_subtitle; there is no audio/video encode action |
| output_tags | string-to-string object | Supported source tags plus explicit requested changes |
| output_disposition | string-to-integer object | Available/requested default/forced values, 0/1; missing source values not fabricated |

`ExternalTrack` fields: `source` (snapshot object), `intended_kind` (stream-kind
string), `stream_index` (integer or null), `codec` and `format_name` (string or
null), `metadata` (same intent object), `validated` (boolean). Unvalidated records
block with EXTERNAL_TRACK_NOT_VALIDATED. A validation claim must match an actual
supplied inspection source, original index, kind, codec and format; requested
external metadata must match its explicit selection. The caller owns validation
provenance; the planner does not import or parse SRT. A validated caller-supplied
snapshot can be mapped as a separate input without changing reference semantics.

## Selection, ordering and metadata

No stream is automatically selected. Duplicate/nonexistent references are errors.
Explicit `include=false` remains visible. Every other unselected source stream
is recorded as implicitly excluded and produces an acknowledgement warning.
At least one supported video stream must be selected; zero audio and zero subtitles
are valid. Multiple videos are supported. Grouping is video, audio, subtitle,
attachment; caller order is stable within each group. Selected data/unknown streams
and unsupported attachments/codecs block. No stream is silently converted to another kind.

Default conflicts are errors when more than one selected stream of the same kind
has effective default=1, including inherited values. The caller must resolve the
conflict explicitly; the service never picks a winner. Default/forced are the only
supported flags. Other nonzero flags produce a loss warning. Missing flags remain
absent in the domain, with a warning that a muxer may report zeros instead.

Preservation statuses are preserve, modify, exclude, unsupported, uncertain.
Language/title and validated attachment filename/mimetype are explicitly set.
Other stream tags and all global tags are excluded with warnings. MP4 language,
title and disposition round-tripping is marked uncertain. Matroska may omit an
explicit und language tag, also warned. Exact tag bytes and player behavior are
not promised. FFmpeg may generate its own container/encoder tags.

Only primary-source chapter time bounds and titles into MKV are enabled. Requested
time bounds are not guaranteed exact: FFmpeg may shift timestamps during muxing,
so CHAPTER_TIMESTAMPS_UNCERTAIN requires acknowledgement and output validation.
Chapter
mapping and per-chapter title metadata are explicit. Other chapter tags are
excluded with a warning; chapter IDs may change after muxing. Requested MP4 chapter
preservation blocks until validated (it can introduce extra data streams). Explicit
chapter exclusion and secondary-source chapters produce warnings. No chapter is
silently discarded. Selected MKV text/plain attachments require an inspected null
codec plus nonempty filename and matching mimetype; arbitrary fonts/images are
unvalidated. MP4 attachments are blocked.

## Compatibility allowlist and evidence requirements

| Kind/codec | MKV | MP4 |
| --- | --- | --- |
| h264 video | copy | copy |
| hevc video | copy | copy |
| mpeg4 video, including AVI input | copy | blocked |
| aac audio | copy | copy |
| mp3 audio | copy | copy |
| subrip subtitle | copy | convert_subtitle to mov_text, formatting warning |
| mov_text subtitle | blocked | copy |
| null-codec text/plain attachment with filename | copy | blocked |
| DTS, AC-3/E-AC-3, ASS/SSA, PGS/VobSub, other codecs/kinds | blocked | blocked |

AC-3/E-AC-3, DTS, ASS/SSA and bitmap subtitles remain unvalidated in this iteration;
the candidate list is not support evidence. Existing inspection fixtures using
FFV1/PCM do not establish output support, and both remain blocked by this policy.
AVI/MOV are input formats only. Decisions use inspected kind/codec, not extensions.

Every enabled entry is exercised by real, temporary FFmpeg muxing tests in
`tests/integration/test_planning_mux.py`. HEVC fixture generation requires libx265;
H.264 requires libx264 and MP3 fixtures require libmp3lame. Missing capabilities
fail rather than skip. Both required CI platforms must pass before readiness is
claimed. Exact tested builds, case counts and run URLs are recorded in the PR.
These tests validate sample muxing, not arbitrary profiles, bitstreams, player
compatibility or a universal runtime FFmpeg capability guarantee.

## Issue and acknowledgement rules

Severity is info, warning or error. `code` is a stable machine-readable string,
`message` is English, `suggestion` is string or null, and `reference` is a stream
reference or null for plan-wide issues. Ordering is deterministic for the same
snapshots, request and filesystem state. Current error codes include:

```text
NO_SOURCE DUPLICATE_SOURCE SOURCE_CHANGED INVALID_SOURCE INVALID_STREAM_IDENTITY
EXTERNAL_TRACK_NOT_VALIDATED EXTERNAL_METADATA_CONFLICT UNSUPPORTED_OUTPUT_CONTAINER
OUTPUT_EXTENSION_MISMATCH DESTINATION_EXISTS SOURCE_DESTINATION_CONFLICT
INVALID_DESTINATION DUPLICATE_SELECTION UNKNOWN_STREAM_REFERENCE
UNSUPPORTED_CODEC_FOR_CONTAINER INVALID_METADATA VIDEO_REQUIRED
CONFLICTING_DEFAULT_FLAGS CHAPTER_COPY_UNVALIDATED
```

Current warning codes:

```text
FORMAT_METADATA_EXCLUDED STREAM_METADATA_EXCLUDED LANGUAGE_UND_UNCERTAIN
DISPOSITION_LOSS DISPOSITION_ABSENCE_UNCERTAIN MP4_METADATA_UNCERTAIN
SUBTITLE_FORMATTING_MAY_CHANGE STREAM_IMPLICITLY_OMITTED CHAPTERS_EXCLUDED
CHAPTER_METADATA_EXCLUDED CHAPTER_TIMESTAMPS_UNCERTAIN
```

Warnings require both their codes and the exact reviewed `revision`. First generate
and review a plan with no acknowledgement. Regenerate the same request with
`acknowledged_warnings=frozenset(reviewed.pending_warnings)` and
`acknowledged_revision=reviewed.revision`. Codes alone, or codes paired with a
different revision, grant no acknowledgement and produce no executable arguments.
A matching revision acknowledges all occurrences of the submitted codes within
that exact diagnostic set; submitting only some codes leaves the others pending.
Acknowledgements never override errors. Final execution confirmation remains
separate (`confirmation_required=true`), with no GUI or execution workflow added.

The revision hashes the domain dataclass content, including plan_version, full
inspection snapshots, ordered sources/selections/external tracks, metadata intent,
requested and normalized destination, container, chapter policy, included/excluded
mappings, preservation decisions, and complete ordered diagnostics (codes, severity,
references, messages, suggestions and occurrence counts). Thus even a change that
leaves the same warning codes requires fresh review. Canonical encoding uses
sorted JSON keys, compact separators, ASCII escapes, finite numbers, native path
strings, UTF-8 bytes and SHA-256. Only acknowledgement state and generated arguments
are excluded, so applying acknowledgement does not change the revision or create
a hash cycle. Identical intent/snapshots/diagnostics produce the same revision.

The public revision is opaque: obtain it from the planner rather than hash the
presentation JSON. It is an equality binding, not a secret or authorization token,
not a file-content hash, and not persisted execution confirmation. Plans with no
warnings need no acknowledgement. Immutable replacements cannot retain arguments
if errors or unacknowledged warnings result. Source/path races still require future
execution-time revalidation.

## Proposed arguments and destination safety

Commands use explicit input positions and source indices, `-map` for every stream,
per-output-index `-c:N copy` or subtitle-only mov_text, explicit dispositions and
metadata, chapter mappings, fixed muxer and `-n` (never overwrite). Global and
per-stream metadata auto-copy are disabled. `-protocol_whitelist file` applies to
each input, and stdin is disabled. The generator rejects blocked/unacknowledged
plans independently. It never calls subprocess or constructs a shell command.
Options follow [official FFmpeg documentation](https://ffmpeg.org/ffmpeg.html).

Planning normalizes local paths, rejects empty/URL/UNC outputs, mismatched
extensions, existing destinations (including aliases), source/output conflicts
across primary/additional/external sources, and invalid Windows path components.
Windows comparisons fold case. No overwrite option exists. No directory is
created. Missing parents are not created and writeability/free space is not
guaranteed. Mapped/network filesystems and path races retain PR-02 limitations.
All identities, collisions and destination conditions must be revalidated by a
future executor immediately before any write. Size/mtime is not a cryptographic
concurrency guarantee. Proposed direct destination arguments are not a staged,
validated publication algorithm; executing them in product code is out of scope.

## Versioning and complete example

`ui.operation_plan_json` exposes `plan_document` and `serialize_plan`. Keys are
sorted, Unicode is escaped safely, arrays retain specified order, and nonfinite
numbers are rejected. Missing scalars are null; absent collections are empty.
Additive fields/codes may be introduced compatibly; consumers must ignore unknown
fields/codes and honor severity. Removing/renaming fields, changing types/units,
reference, mapping, action or acknowledgement semantics requires a new plan_version.
Inspection schema v1 is unaffected. This acknowledgement correction is part of
the unmerged PR-03 review, establishing the initial plan_version 1 semantics;
it is not a change to an accepted/released contract. The example revision below
is illustrative and must not be used to acknowledge a real request.

The complete example below contains one explicitly selected H.264 video stream,
no audio/subtitles/chapters, no source metadata to lose and no warnings. Paths and
snapshot numbers are illustrative, not filesystem or execution guarantees.


```json
{
  "plan_version": 1,
  "revision": "0000000000000000000000000000000000000000000000000000000000000000",
  "acknowledged_revision": null,
  "sources": [
    {
      "schema_version": 1,
      "source": {
        "path": "/examples/source.mkv",
        "size_bytes": 7,
        "modified_time_ns": 1794667285644668300
      },
      "format": {
        "name": null,
        "long_name": null,
        "duration_seconds": null,
        "bit_rate_bps": null,
        "tags": {}
      },
      "streams": [
        {
          "index": 5,
          "kind": "video",
          "codec": "h264",
          "language": null,
          "title": null,
          "disposition": {
            "default": 0,
            "forced": 0
          },
          "duration_seconds": null,
          "properties": {
            "width": null,
            "height": null,
            "channels": null,
            "sample_rate_hz": null,
            "channel_layout": null,
            "pixel_format": null,
            "bit_rate_bps": null,
            "codec_long_name": null,
            "profile": null,
            "time_base": null,
            "average_frame_rate": null
          },
          "tags": {}
        }
      ],
      "chapters": []
    }
  ],
  "output": {
    "container": "mkv",
    "requested_path": "/examples/output.mkv",
    "path": "/examples/output.mkv"
  },
  "selections": [
    {
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      },
      "include": true,
      "metadata": {
        "language": null,
        "title": null,
        "default": null,
        "forced": null
      }
    }
  ],
  "external_tracks": [],
  "included": [
    {
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      },
      "input_index": 0,
      "output_index": 0,
      "kind": "video",
      "source_codec": "h264",
      "target_codec": "h264",
      "action": "copy",
      "output_tags": {},
      "output_disposition": {
        "default": 0,
        "forced": 0
      }
    }
  ],
  "excluded": [],
  "preserve_chapters": true,
  "chapter_input_index": null,
  "preservation": [
    {
      "category": "format_tags:0",
      "status": "exclude",
      "detail": "Global metadata auto-copy is disabled.",
      "reference": null
    },
    {
      "category": "language",
      "status": "preserve",
      "detail": "Preserve available value; no missing value is invented.",
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      }
    },
    {
      "category": "title",
      "status": "preserve",
      "detail": "Preserve available value; no missing value is invented.",
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      }
    },
    {
      "category": "other_tags",
      "status": "preserve",
      "detail": "Only language/title and validated attachment filename/MIME tags are copied.",
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      }
    },
    {
      "category": "default",
      "status": "preserve",
      "detail": "Explicit flag intent; missing source flags remain absent in the snapshot.",
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      }
    },
    {
      "category": "forced",
      "status": "preserve",
      "detail": "Explicit flag intent; missing source flags remain absent in the snapshot.",
      "reference": {
        "source": {
          "path": "/examples/source.mkv",
          "size_bytes": 7,
          "modified_time_ns": 1794667285644668300
        },
        "index": 5
      }
    }
  ],
  "issues": [],
  "intrinsically_valid": true,
  "acknowledged_warnings": [],
  "pending_warnings": [],
  "execution_allowed": true,
  "confirmation_required": true,
  "arguments": [
    "ffmpeg",
    "-nostdin",
    "-v",
    "error",
    "-n",
    "-protocol_whitelist",
    "file",
    "-i",
    "/examples/source.mkv",
    "-map",
    "0:5",
    "-map_metadata",
    "-1",
    "-map_metadata:s",
    "-1",
    "-map_chapters",
    "-1",
    "-c:0",
    "copy",
    "-disposition:0",
    "0",
    "-f",
    "matroska",
    "/examples/output.mkv"
  ]
}
```

## PR-04 consumption boundary

PR-03 plans remain declarative and contract v1 is unchanged. PR-04's separate
RemuxExecutionService requires an ExecutionRequest with exact reviewed and confirmed
revisions, fresh source inspections, trusted regeneration and effective warning
acknowledgements. It never trusts supplied arguments or execution_allowed as
authorization, including immutable copies retaining a stale tuple. Proposed direct
destination arguments are not executed: a controlled infrastructure boundary
binds fresh mappings to an exclusive owned staging file, validates it and publishes
exclusively. See [execution contract](15-EXECUTION-AND-VALIDATION-CONTRACT.md).

## PR-05 compatible external execution

The plan v1 schema and revision semantics are unchanged. ExternalSubtitleService
now supplies genuinely structurally validated and independently inspected SRT source/
ExternalTrack pairs. Planning remains read-only and still verifies matching snapshot
claims and explicit selections. Execution independently revalidates their provenance
before processing/publication; caller validated=true alone never authorizes import.
Multiple sources retain exact source ordering and original indices. Separate
extraction_version 1 serialization does not overload this remux JSON contract.
See document 16 for APIs, external source roles and cancellation/confirmation rules.

## D24 Windows network sources

Trusted mapped/UNC inputs and external SRT retain their canonical resolved source
snapshots and original indices in the same plan v1 contract. Source order, complete
inspections and diagnostics remain revision-bound. New normalization/changed source
snapshots require fresh review; drive aliases cannot redirect confirmed canonical
inputs. Output paths remain local-only: UNC and native Windows remote/unknown
volumes block before staging and are checked again before publication. File-share
input support does not broaden codecs, extraction formats or publication semantics.

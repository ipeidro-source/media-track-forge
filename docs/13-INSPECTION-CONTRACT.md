# Inspection JSON contract - schema version 1

PR-02 implements inspection only for FR-01 and FR-02. It does not establish output
container compatibility, track editing or any remux/extraction acceptance criterion.

## Invocation and output

```powershell
mediatrack-forge inspect "C:\Media\example.mp4"
python -m mediatrack_forge inspect "C:\Media\example.mp4" --ffprobe "C:\Tools\ffprobe.exe" --timeout-seconds 30
```

Both entry points use the same implementation. Global `--help` and `--version`
remain supported; no command prints help with exit 0. Options belong after `inspect`.
Success emits exactly one JSON document plus a newline on stdout and exits 0.
Errors emit a concise English message on stderr, no JSON, and no ordinary traceback.

| Exit | Meaning |
| --- | --- |
| 2 | Invalid arguments, nonfinite/nonpositive timeout, invalid/unreadable local path |
| 3 | Missing or unusable ffprobe executable |
| 4 | ffprobe nonzero exit: invalid, unreadable or unsupported media, blocked protocol, or source identity changed during inspection |
| 5 | ffprobe exceeded its wall-clock timeout (default 30 seconds) |
| 6 | Invalid UTF-8/JSON, unusable structure or captured output exceeded safety limits |

## Complete field definitions

All fields below are always emitted. Missing/unusable optional scalar metadata is
`null`; absent collections are `[]` or `{}`. Unknown ffprobe fields are ignored.
No codec, duration, language, flag or other technical value is inferred.

| Top-level field | Type | Meaning |
| --- | --- | --- |
| schema_version | integer | Exactly `1` |
| source | object | Source snapshot, defined below |
| format | object | Normalized container metadata |
| streams | array of objects | Original ffprobe order, including unknown/attachment/data streams |
| chapters | array of objects | Original ffprobe order; absent chapters become `[]` |

| source field | Type | Meaning / unit |
| --- | --- | --- |
| path | string | Resolved absolute native local path; symlinks resolved |
| size_bytes | integer | Filesystem size in bytes, not ffprobe's reported size |
| modified_time_ns | integer | Filesystem mtime in nanoseconds since Unix epoch; precision depends on filesystem |

| format field | Type | Meaning / unit |
| --- | --- | --- |
| name | string or null | ffprobe format_name, including comma-separated aliases |
| long_name | string or null | ffprobe human-readable format name |
| duration_seconds | number or null | Finite ffprobe duration in seconds; no estimate is fabricated |
| bit_rate_bps | integer or null | Available nonnegative container bitrate in bits/second |
| tags | string-to-string object | Available tag names/values preserved verbatim, including Unicode |

| stream field | Type | Meaning / unit |
| --- | --- | --- |
| index | integer | Original nonnegative ffprobe index; unique within snapshot, not renumbered by kind |
| kind | string | video, audio, subtitle, attachment, data, or unknown; unrecognized/missing types normalize to unknown |
| codec | string or null | ffprobe codec_name |
| language | string or null | Exact `language` tag; preserves unknown codes and `und`, without case/code conversion |
| title | string or null | Exact `title` tag |
| disposition | string-to-integer object | All available flags, including unfamiliar flag names; values 0/1; absent flags are not invented |
| duration_seconds | number or null | Finite per-stream duration in seconds; format duration is not substituted |
| properties | object | Technical fields below; not raw ffprobe output |
| tags | string-to-string object | All available string tags; non-string values are ignored |

Every `properties` object contains all of these fields:

| Property | Type | Meaning / unit |
| --- | --- | --- |
| width, height | integer or null | Nonnegative coded dimensions in pixels |
| channels | integer or null | Nonnegative audio channel count |
| sample_rate_hz | integer or null | Nonnegative sample rate in Hz |
| channel_layout | string or null | ffprobe channel layout name |
| pixel_format | string or null | ffprobe pix_fmt |
| bit_rate_bps | integer or null | Nonnegative stream bitrate in bits/second |
| codec_long_name | string or null | Human-readable codec name |
| profile | string or null | Available codec profile name |
| time_base | string or null | ffprobe rational notation for seconds per timestamp tick; uninterpreted, e.g. `1/1000` |
| average_frame_rate | string or null | ffprobe avg_frame_rate rational notation in frames/second; uninterpreted, `0/0` remains unknown as reported |

| chapter field | Type | Meaning / unit |
| --- | --- | --- |
| id | integer | Original ffprobe chapter ID, not its position in the array |
| start_seconds, end_seconds | number or null | Finite chapter start/end time in seconds |
| title | string or null | Exact chapter title tag |
| tags | string-to-string object | Available chapter tags |

Required input structure: an object containing a format object and streams array.
Each stream requires a nonnegative integer index; duplicates are rejected. Chapters
may be omitted but, when present, must be an array of objects with integer IDs.
Optional numeric `N/A`, nonnumeric and nonfinite values normalize to null. Metadata
objects/collections with incorrect types and noninteger/nonbinary disposition flags
are structurally unusable (exit 6). JSON null is not a substitute for a required
object/array. An empty streams array is allowed; no media-stream minimum is invented.

## Representative document

```json
{
  "schema_version": 1,
  "source": {"path": "C:\\Media\\silent.mp4", "size_bytes": 2048, "modified_time_ns": 1794657600000000000},
  "format": {"name": "mov,mp4,m4a,3gp,3g2,mj2", "long_name": "QuickTime / MOV", "duration_seconds": 0.4, "bit_rate_bps": null, "tags": {}},
  "streams": [{
    "index": 0, "kind": "video", "codec": "mpeg4", "language": "und", "title": null,
    "disposition": {"default": 1}, "duration_seconds": 0.4,
    "properties": {"width": 64, "height": 48, "channels": null, "sample_rate_hz": null, "channel_layout": null, "pixel_format": "yuv420p", "bit_rate_bps": null, "codec_long_name": "MPEG-4 part 2", "profile": "Simple Profile", "time_base": "1/10240", "average_frame_rate": "10/1"},
    "tags": {"language": "und"}
  }],
  "chapters": []
}
```

This is illustrative metadata, not a promised FFmpeg build or codec/container policy.
Serialization sorts object keys, uses ASCII Unicode escapes, rejects nonfinite JSON
numbers and preserves array order. Identical normalized snapshots serialize
identically. Escapes preserve Unicode even on Windows legacy-codepage consoles.
Consumers must accept additive fields/flag names and additional array entries.
Renaming/removing fields, changing types, units or existing semantics requires a
new schema_version. No undocumented raw ffprobe object is part of the API.

## Execution, safety and limitations

The product uses PATH discovery or the trusted `--ffprobe` override, a subprocess
argument array with `shell=False`, detached stdin, and:

```text
ffprobe -v error -protocol_whitelist file -of json -show_format -show_streams -show_chapters -i <absolute-path>
```

Options are verified against [ffprobe documentation](https://ffmpeg.org/ffprobe.html)
and the [protocol whitelist documentation](https://ffmpeg.org/ffmpeg-protocols.html#Protocol-Options).
The supported synthetic containers are tested against the real binary in CI.
Remote URLs, protocol-style paths and UNC paths are rejected before execution.
Nested HTTP access is rejected by the file-only whitelist. The whitelist is not
an OS filesystem sandbox: local references can read other local files, and mounted
network filesystems or mapped drives cannot reliably be identified as remote by
this path policy. Use trusted local media and executables. No ffprobe binary is
bundled, and FFmpeg is never invoked by the product.

Captured stdout is capped at 8 MiB and stderr at 64 KiB, with concurrent draining
and termination on overflow. Raw diagnostics are never printed; bounded English
errors avoid leaking arbitrary filenames or embedded metadata. Timeout/overflow
kills and reaps the ffprobe process; a trusted override that spawns descendants is
not sandboxed or guaranteed process-tree cleanup. ffprobe's own decode memory/CPU
is not OS resource-limited. Process execution has the timeout; parsing and source
filesystem calls are not interrupted by it.

The service compares resolved path, size and mtime before/after inspection; a
changed/unavailable source fails safely. It never opens media for writing.
Integration tests also compare file content/hash. Size/mtime checks are not a
cryptographic identity and cannot prevent every concurrent replacement race.
No guarantee of stream indices remaining valid after a file changes is made.

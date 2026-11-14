# 03 — MVP Functional Requirements and Acceptance Criteria

## Input and inspection

- **FR-01:** Open local AVI, MP4, MKV, MOV, and other ffprobe-readable media. Display a clear error for unreadable files. Acceptance of an input format does not guarantee every output conversion.
- **FR-02:** Support video with zero audio streams and zero subtitle streams. Display all detected video, audio, and subtitle tracks with index, type, codec, language, title, and default/disposition details.
- **FR-03:** Add external supported tracks by selecting local files. **SRT subtitle input is mandatory for the MVP**; external audio input is optional until verified fully.
- **FR-04:** Allow retaining zero audio streams, zero subtitle streams, and one or more video streams when the destination container supports them. Audio must never be mandatory.

## Stream editing and output

- **FR-05:** Explicitly retain/remove tracks, reorder tracks within their types, and set supported language, title, and default metadata.
- **FR-06:** Remux without re-encoding video or audio when the output container supports the codecs. MKV and MP4 are output formats; AVI is initially input-only.
- **FR-07:** For MP4, convert supported text subtitles to `mov_text` after warning that styling may change. For MKV, copy compatible SRT subtitle streams. Never silently convert bitmap subtitle images to text.
- **FR-08:** Extract an individual stream to a codec-appropriate file if FFmpeg supports lossless extraction; explain codec, extension, or bitstream-filter limitations.
- **FR-09:** Let the user choose an output destination and filename. Reject unsafe overwrites; never modify the original.
- **FR-10:** Show a complete pre-execution plan: sources, streams to retain/remove/add, codecs, subtitle conversions, destination, warnings, and actionable errors. Require confirmation.

## Execution and reliability

- **FR-11:** Execute work outside the UI thread; display progress where available and support safe cancellation.
- **FR-12:** Generate explicit FFmpeg `-map` entries, copying compatible video/audio streams (`-c copy`). No video/audio encoders in the MVP.
- **FR-13:** Probe output with ffprobe: existence, expected container, reasonable duration, stream count/types, codec mapping, language tags and output ordering. Document metadata uncertainty.
- **FR-14:** Write to a temporary destination; validate before publishing; preserve diagnostic information on failure, and never publish partial or corrupt output.
- **FR-15:** Support Windows 10/11 x64 with an accessible, understandable GUI, file selection, stream list, and helpful errors.

## Mandatory end-to-end scenarios

| ID | Input | Action | Expected result |
| --- | --- | --- | --- |
| AC-01 | H.264/AAC MP4 | Remove all audio | Video-only MP4 |
| AC-02 | Multi-track MKV | Keep one audio, remove others and subtitles | Exactly selected streams; no video/audio transcoding |
| AC-03 | Xvid/MP3 AVI | Add SRT, output MKV | Valid MKV if the streams can be copied; video quality unchanged |
| AC-04 | MP4 with audio plus SRT | Output MP4 | `mov_text` subtitle and copied compatible video/audio |
| AC-05 | Silent video | Add SRT, output MKV | Video plus subtitle; zero audio streams |
| AC-06 | Input incompatible with MP4 stream-copy | Choose MP4 | Block plan and suggest MKV; no implicit video/audio encoding |
| AC-07 | Input path equals output path | Attempt execution | Reject before writing |
| AC-08 | Running remux | Cancel | Original intact; no corrupt final output |
| AC-09 | Unicode/space-containing paths | Remux | Valid output using safe subprocess arguments |
| AC-10 | Multiple video streams | Retain only one | Correct chosen video stream and consistent metadata |
| AC-11 | Malformed external subtitle file | Import SRT | Contextual error; no published output |
| AC-12 | Target file already exists | Execute | Block or request a new filename; no overwrite by default |

## Non-functional requirements

- No telemetry by default; local-only operation if FFmpeg and ffprobe are installed.
- Responsive UI, Unicode Windows path handling, ffprobe timeouts, minimized diagnostic logs, Windows CI.
- No copyrighted fixtures, personal media, secrets, or downloads required by automated tests.

## Definition of done

Every mandatory AC must have repeatable tests and recorded results, including representative real FFmpeg/ffprobe invocations. A passed smoke test alone is insufficient.

## PR-03 planning-only coverage

FR-04/05/06/07/09/10/12 have explicit planning coverage: video-only selection,
stream ordering, metadata intent, conservative codec policy, subtitle conversion
warnings, destination checks, reviewable plans and exact mappings. Tests named
for AC-01/02/03/04/05/06/07/10/12 cover only their planning portions. Actual remux,
external subtitle import, output validation/publication and end-user confirmation
remain deferred; no full E2E acceptance criterion is declared passed here.

## PR-04 execution coverage

The application service executes the existing policy for FR-04/05/06/07/09/10/11/
12/13/14 using revision-bound confirmation, private staging, independent validation
and exclusive publication. E2E tests cover the applicable remux/safety behavior of
AC-01/02/06/07/09/10/12, including original hashes and destination races. AVI-to-MKV
and internal SubRip conversion cover remux portions only of AC-03/04. Full external
SRT AC-03/04/05 and cancellation AC-08 remain pending, as do GUI acceptance and
extraction. No complete MVP or G3 acceptance is claimed from these results alone.

## PR-05 backend coverage

External SRT and remux E2E address FR-03 and AC-03/04/05/11. Extraction tests
exercise FR-08 for every enabled codec/source/output pair. Backend cancellation
and progress address FR-11 and AC-08 using the shared confirmed/safe pipeline
for FR-09/10/12/13/14. Unicode paths continue AC-09 coverage. Mandatory real tests
retain original hashes, inspect actual outputs and check cleanup/collisions.
Exact enabled combinations, evidence boundaries and diagnostics are in document 16.
No GUI interaction, full FR-15, packaging, complete MVP or owner G3 acceptance is
claimed. Exact final test counts and platform results belong in the PR.

## PR-06 user-interface coverage

The desktop exposes FR-01..05/08..11/15 and the existing FR-06/07/12..14 backend.
Display-independent real-service journeys cover AC-01..12 plus extraction; native
Tk tests separately cover controls/review/confirmation/progress/cancel/close and one
real video-only operation. Controlled GUI fakes are not FFmpeg evidence. Exact
counts/platform runs belong in the PR. Manual Windows 10/11 keyboard/accessibility/
OS-DPI checks and packaging remain acceptance requirements; no full MVP is claimed.

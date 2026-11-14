# 07 — Quality and Test Strategy

## Test pyramid

1. **Unit tests:** ffprobe parsing, languages, stream mapping, compatibility policy, destination collisions, and job state transitions.
2. **Local integration:** create tiny synthetic fixtures with FFmpeg (`lavfi` test sources, tones, sample SRT files) and verify them with ffprobe; no network calls.
3. **Windows E2E:** real FFmpeg/ffprobe, subprocess cancellation, Unicode and spaced paths, temporary-output safety.
4. **GUI smoke:** create a window, inspect sample media, display tracks, preview a plan and execute a short sample case.

## Minimum coverage matrix

- H.264/AAC MP4 with one and multiple streams; video-only MP4.
- MKV with multiple audio/subtitle streams and supported SRT; optional ASS only if explicitly supported.
- Synthetic AVI with a stream-copy compatible path to MKV.
- Unknown/data/attachment streams, chapters, missing language metadata, malformed subtitles.
- Incompatible codec/container, truncated input, missing FFmpeg, unwritable destination, low disk space, and permission errors.
- Cancellation, process failure, retry, occupied output filename, Unicode paths.

## Result validation

Compare expected/observed stream types, number, codec identifiers, language tags, default/disposition data, ordering, duration within documented tolerances, and ffprobe readability. Add partial decoding tests where critical. Changing containers does not imply byte-identical container files.

## CI and releases

Use Windows CI for tests, lint, typing and media integration cases. A secondary Ubuntu job may test cross-platform non-GUI logic. Explicitly declare supported Python versions.

Do not publish a Release on every merge. A manual version tag triggers a validated release workflow only after the owner explicitly authorizes release. Review dependency versions, notices, license obligations, Dependabot, and security tooling as appropriate.

## PR quality checklist

- Summarize the problem and linked requirements.
- Include/update tests and documentation for affected behaviors.
- Report exact checks performed and observed results.
- Do not commit personal media, real copyrighted test content, secrets, or large binaries.
- Keep public API and JSON contracts documented when they change.

## Definition of done for MVP

All AC-01 through AC-12 pass with evidence; the original files are verified unchanged on failure/cancel; GUI and Windows packaging are smoke-tested; the user approves publishing a release.

## PR-01 implemented foundation

See [development and delivery](12-DEVELOPMENT-AND-DELIVERY.md) for setup, the Python
matrix, verified Node 24 Actions, runner images and CI log requirements. No release
workflow is enabled. GUI, output operation and executable validation remain deferred.

## PR-02 inspection tests

Unit tests run separately without media tools on all four matrix combinations.
They cover stream identities/order/kinds, missing and Unicode metadata, the full
JSON schema, frozen snapshots, malformed/invalid responses, path validation,
CLI stdout/exit codes, safe arguments, process errors/timeouts and capture limits.

Real integration runs on Windows 2025 and Ubuntu 24.04 / Python 3.12. Subsecond
fixtures cover MP4 with audio, video-only MP4, AVI, MOV and MKV with two audio
tracks, subtitle, attachment, chapter and Unicode metadata. Dimensions, codecs,
sample rates, formats, indices, dispositions, module CLI and unchanged source
identity/content are checked. A local HLS playlist verifies HTTP is rejected by
the file-only whitelist without a network request. Missing tools or required
fixture encoders fail the suite, and no media cases use skip/xfail.

Fixture encoders are checked before use: native mpeg4, aac, pcm_s16le, ffv1 and srt.
This validates specific inspection samples, not arbitrary codec/container output
compatibility. No AC-01 through AC-12 media-editing scenario is claimed complete.

## PR-03 planning and compatibility validation

Offline unit tests cover explicit identity/order, video-only plans, default
conflicts, metadata intent/loss, external validation, destination collisions,
unknown codecs/kinds, immutable serialization and command safety. Planning-only
AC-01/02/03/04/05/06/07/10/12 coverage is named explicitly in tests.
`test_planning_mux.py` tests every enabled allowlist entry using tiny local media:
H.264/HEVC with AAC or MP3, MPEG-4 Part 2/MP3 AVI, SubRip copying/mov_text conversion,
mov_text copying, multi-video/video-only output and MKV chapter/text attachments.
Fixture encoders libx264/libx265/libmp3lame/mov_text are required, never skipped.
Only the test harness executes generated arguments against temporary files and
probes expected streams/codecs/metadata. Source hashes and identities are compared.
The matrix-to-test check prevents enabling an unrepresented codec entry. Existing
mandatory Windows/Ubuntu Python 3.12 integration jobs run all cases unchanged.

The mixed H.264/AAC chapter fixture permits 50 ms timestamp movement because hosted
FFmpeg 6.1.1 applied an approximately 21 ms offset. Plans report this as uncertain
and require acknowledgement. This test tolerance does not implement or preapprove
the future output validator's general timing policy.

## PR-04 execution tests

New offline tests inject inspection/process/validation boundaries and exercise
local staging, collisions, ownership, error cleanup and revision-bound confirmation.
Python-only managed process tests verify no shell, capture bounds, nonzero exit,
timeout and ordinary descendant writers. Dangling-link unit checks inject lexists
for unprivileged Windows portability; they are not falsely reported as real
symlink-creation evidence. No tests use hidden skips.

Mandatory product-level E2E cases in test_execution_e2e.py use real FFmpeg/ffprobe:
video-only MP4, multi-audio selection, AVI-to-MKV, internal subtitle conversion,
chosen video, metadata/chapters/attachments, incompatible/same/existing destinations,
last-moment publication races, Unicode, injected failures, real managed timeout,
and incorrect staged-output rejection. Original content hashes are checked;
selected video-only/AVI cases also compare copied packet hashes. Tool and filesystem
versions are printed in hosted logs. Neither local tests nor ffprobe metadata alone
establish full decoding, universal filesystem durability or completed G3 scope.

## PR-05 regression and real-media evidence

test_pr05.py covers bounded SRT parsing, exact extraction policies/maps, stale review,
invalid output, cancellation phases/linearization/descendants and progress handling.
test_pr05_e2e.py adds real product external-SRT remux, all enabled extraction pairs,
changed subtitle rejection, remux/extraction cancellation, destination races and
progress/commitment evidence. It uses synthetic fixtures, hashes originals, compares
normalized packet hashes and checks final format/layout/cleanup. Indeterminate
progress injects missing source timing while running real media, explicitly.
All prior suites remain mandatory; unit cases run across the complete matrix and
real media on both Python 3.12 platforms, without hidden skips. Exact counts, tools,
filesystems, run URLs and complete-log findings belong in the PR. No GUI acceptance
or complete decoding guarantee is inferred from these tests.

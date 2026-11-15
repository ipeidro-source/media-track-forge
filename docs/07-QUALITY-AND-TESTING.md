# 07 — Quality and Test Strategy

Current evidence, acceptance gaps and gate statuses: [document 00](00-CURRENT-STATUS.md). Simulated D24 UNC cases do **not** prove real SMB access; hosted Windows Server 2025 GUI tests do **not** certify Windows 10/11 usability or OS DPI. The human usability protocol is [document 18](18-UX-VALIDATION.md). Any future NAS output implementation requires separate real-SMB safety/failure tests.

## Test pyramid

PR-08 adds local synthetic index-3 MP4 and index-5 MKV gapped subtitle extraction,
independent cue evidence, metadata keep/edit/clear round trips and VP9/Opus copy
coverage. These do not establish exact owner-file or SMB acceptance. Specific failed
validation invariants must remain observable without exposing raw vendor output.

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

## PR-06 desktop test layers

Headless controller/worker tests require neither Tk nor FFmpeg and run on the full
matrix. Real-service desktop orchestration runs with the existing synthetic media
integration suite on both Python 3.12 platforms. Native Windows GUI tests are
explicitly invoked with `python -m pytest tests/gui -v -s` in Windows 3.12 CI.
Default pytest discovery covers unit/integration only, with no Linux display.
Each native scenario runs in an isolated process with one root; failures are not
silently skipped. Controlled widget cases and a real GUI-to-backend video-only
operation are identified separately. Actual tests, counts and full CI log review
belong in the PR. Manual Windows 10/11 OS-DPI, keyboard and screen-reader acceptance
is still required; see document 17. A native Tk test is not desktop certification.

## D24 network input evidence boundary

test_network_sources.py is offline Windows-path/volume simulation with a local
backing file, including source/SRT identity, change/failure, exact mapping and
local-only staging/publication regressions. It is not SMB transport evidence.
check_network_sources.py provides an opt-in actual Windows UNC/mapped/SRT remux/
extraction check with real tools and retained local evidence when tiny trusted
synthetic share inputs exist. No real share is available in the current agent/CI
configuration; report this explicitly without skipping mandatory local suites or
claiming simulated paths are SMB. Document 17 gives commands and evidence limits.

## PR-08 desktop regressions and checkpoints

Commit 1 (977ea5a) passed CI 43740079375: 307 unit tests in all matrix environments,
84 real-media integration cases on Windows/Ubuntu Python 3.12 and 8 native GUI
scenarios. Python 3.11/3.13 intentionally omit media/GUI steps; Ubuntu omits native
GUI. All five jobs and complete setup/cleanup logs were inspected without Node
runtime/deprecation, runner migration or dependency compatibility warnings.

Refined native tests additionally exercise effective metadata edits/clear/reset and
non-color change markers, exact Operation extraction targets, unsupported/external
SRT feedback, no-overwrite dialog/inline errors/free suggestions, failed replacement
retention, stable activity and terminal cancellation, second-run stale-result clearing,
main-thread warning-variable disposal and external-import deduplication/removal.
Child GUI processes treat warnings as errors, including a forced worker garbage
collection regression for the earlier Tk variable-finalizer warning. Existing keyboard,
light/dark/scaling, acknowledgement/confirmation, real media and safe teardown cases
remain mandatory. Final head test counts and CI URL belong in PR #8.
Native resize coverage includes a 620-pixel logical workspace and scrolling focused
metadata controls into view. Toolkit canvas, text-label and scrolling adapters use
the pinned CustomTkinter boundary and require rerunning native tests on upgrades.

## PR-08 packet-scan follow-up

Local verification: 445 unit/integration cases and 11 native GUI scenarios passed,
along with Ruff lint/format, mypy, YAML, verified actionlint 1.7.12, pip check and
source/wheel build checks. New cases distinguish source/output failures, classify
timeouts/nonzero exits/pipe limits/JSON/count failures, enforce diagnostic argument
limits and privacy, and count/extract a two-hour 2,400-cue local subtitle timeline.
Controlled scan-cost modeling verifies that full scans use the new 300-second budget
while metadata retains 30; it is not measured SMB latency. Forced source/output
timeouts still block publication and verify cleanup/source hashes. Real bounded-runner
tests verify cancellation kills/reaps a stalled reader before its long deadline,
pre-cancelled probes never launch, and both pipe-limit channels remain bounded.
Invalid execution/metadata/scan deadlines are rejected before staging.
A distinct reordered-HEVC clock-origin case passes both counts and safely rejects
later timing changes. These are local media/process tests, not SMB evidence.

Hosted validation for the final follow-up head is tracked in PR #8; the earlier
green run at `59408c0` is baseline evidence and cannot validate a later commit.
The owner-provided 30-second source timeout is direct live-input evidence, separate
from these local tests. Keep the PR Draft for owner review of the wizard and required consumer Windows/SMB
failure acceptance; selected backend owner results are recorded in document 18.

## PR-08 five-step wizard regression strategy

Display-free tests cover guarded sequential navigation, exact-revision warning and
warning-free decisions, complete issue/code matching, failed/rejected/changed/stale
acknowledgement, duplicate decisions, unrelated replies, cancellation/close during
acknowledgement, safe terminal reset and retained source/published files. Catalog tests
separate preserved original codes from explicitly cleared language.

Native isolated-process scenarios exercise stable large startup/user geometry,
Media/Metadata/Operation/automatic Review/Execution, Back/edit retention, inline invalid
metadata, contextual imported metadata, exact extraction selection, disabled/invalid
operations, full warning display and explicit decision, cancellation, reset/recovery,
one failed-inspection modal with retained intent, keyboard language search and
light/dark/widget scaling/focus/teardown. One real GUI-to-backend remux retains actual
FFmpeg evidence; controller fakes are never counted as media verification. Existing
real-media suites are retained. Final counts/checks/full CI logs belong in PR #8.
Owner Windows 10/11 OS-DPI/screen-reader/ergonomics acceptance remains separate.

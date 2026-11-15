# Confirmed remux execution and validation - PR-04

> **Evolution note:** PR-04's safety contract remains intact. Historical deferrals were addressed in subsequent merged PR-05/06 (except packaging/release); see [document 00](00-CURRENT-STATUS.md). Network input D24 does not authorize network destination publication.

The application API executes the existing compatibility policy and plans.
Inspection schema v1 and plan_version 1 are unchanged. PR-05 extends the backend
with external SRT, separate extraction plans/validation, cancellation and progress;
see document 16. There is no new CLI, GUI, video/audio transcoding or release work.

## API and explicit confirmation

PR-08 uses regenerated remux plan version 2 (contract 14) for explicit compatible
container/stream metadata preservation. Independently validate promised container
tags against output; existing layout/timing/publication/cancellation protections
remain. Old plan revisions cannot authorize the new policy.

```python
from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.domain.execution import ExecutionRequest, ProcessConfiguration

# reviewed_plan is the exact plan whose intent/diagnostics the caller reviewed.
# Required warning codes must already be acknowledged against its revision.
request = ExecutionRequest(
    plan=reviewed_plan,
    reviewed_revision=reviewed_plan.revision,
    confirmed_revision=reviewed_plan.revision,  # Set only after explicit confirmation.
    configuration=ProcessConfiguration(timeout_seconds=300, probe_timeout_seconds=30),
)
result = RemuxExecutionService().execute(request)
```

`confirmed_revision` defaults to None: execution rejects by default. Supplying
the matching revision represents the caller's explicit confirmation action; it is
not authentication or proof that a human clicked a GUI. No boolean authorizes a
different revision. `ProcessConfiguration` also accepts trusted `ffmpeg`/`ffprobe`
executable overrides; otherwise PATH is used. Timeouts must be finite and positive.
There are no arbitrary command fragments or user-supplied FFmpeg option strings.

PR-08 packet-scan correction adds optional `packet_scan_timeout_seconds=300` to
ProcessConfiguration for each extraction completeness probe. Metadata inspection
remains at `probe_timeout_seconds=30`; FFmpeg execution has its own timeout. All
configured limits are finite positive values checked before staging. Remux validation
retains its existing metadata timeout. Extraction scans observe per-job cancellation
without changing OutputValidator's metadata timeout argument or publication authority.
Contract 16 records the confirmed source timeout, diagnostics and per-process bounds.

`RemuxExecutionService` is synchronous and GUI-independent, suitable for a caller's
worker thread. Inspection, managed process, output validation and staging ports
are injectable for deterministic failure tests. No scheduler/queue is introduced.

## Trusted regeneration boundary

Before allocating staging or starting FFmpeg, the service:

1. Requires matching confirmed/reviewed revisions and verifies the supplied plan's
   content revision. It does not trust supplied arguments or execution_allowed.
2. Independently re-inspects every source with configured ffprobe and compares the
   complete normalized inspection snapshot, not only path/size/mtime.
3. Rebuilds the plan from the original selections, output, chapter policy and fresh
   inspections, retaining revision-bound warning acknowledgements.
4. Requires the rebuilt revision to equal the confirmed revision, no errors and no
   pending warnings. All mapping/metadata/default/conflict rules are evaluated again.
5. Requires the destination's parent already to exist and discovers native FFmpeg.

Any forged derived fields, altered intent, changed diagnostics or stale content
fail. A supplied arguments tuple is ignored even if it appears valid. All fresh
arguments come from the existing PR-03 generator, not a second operation planner.
PR-05 replaces the external-import deferral with validated source roles: the primary
source must contain a selected video, while an additional subtitle-only source must
match a freshly structurally validated and independently inspected ExternalTrack
SubRip/SRT record. Unsupported external audio and missing external-record bypasses
remain rejected. Multiple video-bearing container inputs remain supported. Source
order, metadata and complete external intent participate in revision binding.

After processing and validation, every source is re-inspected and the plan is
rebuilt again before publication. A last-moment existing destination is rejected;
the exclusive filesystem primitive remains the final collision authority.
Hashes identify intent/diagnostics, not encoded file contents. Reinspection plus
size/mtime cannot detect all adversarial same-metadata content edits or eliminate
filesystem TOCTOU races. E2E fixtures additionally compare original content hashes.

## Staging, ownership and publication

An unpredictable `.mediatrack-<128-bit-random>` directory is exclusively created
under the existing final destination parent. Ubuntu uses mode 0700; Windows uses
CreateDirectoryW with a protected inheritable owner/SYSTEM-only DACL, after checking
volume support for persistent ACLs and hard links. Unix private mode is verified.
Failure to
establish that directory is a controlled staging failure, with no weaker fallback.
An exclusive `mkstemp` file (Unix mode 0600) is allocated inside it, on the same
filesystem as the requested destination. No output directories are created for users.

Directory and file device/inode identities and the retained file descriptor are
checked around processing/validation. Symlinks or replaced artifacts are rejected.
The fixed muxer remains explicit despite the `.part` extension. The service binds
fresh generator arguments only to its staging pathname and changes the fixed `-n`
to `-y` **solely for that exclusively reserved, owned private file**. This permits
FFmpeg to fill the reserved inode; the final pathname is never passed to FFmpeg.
All approved input positions, maps, codecs, metadata and dispositions remain intact.
Video/audio options are copy-only; only approved subtitle conversion may encode.

After FFmpeg is proven stopped, staged output is independently validated. The
owned file is checked and fsynced, sources/intent are revalidated, then `os.link`
creates the final name pointing to the completed validated inode. An existing
file, directory or dangling symlink makes publication fail. No replace, ordinary
rename, check-then-copy or fallback copy is used. The inode identity of the new
link is checked. Cleanup removes only the temporary entry and its owned empty
directory; it never deletes the final link or recursively removes unknown content.

This requires local same-filesystem hard-link semantics (verified on the actual
Windows/Ubuntu CI filesystem reported in logs). NTFS is the tested local Windows
target. Unsupported primitives return PUBLICATION_UNSUPPORTED/FAILED without an
unsafe fallback. Final Unix permissions remain 0600 and Windows retains the
private inherited file DACL. Both source and destination namespaces must be trusted
against adversarial edits by the same principal/administrator; directory reparse
replacement or privileged concurrent inode manipulation is not OS-sandboxed.
Ordinary competing final-name creation is handled atomically by the link itself.

Atomic visibility is not power-loss durability. Completed file data is fsynced
before linking, but directory entries are not transactionally committed across
all supported platforms. No power-failure or universal network-filesystem claim
is made. URL/UNC rejection and PR-02 mapped-network limitations still apply.

## Managed processes and timeout guarantees

FFmpeg uses argument arrays, shell=False, DEVNULL stdin and concurrent pipe readers.
Each diagnostic channel captures at most 64 KiB; excess data is drained/discarded
while termination is requested. Raw buffers are not returned, printed or persisted.
Outcomes report only bounded byte counts, stable codes, exit status and whether
cleanup is safe. Unexpected application errors never copy exception text into
normal diagnostics. No permanent log store is created.

Windows starts trusted native tools hidden and assigns them immediately to a
Job Object with KILL_ON_JOB_CLOSE and no breakaway. Timeout/normal completion
terminates remaining job members and queries active count zero, then reaps the
root process. The short launch-to-assignment interval is not protection against
a malicious override that deliberately spawns outside containment before assignment.
Assignment failure rejects execution and conservatively retains staging. Ordinary
descendants created after assignment are covered and tested with Python writers.

Ubuntu starts a new session/process group, kills that group, reaps the root, and
checks /proc for non-zombie live group members. Ordinary descendants are tested;
deliberately detached new-session children or privileged escape are not supported.
Failure to establish stop/quiescence prevents cleanup and publication. This is a
trusted-tool lifecycle strategy, not universal containment of malicious programs.

The configured process timeout covers FFmpeg plus pipe completion. Termination
verification can take an additional bounded wait (up to 5 seconds per verification
stage and reader joins). Each ffprobe call has its own timeout. Filesystem calls,
uninterruptible OS work and the entire service transaction do not have a single
hard real-time deadline. PR-05 adds cancellation/progress through the managed
runner and immutable state boundaries; document 16 defines the backend API.

## Independent validation policy

`FFprobeOutputValidator` first requires a nonempty regular staged file, then probes
it independently through the configured Inspector. The immutable ValidationReport
contains expected kind/codec summaries, the observed normalized snapshot and
structured ValidationCheck results. Checks carry code, passed/warning/error status,
detail, optional output index and optional expected/observed/tolerance seconds.
Normal execution diagnostics do not dump these private snapshot paths.

The following mismatches block publication:

- Unreadable/empty/nonregular output, wrong MKV/MP4 container, missing/extra streams.
- Kind/codec/mapping-order mismatch, including wrong copy codec or subtitle conversion.
- Changed available dimensions, channels or sample rate, supporting technical identity.
- Missing/wrong guaranteed MKV language/title, attachment filename/MIME or default/forced.
- Missing/extra promised chapters, wrong chapter title, or chapter movement outside
  its metadata-derived boundary.
- Known source duration that cannot be observed in output, or difference exceeding
  the metadata-derived timing budget.
- Known source duration for which no metadata-derived timing tolerance is available,
  even if the observed duration appears equal. No unverified comparison authorizes publication.

Only existing, accepted plan uncertainties soften the corresponding metadata
check: MP4 normalization of language/title/dispositions may warn; MKV can omit
explicit und language. Other metadata and flags already excluded by the plan are
recorded as accepted limitations. Structural codec/count/type mismatches never
become warnings because MP4 metadata is uncertain. Chapter IDs are not compared.
Same-kind/codec streams with indistinguishable technical metadata cannot be proven
content-identical by ffprobe metadata alone; explicit regenerated mappings remain
authoritative, and no full decode or content-integrity claim is made.

### Timing evidence, units and missing metadata

Durations use finite seconds from stream duration or an available strict Matroska
DURATION tag (`hours:minutes:seconds.fraction`). No value is inserted into the
inspection model or invented when missing. Container duration remains an estimate.

The timing budget is **two largest available time-base ticks plus one largest
available frame/packet boundary**, considering selected input and observed streams:

- Video boundary: reciprocal of reported positive average_frame_rate.
- AAC packet boundary: 1024 / available sample_rate_hz seconds.
- MP3 conservative frame boundary: 1152 / available sample_rate_hz seconds.
- Unknown/invalid frame rates or missing clocks are not guessed.

This budget is computed per operation and recorded in duration check evidence;
it is neither a universal 50 ms allowance nor proof of VFR packet completeness.
Differences larger than the available boundary fail. Differences inside it may
reflect muxer offsets/packet rounding and are not decode-integrity evidence.
Very coarse or absent timing cannot establish fine-grained truncation guarantees.

Per-selected-video/audio durations are checked independently. If all are available,
their maximum is also compared with container duration. If unavailable, container
duration is checked as an estimate only for a single source retaining all timed
media streams; excluding an unknown-length stream must not invent output duration.
Genuinely unknown expected source duration produces DURATION_UNVERIFIED; container
estimation limitations produce DURATION_ESTIMATE_UNCERTAIN. These warnings do not
fabricate an expected value. **Known expected duration is different:** missing
observed duration fails DURATION_UNVERIFIABLE, whether or not a budget is available.
If observed duration is present but no timing budget can be established, validation
fails DURATION_TOLERANCE_UNAVAILABLE. Apparent equality does not bypass this rule.
PR-04 provides no alternative integrity check that waives a required duration
comparison and introduces no arbitrary fallback tolerance. Any such error prevents
publication and triggers safe owned-output cleanup. Regression tests exercise
material truncation without a budget, missing observed duration, valid matching
timing, genuine unknown-duration warnings and the orchestration publication barrier.
Chapter bounds use the same operation-derived budget,
with accepted CHAPTER_TIMESTAMPS_UNCERTAIN where exact timing is unavailable.

## Results, state and cleanup

ExecutionResult contains state, ordered history, structured diagnostics, optional
ValidationReport, final destination only when published, published flag and
cleanup_complete flag. The normal history is:

```text
planned -> running -> validating -> publishing -> completed
```

Failures append failed; a controlled process timeout appends timed_out. There is
no completed status before validation, publication and normal cleanup. A published
valid output with cleanup failure is reported as failed with published=true,
destination present and cleanup_complete=false; it is never deleted as rollback.
If process termination is unverified, staging remains, our descriptor is released
and CLEANUP_UNSAFE is explicit. If ownership changed or cleanup fails, foreign
files are never removed and TEMPORARY_CLEANUP_FAILED is returned. No raw diagnostic
retention policy or keep-temporary-output option exists in PR-04.

Stable codes include UNCONFIRMED_PLAN, INVALID_PLAN, CHANGED_INPUT, INVALID_TIMEOUT,
EXTERNAL_IMPORT_DEFERRED, INVALID_DESTINATION, MISSING_EXECUTABLE,
PROCESS_LAUNCH_FAILED, PROCESS_CONTAINMENT_FAILED, PROCESS_TIMEOUT,
PROCESS_TERMINATION_FAILED, PROCESS_OUTPUT_LIMIT, FFMPEG_FAILED, PROCESS_FAILED,
OUTPUT_VALIDATION_FAILED, DESTINATION_COLLISION, PUBLICATION_UNSUPPORTED,
PUBLICATION_FAILED, STAGING_FAILED, STAGING_OWNERSHIP_LOST,
TEMPORARY_CLEANUP_FAILED, CLEANUP_UNSAFE and EXECUTION_FAILED. Each maps to a bounded
actionable English message. Unsupported filesystem or containment behavior fails
closed; no successful cleanup or publication is inferred from an exception.

## Evidence and boundaries

Mandatory Windows/Ubuntu Python 3.12 E2E tests call the product service, preserve
original hashes, and check final outputs and staging cleanup. Cases cover video-only
MP4, audio selection/subtitle removal, AVI-to-MKV, internal subtitle conversion,
chosen video identity, incompatible plans, same/existing paths, publication races,
Unicode, execution failure, timeout, validation rejection and chapter/attachment
metadata. Selected cases compare video packet hashes to confirm stream-copy behavior.
Offline tests inject failure boundaries and exercise process groups/Job Objects
using Python only. Dangling-link unit behavior is injected to remain runnable on
Windows accounts without symlink privilege; no mandatory test is silently skipped.
Actual filesystem/tool versions and final CI evidence belong in the PR.

References: [Python hard links](https://docs.python.org/3/library/os.html#os.link),
[Windows hard links](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw),
[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
Full extraction, user cancellation, GUI, external-SRT import and release work remain
outside PR-04. G3 cannot be completed by this remux-only iteration.

## PR-05 extension boundary

Document 16 supersedes historical external-import/extraction/cancellation deferrals
in this PR-04 contract. The shared orchestrator adds execute(request, control=...),
per-job cancellation and structured phase/progress events. Successful publication
is the commitment boundary; cancellation cannot roll back a final output. Known
remux duration still requires observed timing and a reliable tolerance. Elementary
extraction uses its separate documented packet-based validation alternative when
raw duration is unavailable, without weakening the remux policy. Filesystem, cleanup,
process trust and diagnostic limits above remain. GUI and release work stay deferred.

## D24 read-only network input boundary

The existing source/role/revision checks now accept trusted Windows UNC/mapped media
and SRT through the shared inspection service. Exact canonical paths remain FFmpeg
inputs with explicit maps and the file-only protocol whitelist. All sources are
reinspected before execution and publication; unavailable/changed sources prevent
publication. This does not make metadata a cryptographic or transactional SMB snapshot.
Network outputs remain blocked by canonical UNC and native Windows volume checks
at planning, staging allocation and publication. Local private staging, validation,
exclusive hard link, collision/cancellation/cleanup guarantees are unchanged. OS
network filesystem operations can outwait subprocess deadlines; the GUI waits for
safe worker completion and never force-publishes or deletes potentially active data.
POSIX mounted-network identification remains outside existing guarantees; this
Windows input change does not certify remote output filesystems.

## PR-08 explicit wizard decision

The final GUI button replaces the old extra confirmation popup, not the backend
confirmation requirement. DesktopController separately acknowledges captured pending
warning codes for the exact reviewed revision, verifies unchanged evidence, then sets
reviewed_revision and confirmed_revision to that same revision in ExecutionRequest.
Without warnings the explicit click is still mandatory. A changed/failed/stale reply,
cancellation or superseding intent cannot auto-launch. Independent backend regeneration,
validation, cancellation and publication are unchanged. Safe Start over is UI state
reset only after verified terminal cleanup and never removes sources or published files.

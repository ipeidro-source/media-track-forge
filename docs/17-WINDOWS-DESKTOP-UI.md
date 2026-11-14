# Windows desktop interface - PR-06

PR-05 is merged at `3b9a560` with successful main CI 43618260739. Owner-approved
D19–D23 authorize this desktop interface. PR-07 packaging, desktop executable
validation and explicitly authorized release publication remain deferred. No G4
or complete MVP acceptance is inferred from GUI smoke tests.

## Setup and launch

Use Python 3.11+ x64 with native Tk installed (the standard Windows Python installer
includes Tcl/Tk). Install the exact development snapshot and the project:

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
python -m mediatrack_forge.ui.desktop
# Alternatively, the installed Windows GUI entry point:
mediatrack-forge-desktop
```

FFmpeg/ffprobe remain external trusted native programs on PATH. The existing
`mediatrack-forge inspect` CLI and inspection/planning/execution contracts 13–16
are unchanged. Backend and presentation-model imports do not initialize a display
or import CustomTkinter; the desktop launcher loads the window lazily.

The selected runtime dependency is `customtkinter==6.0.0`, verified against
[published PyPI metadata](https://pypi.org/project/customtkinter/6.0.0/) on
November 14, 2026 (Python >=3.7; project requires >=3.11). Its darkdetect dependency
is pinned to 0.8.0 in the complete development snapshot; existing packaging 26.3
also satisfies its requirements. No unrelated dependencies were upgraded. Runtime
installation now includes these GUI dependencies even for CLI users, but backend
use needs no display. Tk is supplied by Python/OS, not installed by pip. Review
CustomTkinter's published CC0 and darkdetect's license alongside the unresolved
application license before PR-07 distribution. No binaries are bundled here.

## One window, three areas

Media contains Open Media (native file dialog), Add SRT files (multi-selection),
Remove external, source/container/duration/size/dimensions/count summary and a
scrollable track table. Inspection success never implies output compatibility.
Opening a new primary clears external sources, editing intent and review state.

The table displays inclusion, original index, kind, codec, language/title,
default/forced flags, requested within-kind ordering and primary/external source.
Sorting column headings is presentation-only. Every row maps to a full immutable
StreamReference; row position or row label is never a media index. Audio, video,
subtitle, attachment, data and unknown streams remain visible. Initially every
stream is included, preserving source order; unsupported selections/default
conflicts remain visible blockers, never silently resolved or omitted. Explicit
Include/exclude actions produce explicit selection intent. Zero audio/subtitles
is valid for remux. Move up/down affects only peers of the same kind; final
backend grouping and order are shown in the review.

Metadata editing separates Keep original from Set value. Empty Set value explicitly
clears language/title; Keep original maps to None. Default/Forced use Keep original,
On and Off. Source snapshots remain immutable. Apply metadata saves changes;
review also applies pending edits. Merely editing a field invalidates prior review,
so an unapplied field can never leave Execute enabled. Navigating to another row
saves previous pending metadata. Imported SRT metadata is kept consistent between
the explicit selection and its ExternalTrack record. Duplicate imports are ignored
by source identity, without deleting files. Removing an external source removes
only session intent. Malformed SRT is reported through the existing validator.

Operation contains Remux/Extract mode, output format, native destination chooser,
chapter policy, review, warning acknowledgements and Execute. MKV/MP4 and chapter
restrictions are backend-authoritative. Select Use for extraction on one Media row
to establish an exact original stream target. Available extensions come from
ExtractionPlanningService policy discovery; the GUI has no separate compatibility
matrix. Unsupported tracks remain inspectable and visible, with no fabricated
conversion/extension. Changing mode preserves inspection but invalidates review.
The save dialog never authorizes overwrite; the planner and exclusive publisher
remain authoritative. Missing parents and changed inputs are rechecked by execution.
No directories are created implicitly.

Execution presents phase, determinate/indeterminate progress, processed media time,
Cancel and final result/validation evidence. Completed means validation, exclusive
publication and normal cleanup succeeded. A failed result with published=true is
shown with its actual destination and incomplete cleanup, never “no file created”.
Source files and published results are never deleted by GUI actions.

## Review, acknowledgement and final confirmation

Review invokes the existing planner on a captured immutable EditingIntent in the
worker. Human-readable output shows all sources, exact destination/format, selection
and metadata intent (including keep/clear), final maps/order, exclusions, codec
actions, chapters/attachments preservation, bitstream filters and every diagnostic
with its severity, source reference and available suggestion. Generated FFmpeg
arguments are not editable through the GUI. Errors block execution; there is no
ignore-errors control.

Each warning code has an initially unchecked acknowledgement control. The review
shows every occurrence and each checkbox states how many occurrences it covers.
The explicit Acknowledge selected action rebuilds using that exact revision and
selected codes. Partial acknowledgement leaves pending warnings; changed regenerated
revision discards stale acknowledgement and requires another review. Opening the
review does not grant acknowledgement. Execute is disabled until intrinsic validity,
effective acknowledgement and the reviewed revision match. The separate Execute
confirmation dialog defaults to No, describes the exact destination and constructs
ExecutionRequest with that reviewed/confirmed revision only after Yes.

Any source/external/order/inclusion/metadata/container/destination/chapter/mode/target
edit invalidates the plan and review/confirmation. Monotonic generations reject
superseded worker results. Completion consumes confirmation; another operation needs
fresh review. The backend independently regenerates and checks everything before
processing and publication, regardless of GUI state.

## Background work and lifecycle

ui/presentation_model.py owns immutable EditingIntent, display-independent
DesktopController and a small DesktopBackend composition of existing services.
ui/worker.py owns one non-daemon task thread, one result/error slot and one latest
progress value protected by a short lock. No unbounded queue, event bus, scheduler
or database exists. Inspection, SRT validation, filesystem-based planning, execution,
extraction and validation run on that worker. Workers never call Tk APIs.

The main Tk thread polls through after(), applies generation-matching replies and
renders widgets. Conflicting editing actions are disabled while busy. Progress
callbacks only replace a bounded value and return promptly. Frequent updates
coalesce; slow rendering cannot grow an event queue. Backend percentages/phases
are used without optimistic completion, and 100% is reserved for backend completion.
Observer phase preparing covers blocking inspection/planning as well as execution.

Cancel calls the current per-job backend token. It reports cancellation requested
and waits for the actual terminal result; it does not kill processes independently.
Existing Windows Job Object/Ubuntu process group termination, timeout and atomic
publication commitment semantics remain unchanged. A token request that arrives
after publication cannot remove a final output or convert success into cancellation.

Closing during work asks whether to keep the window open or request cancellation
and close only after a safe terminal reply. Tk is not destroyed while a worker is
active. Non-execution probes finish within their existing timeout; pending close
waits. Incomplete/unverified cleanup keeps recovery information visible and blocks
further operations/automatic close. An unexpected execution exception is likewise
treated as unverified cleanup. Recovery requires inspecting retained staging and
process status privately; no force-kill or automatic unsafe deletion shortcut is
provided. Published outputs remain untouched. After destruction, polling and late
worker replies cannot update widgets.

## Theme, sizing and keyboard

CustomTkinter follows system appearance, with a matching ttk Treeview palette
derived from the toolkit theme and refreshed on appearance changes. Errors are
identified by text/severity, not color alone. The window resizes; table/review and
results scroll. CustomTkinter's native Windows DPI support is retained, without
changing another process's DPI configuration. Automated widget scaling checks use
1.0/1.25/1.5; these do not certify actual OS DPI changes or every laptop resolution.
Window size can be adjusted for the desktop. Higher scaling and actual 100/125/150%
Windows settings remain in the manual acceptance checklist.

Ctrl+O opens media, Ctrl+R reviews, Ctrl+Enter requests execution confirmation and
Escape requests cancellation. Alt+1/2/3 switch Media/Operation/Execution areas.
The table supports arrows, Space inclusion and Alt+Up/Down within-kind movement.
Tab traversal reaches metadata/actions; adapted
CustomTkinter button/option/checkbox canvases expose focus with a visible outline.
Return/Space activate controls; Left/Right cycles option values. Native dialogs
provide their standard keyboard behavior. The adapter uses a small tested toolkit
canvas boundary; dependency upgrades must rerun native interaction tests.

CustomTkinter/Tk accessibility and screen-reader integration are limited; these
tests do not certify Windows UI Automation, Narrator, high contrast, WCAG, or formal
accessibility conformance. A manual Windows 10/11 keyboard/screen-reader check is
required before final product acceptance.

## Repeatable validation and native smoke

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
python -m pytest tests/gui -v -s
python scripts/check_yaml.py
actionlint
python -m pip check
python -m build --no-isolation
```

Default pytest discovery runs offline unit and real-media integration directories;
it never needs a Linux display. Native GUI tests are explicitly invoked separately
on Windows Python 3.12 in the existing mandatory job. Each scenario runs in a fresh
process with one Tk root, matching the application lifecycle. Repeated roots in one
local interpreter produced Tcl initialization failures; process isolation avoids
cross-root state. Tests wait for actual layout/terminal conditions with bounded
deadlines, rather than assuming immediate rendering. Missing Tk/display/media tools
fail the invoked smoke suite; no hidden skip or fake passing desktop is used.

Smoke scenarios cover title/areas, track population/sorting/identity, explicit
metadata clearing, review/checkboxes/confirmation, progress/cancellation, safe close,
published cleanup-failure presentation, light/dark/widget scaling and teardown.
Controlled backend cases validate GUI interaction only. A separately identified
real GUI-to-backend synthetic H.264/AAC-to-video-only MP4 case validates actual
processing, source hash preservation, output inspection and staging cleanup.
Display-independent real orchestration also covers AC-01..12 and extraction using
actual services; low-level PR-01..05 tests remain unchanged except the now-authorized
runtime-dependency expectation. Final counts and hosted tool/build/log evidence
belong in the PR description, not assumed from this document.

Hosted Windows Server 2025 Tk widget tests are not a logged-in Windows 10/11 user
acceptance session. Screen capture was unavailable in the local execution desktop;
no screenshot is fabricated or presented as evidence. Native tests exercise real
widgets and event loops with dialogs controlled for determinism. They do not prove
human screen visibility, keyboard ergonomics or screen-reader behavior.

Manual Windows 10/11 checklist before final acceptance:

1. Launch from a clean development environment; resize at 100/125/150% OS DPI.
2. Inspect synthetic media; sort/select tracks and verify original indices.
3. Edit keep/set/clear tags and flags, reorder peers, add/remove multiple SRT files.
4. Review remux and extraction, resolve blockers and explicitly acknowledge warnings.
5. Reject the first confirmation; verify no execution. Confirm a fresh reviewed plan.
6. Observe progress, cancel, then close during work; verify safe backend completion.
7. Inspect published/failed/cancelled and cleanup evidence; originals remain intact.
8. Check light/dark, full keyboard traversal, native pickers and screen-reader limits.

No recent-files/history persistence, telemetry, network media, GUI process runner,
video/audio transcoding, batch, PyInstaller, portable ZIP, installer or release is
introduced. PR-07 must address packaging, dependency notices/license, executable
smoke and owner-authorized release gates separately.

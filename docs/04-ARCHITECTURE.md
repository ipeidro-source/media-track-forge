# 04 — Architecture (Implemented Baseline and Historical Proposals)

## Principles

Python 3.11+ and a GUI-independent core were selected in PR-01; the CustomTkinter/ttk desktop was implemented by PR-06. FFmpeg and ffprobe remain required external executables. Mapped/UNC trusted inputs are supported under D24 (real SMB testing pending); output remains local-only. Startup winget guidance/updates and safe network publication are planned, not implemented. See [current status](00-CURRENT-STATUS.md).

```text
Windows Desktop UI (CustomTkinter)
              |
Application services: inspect / plan / execute / extract
              |
Domain model and policies: sources / streams / compatibility / operations
        |                            |
FFprobe adapter              FFmpeg command planner
        |                            |
        +---- Process runner (subprocess, cancel, progress) ----+
                                                  |
                                  Output validator / safe publisher
```

## Original proposed modules (historical; implemented packages are below)

- `domain/`: immutable media entities, stream identities, operation plans, compatibility warnings.
- `probe/`: ffprobe JSON parsing, input normalization, errors, and timeouts.
- `compat/`: tested codec/container/subtitle compatibility policy and actionable blockers.
- `planner/`: explicit stream order, FFmpeg mappings, codec actions, language/disposition metadata, output constraints.
- `runner/`: shell-free subprocesses, Windows cancellation, progress, and diagnostic output.
- `validate/`: pre/post stream comparison, media duration tolerance, and basic output integrity.
- `storage/`: safe temporary files, path checks, collision detection, and atomic publication where supported.
- `ui/`: view state and presentation logic, with no embedded FFmpeg business rules.
- `cli/`: a small `inspect` entry point for CI and troubleshooting; not a commitment to a full headless product yet.

## Workflow

1. User selects local media and optional external tracks.
2. ffprobe inspects sources and converts metadata to domain entities.
3. User specifies output streams, ordering, container and metadata.
4. Planner generates a declarative plan and compatibility diagnostics.
5. User reviews and explicitly confirms the plan.
6. Runner writes temporary output in a safe location, preferably on the destination volume.
7. Validator probes the output and compares expected vs. observed streams and duration.
8. Publisher commits a valid output to a free destination; otherwise it reports failure and follows a clear cleanup policy.

## Technical cautions

- Map streams by source and source-local ffprobe stream index. Do not use automatic stream selection.
- Handle chapters, attachments, unknown data streams, `-map_metadata`, `-map_chapters`, and `-disposition` explicitly. Warn when content or metadata cannot be preserved.
- Stream indices are not stable identifiers across file changes. Store source path/size/mtime and a snapshot identity in plans; revalidate inputs before execution.
- MP4 `mov_text` involves **subtitle re-encoding**, not audio/video transcoding. It can lose formatting.
- Compatibility must be based on tested combinations and the capabilities of the installed FFmpeg build. AVI input does not imply AVI-to-MP4 stream-copy support.
- Remuxing does not correct corrupted sources or pre-existing sync problems.
- Size savings from track removal are estimates until actual file-size and bitrate information is available; label uncertainty.

## Future extension points

Phase 1: selective `TranscodePlan` for individual video and audio streams.

Phase 2: `BatchJob`, resource scheduling, estimated savings, rules-based execution, and GPU-capability discovery.

Optional future: a headless service/CLI or Docker deployment should use the core without importing the GUI.

## PR-01 package boundaries

The `src/mediatrack_forge` scaffold separates `domain`, `application`, `infrastructure`, and `ui`. PR-01 introduced help/version without a GUI or media dependency. Specialized processing modules above remain future responsibilities inside those layers.

## PR-02 implemented inspection path

`ui/cli.py` composes `InspectionService` with `FFprobeAdapter`. The service validates
and snapshots a regular local file and calls an application-owned `MediaProbe`
Protocol. `infrastructure/ffprobe.py` discovers the external executable and runs
it with bounded pipes, timeout and file-only protocol whitelist; `ffprobe_json.py`
normalizes the response. Both depend on application error types and domain
snapshots, never presentation. `domain/media.py` contains frozen dataclasses and
immutable tuples with no subprocess, CLI or infrastructure imports.

`ui/inspection_json.py` defines explicit public serialization, separate from the
ffprobe parser. The application service can be used without either UI or GUI:

```python
from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter

asset = InspectionService(FFprobeAdapter()).inspect("example.mkv")
```

Inspection and the PR-03 declarative planning API are implemented. Execution,
processing cancellation, output validation and publication remain deferred.
See [contract and safety limits](13-INSPECTION-CONTRACT.md).

## PR-03 planning subsystem

`domain/planning.py` defines frozen references, selection/metadata/external intent,
output profiles, issues, preservation decisions and plans. `domain/compatibility.py`
is an explicit allowlist with no filesystem or process dependency.
`application/planning.py` validates supplied inspection snapshots and caller intent,
coordinates read-only path checks, compatibility and metadata policies, and returns
an immutable plan. It composes the pure infrastructure argument generator and
read-only path adapter, independently of CLI/GUI. `infrastructure/ffmpeg_arguments.py`
generates explicit mappings/codecs/metadata/dispositions/chapters without subprocess.
`ui/operation_plan_json.py` serializes plan_version 1 separately from inspection.
No product runner, importing, persistence or new framework is introduced.

## PR-04 execution boundary

`domain/execution.py` defines immutable requests/configuration, state histories,
diagnostics and validation/results. `application/execution.py` orchestrates meaningful
injected ports in `execution_ports.py`: Inspector, ProcessRunner, OutputValidator,
StagingStore and OwnedStage. It reuses the inspection/planning services and existing
argument generator; stored supplied arguments are never trusted. Native filesystem,
process groups/Windows jobs, pipe draining, output validation and private staging
remain infrastructure-owned in focused modules. No GUI or background scheduler
is introduced. See [execution contract](15-EXECUTION-AND-VALIDATION-CONTRACT.md).

## PR-05 shared backend extension

ExternalSubtitleService composes bounded structural SRT validation and the existing
Inspector. Domain SubtitleCue and ExtractionPlan retain immutable intent/evidence.
ExtractionPlanningService owns the separate exact source/codec/format/filter policy.
ExtractionExecutionService specializes the shared RemuxExecutionService through
regeneration, argument and validator hooks. Process runner, native containment,
private staging, exclusive publication and cleanup are shared, with no second
execution stack. Elementary validation uses independent packet completeness checks.
ExecutionControl coordinates per-job cancellation and synchronous bounded progress;
ProgressEvent is a domain value. Existing four layers and dependency pins remain.
Document 16 supersedes historical deferred-import/extraction statements above.
No GUI, scheduler, batch processing or public writing CLI is added.

## PR-06 desktop boundary

ui/desktop.py lazily composes DesktopWindow. ui/window.py renders CustomTkinter/ttk
on the main thread. ui/presentation_model.py adapts immutable backend entities into
EditingIntent and DesktopController, with generation-safe review/confirmation and
DesktopBackend composition of existing services. ui/worker.py contains one task
thread, bounded reply and latest-value progress. No widgets call media processes.
Pure presentation/backend imports require no display. Extraction extension discovery
is application-owned, not a second GUI compatibility matrix. Existing inspection,
planning/execution/extraction contracts and four-layer direction remain unchanged.
See document 17 for lifecycle, source identity, acknowledgement and testing limits.

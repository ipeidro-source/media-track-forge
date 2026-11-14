# 04 — Proposed Architecture

## Principles

Python 3.11+ and CustomTkinter are **proposed, not permanently mandated**. Design a Windows-first desktop GUI over a UI-independent core. Treat FFmpeg and ffprobe as external executables whose presence and capabilities are checked. The MVP works offline with local files.

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

## Proposed modules

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

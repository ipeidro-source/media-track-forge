# MediaTrack Forge

**Status (November 15, 2026):** PR-01–PR-06 are merged into `main` (`9298fd46`). GUI and trusted UNC/mapped file inputs are implemented but not fully owner-accepted. See [current status](docs/00-CURRENT-STATUS.md); no Release has been published.

A free, open-source, Windows-first desktop application for **inspecting, adding, removing, extracting, and rearranging video, audio, and subtitle tracks**, and changing media containers without video or audio re-encoding whenever possible. Selective transcoding, batch processing, and intelligent library optimization are planned for later phases.

## Getting started

1. Read [Product vision and scope](docs/01-VISION-AND-SCOPE.md).
2. Review the [Roadmap](docs/02-ROADMAP.md) and [MVP requirements](docs/03-MVP-REQUIREMENTS.md).
3. Codex must follow [AGENTS.md](AGENTS.md) and the [Codex implementation plan](docs/08-CODEX-IMPLEMENTATION-PLAN.md).
4. Record new decisions in the [Architecture Decision Record](docs/06-ARCHITECTURE-DECISIONS.md); do not silently override accepted decisions.

For Python setup, validation commands, CI policy and deferred Windows release gates, see [Development and delivery](docs/12-DEVELOPMENT-AND-DELIVERY.md).

With external ffprobe installed on PATH:

```powershell
mediatrack-forge inspect "C:\Media\example.mp4"
python -m mediatrack_forge inspect "C:\Media\example.mkv" --ffprobe "C:\Tools\ffprobe.exe" --timeout-seconds 30
```

Inspection preserves stream order/indices, metadata, chapters, and video-only inputs.
Success prints one JSON document; errors go to stderr with documented exit codes.
See the [version 1 inspection contract](docs/13-INSPECTION-CONTRACT.md) for fields,
units and local-file security limitations. Global help and version remain available.

Planning is available through `OperationPlanningService`, with explicit stream
references, deterministic ordering, a conservative tested codec allowlist, metadata
diagnostics and warning acknowledgements. It creates no output and runs no FFmpeg.
See the [plan v1 contract](docs/14-OPERATION-PLAN-CONTRACT.md) for the Python API,
supported combinations and limits. There is no public planning/editing CLI.

The Python `RemuxExecutionService` consumes an explicitly revision-confirmed plan,
re-inspects/regenerates it, writes private staging, validates it and publishes by an
exclusive hard link. Existing final files are never overwritten. There is no
remux CLI. See [execution and validation](docs/15-EXECUTION-AND-VALIDATION-CONTRACT.md)
for supported filesystem/process guarantees and timing limitations.

## Documentation index

- [01 — Vision and scope](docs/01-VISION-AND-SCOPE.md)
- [02 — Roadmap and estimates](docs/02-ROADMAP.md)
- [03 — MVP requirements and acceptance criteria](docs/03-MVP-REQUIREMENTS.md)
- [04 — Architecture](docs/04-ARCHITECTURE.md)
- [05 — Domain model](docs/05-DOMAIN-MODEL.md)
- [06 — Architecture decisions](docs/06-ARCHITECTURE-DECISIONS.md)
- [07 — Quality and testing](docs/07-QUALITY-AND-TESTING.md)
- [08 — Codex implementation plan](docs/08-CODEX-IMPLEMENTATION-PLAN.md)
- [09 — GitHub and development environment](docs/09-GITHUB-AND-DEVELOPMENT.md)
- [10 — Risks and open questions](docs/10-RISKS-AND-OPEN-QUESTIONS.md)
- [11 — ChatGPT project context](docs/11-CHATGPT-PROJECT-CONTEXT.md)
- [12 - Development and delivery foundation](docs/12-DEVELOPMENT-AND-DELIVERY.md)
- [13 - Inspection JSON contract](docs/13-INSPECTION-CONTRACT.md)

- [14 - Operation plan contract](docs/14-OPERATION-PLAN-CONTRACT.md)

- [15 - Execution and validation contract](docs/15-EXECUTION-AND-VALIDATION-CONTRACT.md)

## Guiding principles

**No surprises:** never overwrite original files, never silently transcode audio/video, preview the exact track operations, detect incompatible codecs, validate output before publication, and provide a clear audit trail.

The MVP reads local media and trusted Windows file-share media (D24); output publication remains local-only. It is independent of YouTube Smart Downloader and does not download media from the internet.

**Language policy:** all project artifacts must be written in **English**, including documentation, ADRs, source-code comments/docstrings, commit messages, PR descriptions, Issues, tests, UI copy, and instructions to Codex. ChatGPT may explain the project conversationally in Spanish if the user asks, but changes committed to the repository must remain in English.

The project uses the name `media-track-forge`. Application-owned code is under [MIT](LICENSE); third-party redistribution notices remain a packaging/release gate.

## PR-05 backend APIs

ExternalSubtitleService validates UTF-8 SRT and independently probes its actual stream.
ExtractionPlanningService/ExtractionExecutionService support the explicit elementary
matrix. Both execution services share cancellation, progress, private staging and
exclusive publication. These are worker-callable Python APIs, with no new CLI/GUI.
See [external tracks, extraction and cancellation](docs/16-EXTERNAL-TRACKS-EXTRACTION-AND-CANCELLATION.md)
for usage, encoding/matrix limits, revision confirmation and atomic commitment.
G3 remains subject to owner review; the complete MVP is not claimed.

## Windows desktop (PR-06)

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m mediatrack_forge.ui.desktop
```

CustomTkinter 6.0.0 provides one window with Media, Operation and Execution areas.
Inspect local media, edit explicit track intent, add SRT, review remux/extraction,
acknowledge warnings and separately confirm execution. Backend staging/validation/
publication and cancellation remain authoritative. The installed alternative entry
point is `mediatrack-forge-desktop`; the inspection CLI is unchanged.
See [Windows desktop workflow and smoke procedure](docs/17-WINDOWS-DESKTOP-UI.md).
Native Windows 10/11 manual acceptance and PR-07 packaging remain pending.

## Trusted Windows network inputs (D24)

Windows mapped-drive inputs such as `Z:\Media\movie.mkv` and direct UNC inputs
such as `\\server\share\movie.mkv` can be inspected and used read-only, including
external SRT. Mapped inputs retain their resolved canonical source identity through
review/reinspection. HTTP/FTP/other media URLs remain blocked; FFmpeg/ffprobe use
only the file protocol. Outputs must remain on supported local volumes: network
publication is not enabled. See document 17 for access, timeout, identity and real
SMB validation limitations. No real SMB execution is claimed from simulated tests.

## Upcoming work

Interactive [UX validation](docs/18-UX-VALIDATION.md) precedes GUI refinement and two-artifact Windows portable packaging (`onefile` `.exe` and `onedir` ZIP). D24 allows trusted network **inputs**, pending real SMB acceptance; network **outputs** remain blocked by design until independently verified and authorized. The [roadmap](docs/02-ROADMAP.md) records this future requirement.

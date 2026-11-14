# MediaTrack Forge

**Status:** PR-02 media inspection implementation - November 14, 2026. PR-01 is merged. Local read-only ffprobe inspection and a versioned JSON CLI are implemented on this branch; media editing, GUI and executable releases remain deferred.

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

## Guiding principles

**No surprises:** never overwrite original files, never silently transcode audio/video, preview the exact track operations, detect incompatible codecs, validate output before publication, and provide a clear audit trail.

The MVP works with local media only. It is independent of YouTube Smart Downloader and does not download media from the internet.

**Language policy:** all project artifacts must be written in **English**, including documentation, ADRs, source-code comments/docstrings, commit messages, PR descriptions, Issues, tests, UI copy, and instructions to Codex. ChatGPT may explain the project conversationally in Spanish if the user asks, but changes committed to the repository must remain in English.

The repository name `media-track-forge` and the final license are subject to confirmation before public release.

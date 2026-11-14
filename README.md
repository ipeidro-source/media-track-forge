# MediaTrack Forge

**Status:** project proposal and planning baseline v0.2 — November 14, 2026. No product code has been implemented as part of this documentation kit.

A free, open-source, Windows-first desktop application for **inspecting, adding, removing, extracting, and rearranging video, audio, and subtitle tracks**, and changing media containers without video or audio re-encoding whenever possible. Selective transcoding, batch processing, and intelligent library optimization are planned for later phases.

## Getting started

1. Read [Product vision and scope](docs/01-VISION-AND-SCOPE.md).
2. Review the [Roadmap](docs/02-ROADMAP.md) and [MVP requirements](docs/03-MVP-REQUIREMENTS.md).
3. Codex must follow [AGENTS.md](AGENTS.md) and the [Codex implementation plan](docs/08-CODEX-IMPLEMENTATION-PLAN.md).
4. Record new decisions in the [Architecture Decision Record](docs/06-ARCHITECTURE-DECISIONS.md); do not silently override accepted decisions.

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

## Guiding principles

**No surprises:** never overwrite original files, never silently transcode audio/video, preview the exact track operations, detect incompatible codecs, validate output before publication, and provide a clear audit trail.

The MVP works with local media only. It is independent of YouTube Smart Downloader and does not download media from the internet.

**Language policy:** all project artifacts must be written in **English**, including documentation, ADRs, source-code comments/docstrings, commit messages, PR descriptions, Issues, tests, UI copy, and instructions to Codex. ChatGPT may explain the project conversationally in Spanish if the user asks, but changes committed to the repository must remain in English.

The repository name `media-track-forge` and the final license are subject to confirmation before public release.

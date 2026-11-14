# 02 — Roadmap, Estimates, and Approval Gates

Estimates are **rough development-effort ranges**, not calendar commitments. Reassess them after the first Codex PRs.

| Phase | Scope | Preliminary effort | Exit condition |
| --- | --- | ---: | --- |
| MVP (v0.x) | Inspect local media, select/remove tracks, add SRT, support video-only output, remux/extract, validate AVI/MP4/MKV input and MKV/MP4 output | 25–40 h for core functionality, plus cross-cutting quality work | E2E cases and acceptance criteria in document 03 |
| Phase 1 — Transcoding | Selective H.264/H.265 video and AAC audio encoding; quality/bitrate presets, robust progress/cancellation | +30–50 h | Repeatable conversions and explicit codec decisions without breaking stream-copy workflows |
| Phase 2 — Automation | Batch queues, subtitle-file matching, conditional GPU support, sampling, size estimates, and simple rules | +40–70 h | Recoverable batch workflow and per-file output validation |
| Cross-cutting quality and delivery | CI/CD, FFmpeg integration testing, Windows packaging, user documentation, licenses, Releases | +20–35 h | Tested portable artifact and release process |
| Optional future | Headless CLI/Docker/NAS use, Plex/Jellyfin-oriented workflows, commercial packaging | Not estimated | Separate ADR and authorization |

**Original overall planning estimate:** 115–195 effort-hours for a reasonably complete desktop product. These categories overlap; do not double-count tests/CI included in each PR.

## Approval gates

- **G0:** documentation and GitHub repository established.
- **G1:** tested core scaffold and ffprobe inspection.
- **G2:** compatibility rules and declarative operation planning.
- **G3:** remux/extraction engine and E2E validation.
- **G4:** Windows GUI and portable packaging.
- **G5:** reviewed MVP; release only when explicitly authorized.
- **G6:** separate decision to implement transcoding, GPU, or batch processing.

Documenting later phases **does not authorize Codex to implement them during the MVP**.

## Working principles

Use narrow PRs; review acceptance criteria at each gate; update the roadmap with actual results and newly discovered constraints. Never represent a planned feature as already implemented.

## Current milestone evidence

PR-01 and PR-02 are merged. The PR-02 main baseline is
`392ce9456f63ca2cdc836b168766b43d10035d37`, with successful
[main CI](https://github.com/ipeidro-source/media-track-forge/actions/runs/43604124796).
PR-03 targets G2 with compatibility policy and declarative plans only. G2 remains
pending review and acceptance by the owner; no execution, publication or GUI gate
is completed by planning tests.

## PR-04 iteration evidence boundary

PR-03 is merged at a91493fe67203716300b015ada481140f546de8a, with passing
[post-merge CI](https://github.com/ipeidro-source/media-track-forge/actions/runs/43608930710).
PR-04 implements confirmed remux execution, staged validation and exclusive
publication. Its actual hosted evidence belongs in the PR. G3 remains incomplete:
extraction and full user cancellation are PR-05 responsibilities; GUI/release
gates are not advanced by this iteration.

## PR-05 iteration

PR-04 is merged at 3bea7ee; main CI 43614579922 passed. D14-D18 approve the
remaining backend external SRT, exact-matrix extraction, cancellation and progress
work on this branch. Evidence and review belong in PR-05; G3 remains pending owner
acceptance. PR-06 implements GUI interaction; PR-07 addresses packaging/Windows
desktop smoke checks and release gates. Neither is implemented here.

## PR-06 desktop iteration

PR-05 is merged at 3b9a560 with successful main CI 43618260739. Approved D19-D23
authorize the native desktop workflow on this branch. Unit/controller, real-media
orchestration and explicit Windows Tk smoke evidence belong in PR-06. G4 remains
incomplete until PR-07 packaging and native Windows 10/11 acceptance; no release
gate is advanced automatically. The complete desktop contract is document 17.

# 06 — Architecture Decision Record (ADR)

Statuses: **Accepted baseline**, **Proposed / pending**, or **Deferred**. These decisions document the project baseline; implementation remains subject to each approval gate.

| ID | Status | Decision | Rationale |
| --- | --- | --- | --- |
| ADR-001 | Accepted baseline | Windows desktop first; develop natively in VS Code on Windows | Test GUI, native paths, and executable without WSL friction |
| ADR-002 | Accepted baseline | UI-independent processing core | Enables future CLI and Docker execution |
| ADR-003 | Accepted baseline | External FFmpeg and ffprobe; initially not bundled | Reduce binary size, licensing/distribution complexity |
| ADR-004 | Accepted baseline | No video/audio transcoding in the MVP | Bounded scope; preserve media quality |
| ADR-005 | Accepted baseline | MKV/MP4 outputs; AVI accepted as input; verify compatibility | Useful formats without false codec guarantees |
| ADR-006 | Accepted baseline | Immutable original, staged output and post-run validation | Reduce risk of data loss |
| ADR-007 | Proposed / pending | Python 3.11+, CustomTkinter, pytest, Ruff, mypy | Leverage existing experience; approve at G0 |
| ADR-008 | Proposed / pending | MIT for application code | Easy contributions; review redistribution constraints |
| ADR-009 | Deferred | Portable ZIP + Windows `.exe` | Decide during packaging |
| ADR-010 | Deferred | GPU acceleration and specialized codecs | Phase 2; requires capability/licensing assessment |
| ADR-011 | Accepted baseline | **English-only project artifacts and English-first UI** | International consistency; avoid mixed-language documentation |
| ADR-012 | Accepted baseline | Versioned docs and code, reviewable PRs, no automatic merges | Traceability across ChatGPT and Codex work |
| ADR-013 | Accepted baseline | Explicit source-to-output stream mapping, with video-only output permitted | Predictable track-level operation |

## Decision-change policy

Any material change to media integrity, track semantics, compatibility policy, licensing, CI, packaging or UX requires a dated ADR update documenting context, alternatives, choice, trade-offs, and approval state.

Phase 1/2 ADRs are not authorization to extend the MVP. The project owner approves scope changes.

## Documentation language rule

All ADRs, technical notes, source comments, issues, commits, PR descriptions, UI copy and release notes **must be in English**. Conversational Spanish does not change this repository-wide policy.

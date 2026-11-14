# 08 — Incremental Codex Implementation Plan

## Collaboration

- **ChatGPT:** product scope, architecture, specifications, decision tracking, and requirement reviews.
- **Codex:** scoped implementation, local validation, tests, documentation updates, and draft/reviewable PRs.
- **Project owner:** approves product decisions, reviews and merges PRs, authorizes tags and releases.

Start with one Codex working tree. For concurrent agents, use **separate branches and separate `git worktree` directories**; never share a mutable working tree.

## Initial PR backlog

| Suggested PR | Deliverable | Acceptance |
| --- | --- | --- |
| PR-01 | Installable package scaffold, pytest/Ruff/mypy, Windows/Linux CI, dependency maintenance and deferred release gates | Reproducible development environment and passing initial tests |
| PR-02 | ffprobe adapter, stream domain model, `inspect` CLI with stable JSON | Correctly report track types, codecs, language and format without GUI |
| PR-03 | Compatibility policy and declarative operation plans | Exact stream mappings; reject unsupported codecs/containers |
| PR-04 | Safe MKV/MP4 remux, temporary outputs, validation | AC-01 to AC-07 and AC-12 as applicable |
| PR-05 | Track selection, metadata, extraction and safe cancellation | AC-08 to AC-10; related requirements and tests |
| PR-06 | Windows UI for inspection, track controls and preview/confirmation | End-to-end operation without CLI; clear errors |
| PR-07 | Final Windows CI, portable package, docs and smoke tests | MVP candidate ready for an explicitly authorized Release |

The PR sequence is a planning aid, not an excuse to merge untested functionality. Map each PR to the detailed FR/AC list.

## Recommended first Codex prompt

> Work only on PR-01 of the MediaTrack Forge roadmap. Read AGENTS.md, README.md and docs/01–10. Identify contradictions and record non-blocking assumptions in docs/10. Create a feature branch and implement only an installable Python skeleton, tooling, initial unit tests and Windows CI. Use English for every project artifact, comment, commit and PR. Do not implement the full GUI, transcode video/audio, merge your PR, or publish a Release. Run the relevant checks, describe actual results and open a small PR for review.

## Deliverables for every iteration

Goal; linked requirements/acceptance criteria; changed files; validation steps and results; risks; open decisions; and a recommendation for the next review gate.

Prefer small PRs. Do not edit `main` from a second session while Codex is implementing in another branch without reconciling the latest remote changes.

PR-01 implementation and deferred delivery gates are documented in [development and delivery](12-DEVELOPMENT-AND-DELIVERY.md). PR-02 remains a separate PR after PR-01 review and merge; no functional media acceptance criterion is claimed by foundation tests.

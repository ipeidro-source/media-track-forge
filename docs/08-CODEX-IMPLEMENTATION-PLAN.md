# 08 — Incremental Implementation Plan

## Governance

Owner approves requirements, merges and Releases; ChatGPT reviews product/architecture; Codex implements only separately authorized scopes with repeatable tests. Each code feature uses a branch and PR, never commits directly to main. Concurrent agents use separate git worktrees.

## Current queue (November 15, 2026)

| Order | Work | Acceptance/evidence |
| --- | --- | --- |
| Documentation PR (expected #7) | Consolidate status, license, roadmap, open NAS design and UX test protocol | Documentation-only diff, references and owner review |
| UX session (no code PR) | UX-01–UX-10 individually and real SMB mapped/UNC **input** verification | Reproducible P0–P3 observations in document 18 |
| GUI refinement PR (expected #8) | Resolve approved usability issues while preserving backend safety | GUI, real-media, cancellation and manual Windows tests |
| NAS output design and subsequent implementation (number TBD) | Separately approve safe SMB output architecture before any code | No overwrites/partial committed output, genuine SMB/failure recovery evidence |
| Packaging PR (historically PR-07, expected #9 or later) | PyInstaller `onedir` executable/ZIP, MIT and third-party notices, mandatory external FFmpeg checks, winget guidance, optional updates and Windows 10/11 acceptance | Owner-approved release candidate, no automatic publication |
| G5 acceptance | All FR/AC/user acceptance and release gates | Explicit separate Release decision |
| Future phases | Selective transcoding, conditional GPU, batch and library automation | New approved requirements/ADRs |

Actual GitHub PR numbers cannot be reserved and may differ as further work is interleaved. **Do not start Codex yet.**

## Historical completion

PR-01 foundation, PR-02 inspection, PR-03 planning, PR-04 safe remux, PR-05 SRT/extraction/cancellation and PR-06 GUI/D24 have all merged into main at `9298fd46` ([passing CI 43630367616](https://github.com/ipeidro-source/media-track-forge/actions/runs/43630367616)). Their original contracts, test counts, scope and decisions remain traceable through merged PRs. Historical Codex prompts and pending declarations are not current instructions.

## Expected future PR reports

Record linked requirements/ADR, scope, changed files, unit/integration/native Windows tests with actual evidence, CI checks, security compatibility, risks and explicit separation of implemented, verified, owner-accepted and released. No tags, merges or Releases without express owner authorization.

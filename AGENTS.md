# Codex Agent Instructions — MediaTrack Forge

Read `README.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md` and `docs/01` through `docs/13` before implementation. The repository is the source of truth. Never infer implementation status solely from the roadmap.

## Language policy — mandatory

Use **English exclusively** for repository files, code identifiers, comments, docstrings, documentation, tests, test names, user-facing UI text, error messages, commit messages, pull requests, Issues, release notes, and technical discussion recorded in the repository. Do not introduce Spanish documentation or mixed-language headings. User conversations outside the repository may take place in Spanish.

## Mandatory engineering rules

1. Stay within the MVP scope. No audio/video transcoding, GPU, Docker, large-scale recursive scanning, automatic subtitle synchronization, or AI features without explicit scope approval.
2. Separate desktop UI, application services, domain entities, media probing, operation planning, process execution, validation, and publication. The core must be usable without the GUI.
3. Invoke `ffprobe` and `ffmpeg` as subprocesses with argument arrays. **Never use `shell=True`** or execute user-supplied command strings.
4. Build **explicit stream mappings**. Never rely on FFmpeg's automatic stream selection. Preserve stream order and supported language/title/default/disposition metadata, or clearly disclose limitations.
5. Never alter or remove an original source. Produce temporary output, validate it, then publish safely. Existing final destinations must not be overwritten by default. On failure, retain useful diagnostics and apply a documented cleanup/recovery policy.
6. Support Windows subprocess-tree cancellation. Do not publish incomplete output. Report progress where feasible and indicate when progress cannot be calculated reliably.
7. Do not assume arbitrary codec/container compatibility. Implement a tested policy with actionable validation errors.
8. Use synthetic, local media fixtures for unit and integration tests. Do not require copyrighted sample content, external network access, private files, or credentials.
9. Every implementation PR must include relevant tests, affected documentation, lint/type-check evidence, and Windows CI validation.
10. Work on topic branches and submit reviewable PRs. Do not merge branches, create tags, or publish Releases without explicit user authorization.
11. When product behavior is ambiguous, record the assumption and alternatives in `docs/10-RISKS-AND-OPEN-QUESTIONS.md`; ask before committing to irreversible design choices.
12. Never claim an acceptance criterion has passed without concrete test evidence.
13. Keep related changes focused. If parallel agents are introduced, use separate branches and `git worktree` directories. Never let two agents modify the same working tree concurrently.

## GitHub Actions maintenance - mandatory

- Verify that every selected Action tag or SHA exists; inspect `runs.using` and release notes. Require supported Node.js 24 runtimes for JavaScript Actions; never rely on setup-node to change another Action's runtime or suppress deprecation warnings.
- Use explicitly versioned, currently supported runner labels (`windows-2025` and `ubuntu-24.04` for this foundation). No floating `*-latest` runners. Verify official support before changes and review quarterly and before release.
- Run YAML validation and actionlint for workflow changes. Use a verified official actionlint binary; review version and checksum updates.
- Keep weekly Dependabot updates enabled for GitHub Actions and Python manifests. Updates require review and the same mandatory CI as other changes.
- After pushing, inspect all actual CI job results and full logs, including setup and cleanup, for Node.js deprecation, runner-image migration/retirement, unsupported Actions and dependency compatibility warnings. Correct avoidable warnings before marking a PR ready. Record run URLs, skipped checks and any unavailable evidence; syntax validation alone is insufficient.
- Keep default workflow permissions minimal and publication gated by explicit owner authorization. A merge into main must never publish a Release.

## Current implementation baseline

PR-01 was merged and its main CI passed. Preserve its src layout, dependency pins, four layers and quality controls. PR-02 implements only read-only inspection using external ffprobe, immutable media snapshots, application orchestration, and the documented schema_version 1 JSON CLI. D1-D3 were approved by the owner for this iteration: versioned normalized JSON; external configurable local-only ffprobe with a 30-second default timeout; mandatory synthetic media integration on Windows 2025 and Ubuntu 24.04.

Keep unit tests runnable without media tools across the full Python matrix. Integration tests must fail when required tools/fixture codecs are missing; never silently skip mandatory media coverage. Run them on both Python 3.12 CI platforms. Preserve original ffprobe indices and ordering, all stream kinds and unknown metadata values. Changes to the public JSON contract must follow docs/13 compatibility policy.

No GUI, track planning/editing, external subtitle import, remuxing, extraction, transcoding, output publication, packaging or release automation is authorized by PR-02. FFmpeg may generate local synthetic fixtures only. Do not start PR-03 before separate authorization.

## PR reporting template

Describe the goal and linked acceptance criteria; list files changed; summarize architectural decisions; report executed checks and results; state residual risks and open questions. Never report a test as passed unless it was actually run.

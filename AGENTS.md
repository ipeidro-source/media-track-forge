# Codex Agent Instructions — MediaTrack Forge

Read `README.md`, `docs/00-CURRENT-STATUS.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md` and relevant specifications/ADRs before implementation. For UI refinement read `docs/18-UX-VALIDATION.md`. The repository is the source of truth. Never infer implementation status solely from the roadmap.

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

PR-01–PR-06 are merged on main at `9298fd46` with passing CI run 43630367616. PR-06 includes D24/ADR-039 read-only UNC/mapped inputs; real SMB evidence remains pending. **Network destinations are currently blocked**; new NAS output capability is an approved requirement, not an implemented safety design. Use [document 00](docs/00-CURRENT-STATUS.md) for live status.

Next work is documentation consolidation, then owner-led UX-01–UX-10, separately approved GUI refinements and portable PyInstaller `onefile` `.exe` and `onedir` ZIP packaging after GUI maturity. MIT for application code is approved. FFmpeg/ffprobe remain required external tools; startup checks, winget guidance and optional update checks are **planned**, not built. Future network output requires a separate security ADR and real SMB tests. Transcoding, GPU and batch remain deferred. Do not initiate Codex work without scoped owner approval, and never merge, tag or release without authorization.

## Git and CI discipline — mandatory

- Prepare a coherent complete change set **before pushing**. Perform local/static/documentation checks first; GitHub and hosted CI are review/verification gates, **not** a trial-and-error workspace.
- Prefer **one commit per coherent scope**; use at most two when a meaningful independent boundary justifies it. Avoid per-file commits, repetitive small fixes and unnecessary PR pushes. If a correction is necessary, batch related corrections before publishing.
- Read the existing document and current branch state before editing. Prefer a single atomic tree/commit update for multi-file documentation changes; review the diff and references before pushing.
- Do not repeatedly push while PR CI is running unless a real blocker requires intervention. Allow the final checks to finish, and distinguish cancelled/superseded CI from actual failures.
- No history rewrite, force push or destructive cleanup without explicit owner authorization. Do not use a large series of commits as a substitute for proper preparation.
- Report exactly which local checks ran and which hosted CI run validates the **final head commit**. A previously green run does not validate a later commit.

## PR reporting template

Describe the goal and linked acceptance criteria; list files changed; summarize architectural decisions; report executed checks and results; state residual risks and open questions. Never report a test as passed unless it was actually run.

## D24 network input boundary - owner approved

Allow trusted Windows mapped-drive and direct UNC regular files as read-only media/
SRT sources. Preserve resolved source identity, original stream indices, reinspection,
revision binding and change detection. Reject URL/protocol inputs and non-file device paths;
keep file-only FFmpeg/ffprobe arguments. Inputs do not authorize network outputs:
reject UNC/remote/unknown Windows destinations, recheck before staging/publication
and retain all private-staging/no-overwrite/atomic/cancellation/cleanup protections.
Show bounded specific controlled InspectionError messages in the GUI; never expose
raw vendor logs or unexpected exception text. Simulated UNC tests are not real SMB
evidence. Real-share checks are opt-in with owner-supplied tiny synthetic fixtures;
report unavailable evidence, session/permissions, filesystem metadata/cache and OS
I/O timeout limitations. Do not create shares, mappings or credentials implicitly.
ADR-039 records D24; ADR-034..038 retain their PR-06 meanings.

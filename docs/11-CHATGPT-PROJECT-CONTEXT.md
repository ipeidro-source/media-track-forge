# 11 — ChatGPT Project Context and Knowledge Management

**Project:** MediaTrack Forge  
**Repository:** https://github.com/ipeidro-source/media-track-forge  
**Document status:** Context-management policy — v0.3, November 14, 2026  
**Language:** English for all versioned project artifacts

## 1. Purpose

This document defines how MediaTrack Forge's project knowledge is organized, retrieved, updated, and handed over between ChatGPT, Codex, and GitHub. It is **not** the ChatGPT instruction prompt and is **not** an implementation specification.

The repository is the source of truth for approved requirements, architecture, decisions, implementation, and roadmap status. ChatGPT project sources are convenient context snapshots, **not automatically synchronized replicas** of the repository.

## 2. Roles and instruction files

| Location | Purpose | Maintenance |
| --- | --- | --- |
| `CHATGPT_INSTRUCTIONS.md` | Canonical, version-controlled text to copy into the ChatGPT project's *Project instructions* field | Update in GitHub and manually apply the revised instructions in ChatGPT |
| `AGENTS.md` | Repository-level development instructions for Codex and other coding agents | Read and follow in coding sessions; update by reviewed PR |
| `docs/11-CHATGPT-PROJECT-CONTEXT.md` | Knowledge hierarchy, context recovery, synchronization, and continuity procedures | Update when the collaboration workflow changes |
| `README.md`, `docs/01`–`docs/10` | Product and engineering specifications, decisions, requirements, and implementation plans | Update with approved design or delivery changes |
| Source code, tests, commits, and merged PRs | Evidence of what is actually implemented | Validate against the current repository state |

`CHATGPT_INSTRUCTIONS.md` is a project file **and** a template for the ChatGPT instruction field. Editing the GitHub file does not update the ChatGPT UI automatically. Similarly, adding a GitHub URL to an instruction does not itself grant repository access.

## 3. Repository and source hierarchy

Repository: **`ipeidro-source/media-track-forge`**. Before relying on its contents, confirm that the repository exists and that the GitHub connection or authorized access is available.

Use the following precedence, depending on the question:

1. **Implementation status:** current code, tests, relevant commits, merged PRs, and Releases. A documented requirement does not prove that code exists.
2. **Approved product and design intent:** the latest accepted specifications and architecture decisions committed to the repository.
3. **Current work:** open PRs, feature branches, and Issues; identify these explicitly as proposed or in progress, not accepted.
4. **ChatGPT project sources:** uploaded Markdown files and conversation summaries, which may be older snapshots.
5. **Conversation proposals:** suggestions and discussions that are not yet recorded as approved decisions.

If two sources conflict, identify the conflict and the relevant versions/commits. Do not silently replace an approved decision. When GitHub access is unavailable, state what sources were used and that their freshness could not be verified.

## 4. Documentation map

| File | Primary content |
| --- | --- |
| `README.md` | Product overview and documentation index |
| `docs/01-VISION-AND-SCOPE.md` | Product vision, target users, differentiators, scope |
| `docs/02-ROADMAP.md` | Phases, effort estimates, approval gates |
| `docs/03-MVP-REQUIREMENTS.md` | Functional requirements and acceptance criteria |
| `docs/04-ARCHITECTURE.md` | System components, boundaries, processing flow |
| `docs/05-DOMAIN-MODEL.md` | Entities, state transitions, invariants |
| `docs/06-ARCHITECTURE-DECISIONS.md` | Accepted decisions, proposals, and trade-offs |
| `docs/07-QUALITY-AND-TESTING.md` | Test strategy, CI, validation, release quality |
| `docs/08-CODEX-IMPLEMENTATION-PLAN.md` | PR sequence, Codex tasks, review process |
| `docs/09-GITHUB-AND-DEVELOPMENT.md` | Repository configuration and local development setup |
| `docs/10-RISKS-AND-OPEN-QUESTIONS.md` | Risks, technical debt, unresolved decisions |
| `docs/11-CHATGPT-PROJECT-CONTEXT.md` | This knowledge-management policy |

Read only the documents relevant to a question when possible, but review related ADRs and requirements before recommending material architectural or scope changes.

## 5. Project baseline — November 14, 2026

**Current status:** planning and documentation. No product implementation is established by this document. Confirm actual repository state whenever discussing progress.

- **Product:** independent Windows-first application for local media track management; not part of YouTube Smart Downloader.
- **MVP:** inspect media using ffprobe, select/add/remove/reorder/extract streams, remux compatible inputs into MKV or MP4, including **video-only outputs**, without video or audio transcoding.
- **Input expectations:** AVI, MP4, and MKV, subject to codec and output-container compatibility; no guarantee that every codec can be copied to every container.
- **Subtitle processing:** SRT as a required MVP input; MP4 text subtitles may need an explicit conversion to `mov_text`.
- **Phase 1:** selective video/audio transcoding and quality profiles, subject to a separate approval gate.
- **Phase 2:** batch processing, rules, GPU-aware options, and size estimates, subject to a separate approval gate.
- **Architecture:** Windows-native development in VS Code, Python/CustomTkinter proposed, FFmpeg/ffprobe subprocess integration, GUI-independent processing core.
- **Safety:** preserve original media, require explicit track selection, disallow silent video/audio transcoding, validate staged outputs before publication.
- **Delivery model:** ChatGPT supports specification and review; Codex implements in small PRs; the project owner approves scope changes, merges, tags, and Releases.

These are planning decisions, not evidence that a feature is implemented.

## 6. Language policy

All artifacts intended for GitHub or the ChatGPT project's persistent sources must be written in **English**: requirements, architecture, ADRs, comments, docstrings, identifiers, tests, UI copy, GitHub Issues, commit messages, PR descriptions, release notes, and Codex prompts.

The project owner and ChatGPT may converse in Spanish. Approved outcomes discussed in Spanish must be recorded **in English** in the appropriate repository document.

## 7. Starting a new ChatGPT conversation

1. Read the project's active instructions (maintained from `CHATGPT_INSTRUCTIONS.md`).
2. Identify the user task and the relevant documents in Section 4.
3. For questions about recent progress, PRs, code, CI, or current decisions, inspect the connected GitHub repository first where access is available.
4. Distinguish **implemented**, **approved**, **proposed**, and **deferred** items.
5. If a required document or repository is inaccessible, explain the limitation rather than guessing.
6. Do not reopen an accepted decision without a reason or treat a previous chat's draft as an approved specification.

## 8. Updating and synchronizing context

After an approved product or architecture decision:

1. Update the relevant spec/ADR/roadmap Markdown files **in English**, normally in a dedicated branch/PR.
2. Record the rationale, effect on scope and tests, and any newly created risk or open question.
3. Merge only with the owner's approval; do not treat an unmerged PR as authoritative.
4. If the decision changes how ChatGPT must operate, update `CHATGPT_INSTRUCTIONS.md` **and manually update the Project instructions field**.
5. If a ChatGPT project source contains an older uploaded file, replace or refresh it manually, or make a fresh repository retrieval when needed. Uploaded snapshots do not update automatically when GitHub changes.
6. Update the project baseline in Section 5 only when materially necessary; keep it concise and date-stamped.

After Codex delivers an implementation, review code/tests and PR evidence against requirements before changing any feature's status from planned to implemented.

## 9. Working with Codex and concurrent development

Codex must follow `AGENTS.md`, the relevant requirement documents, and the reviewed PR scope. ChatGPT should review PR diffs and associated tests against accepted specifications. No direct changes to `main`, merges, tags, or Releases without explicit owner authorization.

For parallel coding agents, use separate branches and separate `git worktree` directories. Do not allow concurrent agents to edit the same working tree. Recheck the base branch before reconciling changes.

## 10. Context recovery checklist

When resuming work after a long gap, establish:

- Latest merged commit on `main`, open PRs, current Release, and CI status (when accessible).
- Latest accepted ADRs and any changed acceptance criteria.
- Current phase/gate in `docs/02-ROADMAP.md`.
- Outstanding tasks in `docs/08-CODEX-IMPLEMENTATION-PLAN.md` and unresolved issues in `docs/10-RISKS-AND-OPEN-QUESTIONS.md`.
- Whether Project instructions and uploaded sources still match GitHub's current versions.

Summarize what is implemented, in progress, and pending, with references to concrete GitHub files/PRs when available. Never imply a repository was checked unless it actually was.

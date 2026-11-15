# 02 — Roadmap, Estimates, and Approval Gates

This document owns **planning, sequencing and approval gates**. Current implementation and test evidence are recorded in [document 00](00-CURRENT-STATUS.md); detailed Codex backlog belongs to [document 08](08-CODEX-IMPLEMENTATION-PLAN.md). Historical PR narratives and rough effort estimates are preserved in merged PRs/commits and are not live delivery promises.

## Present MVP and upcoming work

| Milestone | Scope | Status |
| --- | --- | --- |
| Backend MVP | Inspection, track planning, SRT import, safe remux/extraction, progress/cancellation | Implemented PR-01–PR-05; owner acceptance separate |
| Windows desktop GUI | CustomTkinter/ttk, review/confirmation and progress | Implemented PR-06; human UX and Win10/11 checks pending |
| Documentation consolidation | Live status, traceability, cleanup, roadmap, UX protocol and MIT | Merged PR-07 at e3ee5af391 |
| Usability validation | UX-01–UX-10 and real SMB **read** test | Owner audit findings recorded in document 18; full protocol and SMB acceptance pending |
| PR-08 reliability and UX | Backend B1–B4, then U1–U10 behind passing backend CI | Implemented on PR-08 review branch; final CI and owner acceptance separate |
| Network destination support | Write to trusted UNC/mapped NAS while preserving safe publication | Owner-approved **requirement**, design and implementation pending |
| Windows packaging | Two downloadable artifacts: PyInstaller `onefile` `.exe` and `onedir` portable ZIP; no installer, FFmpeg external and mandatory | Planned after UI maturity, no executable or release yet |
| MVP acceptance/release | Owner-reviewed AC, consumer Windows and real-share evidence where applicable | Pending; explicit Release authorization required |
| Phase 1 | Selective H.264/H.265 video and AAC audio transcoding, quality presets | Deferred |
| Phase 2 | Batch automation, subtitle matching, GPU if justified, resource/size planning | Deferred |
| Optional future | Additional codec/subtitle combinations, NAS libraries, Plex/Jellyfin, headless Docker/CLI and commercial options | Ideas, separate approvals |

Original early estimates (MVP 25–40 h, selective transcoding +30–50 h, batch/automation +40–70 h, quality/delivery +20–35 h; overall 115–195 overlapping hours) remain **historical**; re-estimate after usability and NAS-output design.

## Original approval gates (identifiers preserved)

- **G0:** Repository and documentation established — complete.
- **G1:** Core scaffold and inspection — implemented.
- **G2:** Compatibility and declarative plans — implemented.
- **G3:** Safe remux/extraction and E2E validation — implementation present; owner acceptance separate.
- **G4:** Windows GUI and portable packaging — GUI code implemented, UX/packaging and Windows 10/11 acceptance incomplete.
- **G5:** Full reviewed MVP; Release only by express owner approval — pending.
- **G6:** Separate approval to start transcoding, GPU and batch — not given.

## Order and non-negotiable boundaries

1. Documentation PR reviewed independently; no automatic merge.
2. Execute UX scenarios individually and record P0–P3 human findings in [18](18-UX-VALIDATION.md).
3. Define GUI refinements from evidence, independently approve Codex specification, preserve immutable inputs, warning/confirmation revision binding, safe staging, validation and cancellation.
4. Evaluate NAS output safety separately (provisional ADR-040): local validated staging and safe remote publication versus controlled private remote staging; demand evidence for atomic visibility, no overwrite, cleanup, ACL, disconnect and durability. **Do not simply allow UNC destinations under D24.**
5. After GUI maturity prepare both standalone Windows `.exe` and portable `onedir` ZIP, startup FFmpeg/ffprobe compatibility checks, winget guidance and optional updates; no silent installs. Validate license notices, checksums and Windows 10/11.
6. Owner decides whether all G4/G5 evidence suffices; tagging/publication requires separate explicit authorization.

The historical label “PR-07 packaging” is superseded by the owner-approved sequence: a documentation PR first, then UI refinement and packaging after UX. GitHub allocates actual PR numbers; NAS implementation can change numbering. Requirements live in [03](03-MVP-REQUIREMENTS.md), approved decisions in [06](06-ARCHITECTURE-DECISIONS.md), open risks in [10](10-RISKS-AND-OPEN-QUESTIONS.md).

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
| ADR-007 | Accepted for PR-01; GUI deferred | Python 3.11+, pytest, Ruff, mypy; CustomTkinter remains proposed | Explicit PR-01 scope approval; no GUI dependency |
| ADR-008 | Proposed / pending | MIT for application code | Easy contributions; review redistribution constraints |
| ADR-009 | Accepted target; implementation deferred | PyInstaller Windows `.exe`, versioned portable ZIP and SHA256SUMS.txt | Explicit PR-01 delivery direction; no executable or release yet |
| ADR-010 | Deferred | GPU acceleration and specialized codecs | Phase 2; requires capability/licensing assessment |
| ADR-011 | Accepted baseline | **English-only project artifacts and English-first UI** | International consistency; avoid mixed-language documentation |
| ADR-012 | Accepted baseline | Versioned docs and code, reviewable PRs, no automatic merges | Traceability across ChatGPT and Codex work |
| ADR-013 | Accepted baseline | Explicit source-to-output stream mapping, with video-only output permitted | Predictable track-level operation |

## Decision-change policy

Any material change to media integrity, track semantics, compatibility policy, licensing, CI, packaging or UX requires a dated ADR update documenting context, alternatives, choice, trade-offs, and approval state.

Phase 1/2 ADRs are not authorization to extend the MVP. The project owner approves scope changes.

## Documentation language rule

All ADRs, technical notes, source comments, issues, commits, PR descriptions, UI copy and release notes **must be in English**. Conversational Spanish does not change this repository-wide policy.

## November 14, 2026 - PR-01 delivery decisions

ADR-014 (accepted for PR-01): setuptools src layout, a single literal package version, no runtime dependencies, exact development dependency pins and four layer namespaces. Alternatives were a GUI-bound scaffold or premature media interfaces; both add scope without testable product behavior.

ADR-015 (accepted for PR-01): Node 24 Actions with exact stable tags, explicit supported Windows 2025 / Ubuntu 24.04 images, weekly reviewed Dependabot PRs, actionlint and actual CI log review. Tags favor readable maintenance over SHA immutability; runner labels still receive image updates. Release automation remains disabled until meaningful executable tests and licensing gates exist. Details and evidence: [development and delivery](12-DEVELOPMENT-AND-DELIVERY.md).

## November 14, 2026 - approved PR-02 D1-D3

- ADR-016 / D1 (owner approved): public schema_version 1 with explicit normalized
  source/container/streams/chapters, null missing scalars, preserved source indices
  and stream order including data/attachments/unknown kinds. Frozen dataclasses
  with tuple fields keep snapshots independent of presentation. Raw ffprobe JSON
  is not the public API; breaking changes require a schema version bump.
- ADR-017 / D2 (owner approved): external PATH-discovered ffprobe, explicit trusted
  executable override, default 30-second configurable timeout, shell-free arrays
  and file-only protocol whitelist. No bundled FFmpeg and no product FFmpeg call.
  Capture caps are 8 MiB stdout / 64 KiB stderr; overflow is a controlled response
  error. OS filesystem sandboxing is outside this adapter's guarantees.
- ADR-018 / D3 (owner approved): real FFmpeg-generated synthetic fixtures, mandatory
  Windows 2025 and Ubuntu 24.04 Python 3.12 integration, unit tests across the full
  matrix. Missing tools/codecs fail, never skip. Supported package managers install
  CI tools without adding Actions. Versions are recorded rather than guessing an
  exact cross-platform codec build.

Alternatives rejected for this scope: exposing raw vendor JSON, renumbering streams,
shipping binaries, network probing, adding a parsing/CLI framework, or optional
CI media checks. Inspection does not settle output compatibility or editing design.

## November 14, 2026 - approved PR-03 D4-D8

- ADR-019 / D4 (accepted): conservative kind/codec/container allowlist, enabled only
  with mandatory real muxing evidence on both CI platforms. Candidates are not
  support claims. Leave DTS, AC-3/E-AC-3, ASS/SSA and bitmap subtitles blocked in
  this iteration; no audio/video encoding. Alternative automatic codec recognition
  would overpromise output compatibility.
- ADR-020 / D5 (accepted): references use full source identity plus original index;
  explicit selections group video/audio/subtitle/attachment, stably ordered within
  each group. Output indices follow maps. Multiple defaults per kind block rather
  than silently choosing a winner. Implicit omissions require acknowledgement.
- ADR-021 / D6 (accepted): ExternalTrack is an extension record. No importer or SRT
  parser is implemented. A validated claim must match supplied inspected metadata;
  no index/codec is derived from a suffix. Alternative premature importing exceeds
  scope. Inspected SubRip can be explicitly planned for mov_text conversion.
- ADR-022 / D7 (accepted): explicit supported metadata, chapter and attachment
  decisions, warnings for losses/uncertainties, blockers for unvalidated selected
  content. Primary MKV chapter times/titles and text/plain attachments only are
  enabled. Per-chapter titles must be explicitly set after metadata auto-copy is
  disabled. Exact metadata bytes, chapter IDs and player semantics are not promised.
- ADR-023 / D8 (accepted): immutable declarative plan_version 1, separate public
  serialization and command generator. Intrinsic validity, warning acknowledgement
  and future execution confirmation are distinct. No executable arguments for
  blocked/unacknowledged plans. Alternative mutable vendor-command dictionaries
  would hide intent and invalidate source identities.

  PR-03 D8 review correction: warning codes must be paired with the SHA-256
  revision of the exact reviewed immutable intent and diagnostic occurrences.
  Source/order/metadata/output/chapter/external or diagnostic changes invalidate
  prior acknowledgement even if codes are unchanged. Acknowledgement state and
  generated arguments do not affect the revision. Intrinsic validity, warning
  acknowledgement and future final confirmation remain distinct. Unbound code
  sets are ineffective; blocked/unacknowledged plans expose no arguments. This
  establishes the initial unmerged plan v1 contract without altering inspection v1.

See [contract v1](14-OPERATION-PLAN-CONTRACT.md) for detailed choices and limitations.
These decisions authorize planning and test-harness muxing only, not PR-04 execution.

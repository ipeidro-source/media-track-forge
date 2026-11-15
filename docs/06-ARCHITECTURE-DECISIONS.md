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
| ADR-007 | Accepted; GUI implemented under ADR-034 | Python 3.11+, pytest, Ruff, mypy and CustomTkinter desktop | Preserve core independence |
| ADR-008 | Accepted November 15, 2026 | MIT for application-owned code | Permissive license; third-party notices and redistribution obligations remain separate |
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

## November 14, 2026 - approved PR-04 D9-D13

- ADR-024 / D9 (accepted): owner-private, exclusive same-filesystem staging and
  exclusive os.link publication after validation/fsync; no rename/replace/copy
  fallback. Atomic name visibility is not power-loss durability. Local filesystem
  support is proven by tests, not assumed for network/FAT-like filesystems.
- ADR-025 / D10 (accepted): independent ffprobe validation of layout, codecs,
  supported metadata, chapters/attachments and timing. The per-operation timing
  budget uses available timestamp ticks plus known frame/packet boundaries;
  missing metadata is explicitly unverified. Structural mismatches are errors,
  not blanket warnings. Metadata alone is not full decode integrity.
  PR-04 D10 review clarification: only genuinely unknown expected duration may be
  unverified with a warning. Known expected duration requires observed duration
  and a metadata-derived timing tolerance; missing either blocks publication.
  Matching numbers alone do not justify omitting the timing check. No universal
  fallback tolerance or alternative integrity waiver is implemented.
- ADR-026 / D11 (accepted): reviewed and explicitly confirmed revision must match
  full fresh source inspections and a regenerated plan. Repeat before publication;
  ignore caller arguments even when execution_allowed is true. Bind only fresh
  approved mappings to the reserved staging target. The fixed -n becomes -y only
  for that owned preallocated file, never for the final pathname.
- ADR-027 / D12 (accepted): automatic owned-temporary cleanup after proven process
  stop, stable bounded diagnostics and explicit cleanup failure. No raw logs are
  retained. If stop/ownership is uncertain, retain artifacts and report it rather
  than deleting unknown/active files. Never delete a published final as rollback.
- ADR-028 / D13 (accepted): hidden shell-free trusted native execution with bounded
  pipes, finite timeout, Windows Job Object or Ubuntu session/group containment.
  Ordinary descendants are tested; deliberate malicious escape is not sandboxed.
  Worker-callable service and immutable states are PR-05 extension boundaries,
  not authorization for cancellation/progress UI or batch scheduling.

Alternatives rejected: direct final writes, check-then-rename, copying placeholder
finals, trusting a supplied command tuple, universal fixed 50 ms duration tolerance,
unbounded logs and silently weakening unsupported publication/termination behavior.
See document 15 for exact guarantees, observed evidence boundaries and limitations.

## November 14, 2026 - approved PR-05 D14-D18

- ADR-029 / D14 (accepted): bounded strict UTF-8/BOM local SRT structural validation
  plus independent ffprobe inspection, explicit external source roles and repeated
  validation before execution/publication. Alternatives: extension-derived codec,
  ffprobe-only validation or arbitrary codepage guessing; rejected for ambiguous
  timing/identity. Accept harmless cue-label/line-ending/overlap variations. Existing
  ExternalTrack v1 fields remain; audio imports stay blocked. Supersedes ADR-021's
  importer deferral only for this approved SRT scope.
- ADR-030 / D15 (accepted): separate one-stream extraction matrix and declarative
  version 1 contract, explicit MP4 Annex B filters/ADTS packaging and approved text
  conversion. Alternatives: generic transcode framework or broad codec recognition;
  rejected. Only document 16's six combinations are enabled with required real tests.
  AC-3 and all other candidates remain unsupported. Elementary validation checks
  layout/properties and full positive equal selected packet counts, including when
  elementary timing is absent. This independent truncation check is extraction-only,
  not a remux duration waiver or full decode/content proof. AAC LC priming/padding
  has a sample-derived allowance; no arbitrary universal tolerance is used.
- ADR-031 / D16 (accepted): per-job thread-safe cooperative cancellation with a short
  lock linearizing cancellation against exclusive publication. Alternatives: global
  flags, deleting final output on cancellation or holding a lock throughout processing;
  rejected. Successful publication commits; later cancellation cannot undo it. Process
  quiescence precedes cancelled/cleanup. Blocking probes reach their existing bounds;
  pending cancellation still prevents publication. Trusted process/namespace limits
  from PR-04 remain. No scheduler or GUI cancellation control is introduced.
- ADR-032 / D17 (accepted): structured FFmpeg progress pipe, bounded incremental lines,
  one latest time and synchronous worker observer delivery. Alternatives: parsing
  human stderr, unbounded event queues or invented percentages; rejected. Selected
  timing only, indeterminate fallback, monotonic processing capped at 99 and final
  100 only after completion. Observer exceptions disable/report the observer; trusted
  callbacks must return promptly. Blocking callbacks can delay observation.
- ADR-033 / D18 (accepted): reuse the existing execution orchestrator with small
  operation-specific regeneration/argument/validation hooks. Alternatives: a second
  extraction process stack or a generic job framework; rejected. Distinct extraction
  serialization avoids changing inspection schema v1/remux plan v1 meanings. Existing
  diagnostics and remux allowlist remain stable; no new production dependencies.

Context, exact matrix, alternatives' consequences, timing/packet limitations, API
contracts and test boundaries are detailed in document 16. These decisions authorize
backend implementation, not G3 acceptance, GUI, packaging or release publication.

## November 14, 2026 - approved PR-06 D19-D23

- ADR-034 / D19 (accepted): desktop controls need a native Python toolkit while the
  backend remains display-independent. Choose pinned CustomTkinter 6.0.0 with ttk
  Treeview and native dialogs; preserve lazy GUI imports and the inspection CLI.
  Alternatives were Electron/web server or a custom table framework; rejected for
  dependencies and maintenance. The trade-off is Tk accessibility and untyped toolkit
  boundaries; native tests and a scoped mypy import override cover the adapter.
  Runtime CLI installations now also install GUI libraries; no display is initialized.
  This resolves ADR-007's GUI proposal without changing tooling decisions.
- ADR-035 / D20 (accepted): users need direct inspection/edit/review/results without
  a wizard. Choose one window with Media/Operation/Execution tabs, original immutable
  references, explicit keep/set/clear metadata and within-kind order. Alternative
  auto-resolving defaults/omitting incompatible tracks was rejected. Initially include
  all detected tracks so unsupported selections stay visible as blockers; this can
  require correction before a valid plan. Source replacement clears external state.
  Only backend-supported extraction extensions are offered; no second codec policy.
- ADR-036 / D21 (accepted): review cannot authorize another intent. Use generation-
  invalidated immutable plans, all-occurrence warning presentation and explicit
  revision-bound acknowledgement rebuild, followed by a distinct default-No execution
  confirmation. Alternatives: auto-acknowledgement or execution_allowed alone; rejected
  as unsafe. Any edit, including pending metadata, clears review. Worker results cannot
  restore stale authority. The cost is repeated review after edits; backend regeneration
  remains mandatory and public contracts 13-16 are unchanged.
- ADR-037 / D22 (accepted): blocking media/filesystem work must not freeze Tk. Choose
  one non-daemon worker with bounded discrete reply/latest progress and main-thread
  polling. Alternatives: widget process management, unbounded queue or abrupt close;
  rejected. Disable conflicting edits, use the existing job cancellation token and
  wait for safe terminal cleanup before closing. Unverified cleanup keeps recovery
  visible and blocks new operations; published results are never rolled back. Probe
  cancellation still waits for existing timeout bounds. No scheduler/database is added.
- ADR-038 / D23 (accepted): choose system-following theme, matching ttk colors,
  resizable/scrollable layout, toolkit DPI support and explicit keyboard adapters.
  Alternatives: fixed light-only styling or packaging in this PR; rejected. Native
  smoke uses one root per isolated process after local repeated-root Tcl failures;
  exact display/widget evidence is reported separately from manual Windows 10/11
  acceptance. Widget scaling tests do not certify actual OS DPI or screen readers.
  Accessibility limitations remain documented. PR-07 owns executable/ZIP/installer
  and release gates; no packaging or release is authorized here.

Document 17 records context, APIs, consequences, test procedure and residual limits.
These owner-approved choices authorize PR-06 implementation, not automatic G4/MVP
acceptance, branch merging, tags or releases.

## November 14, 2026 - approved PR-06 D24

ADR-039 / D24 (accepted): read-only Windows file-share media sources.

Context: strict Path.resolve() can turn a valid mapped SMB filename into UNC;
the former local-only input check rejected both that result and direct UNC paths.
This blocked legitimate trusted media/SRT inspection and existing remux/extraction
to local output. ADR-034 through ADR-038 already belong to the desktop decisions.

Decision: accept regular readable Windows filesystem sources, including mapped
drives resolving to UNC and direct UNC. Keep strict resolved path/size/mtime source
snapshots, original indices, full fresh inspection and exact revision binding.
The canonical UNC identity, rather than the original drive-letter alias, is the
reviewed execution input. A later remapping cannot silently redirect that plan;
new inspection of a different mapping produces another identity/revision. Source
handles remain read-only. No credentials, mappings or shares are created/stored.
Protocol URLs/non-file device paths stay blocked; ffprobe/FFmpeg retain file-only
whitelists. Extended UNC file identities are allowed for consistent reinspection.

Output policy remains separate: UNC and Windows remote/unknown volumes are rejected
using canonical path checks and GetVolumePathNameW/GetDriveTypeW classification,
including mapped outputs that retain a drive letter. Recheck at actual staging and
exclusive publication boundaries. Local private ACLs/modes, owned staging, validation,
no overwrite, atomic link, cancellation commitment and cleanup are unchanged.
GUI InspectionError presentation now retains bounded specific controlled messages;
unexpected exception/vendor text stays suppressed.

Alternatives: preserve drive letters without resolution (rejected: weaker alias
identity/remapping semantics); accept only direct UNC (rejected: breaks normal
Windows usage); permit SMB outputs (rejected: unvalidated safety/capability scope);
mount/copy/download inputs automatically (rejected: credentials, writes and scope).
Reusing the filesystem inspection path avoids a second media/network adapter.

Trade-offs/limitations: file protocol is not an OS sandbox and Windows file providers
perform their own network access/authentication. SMB availability/permissions and
drive mappings are tied to the application's session; metadata may be cached/coarse.
Path/size/mtime plus inspection is not cryptographic content identity or a network
transaction snapshot. Python filesystem calls can wait on OS/redirector timeouts
beyond subprocess limits; cancellation remains cooperative at safe boundaries.
Server/share aliases are not universally deduplicated. Network/remote output support
needs a separate capability/atomicity/ACL/durability decision and real evidence.

Consequences: schema fields, codecs and plan/extraction versions are unchanged;
the accepted Windows input set expands without changing existing local payloads.
Regression tests simulate UNC normalization offline and are explicitly not SMB
proof. The opt-in check_network_sources.py runs actual UNC/mapped media/SRT with
real tools and local output when synthetic shares are supplied; Get-SmbConnection
evidence establishes transport/dialect separately. No real SMB share was available
for validation in the current agent environment (no mapping; enumeration unavailable).
Document 17 records the manual evidence procedure and remaining limits.

## November 15, 2026 — owner-approved decisions after audit

**ADR-008 (accepted):** License application-owned source under MIT. This does not relicense FFmpeg, PyInstaller, Python, GUI dependencies or any third-party components; inventory redistributed dependencies and notices before shipping. MIT selection does not authorize a Release.

**ADR-003 and ADR-009 clarified (approved direction, not implementation):** FFmpeg/ffprobe remain mandatory external tools. A future startup check should validate executable presence, compatibility and necessary capabilities, with actionable winget `Gyan.FFmpeg` installation guidance (verify package identifier at implementation). Compatible older builds may operate. Update notices must be optional, nonblocking and never silently install or upgrade. Distribution target is **two Windows artifacts**: a standalone PyInstaller `onefile` `.exe` for direct use and a versioned ZIP containing the PyInstaller `onedir` portable build, without an installer. Build/test `onedir` before `onefile` for diagnosis. Verify onefile temporary extraction/startup, clean shutdown, permissions, antivirus/SmartScreen behavior, checksums, third-party notices and Windows 10/11 acceptance before publication.

**Provisional ADR-040 — OPEN architectural design (not an accepted solution):** Owner approves the future requirement to write output to trusted mapped/UNC NAS destinations. ADR-039's current local-only output safety restriction remains active until a separately reviewed design and real SMB safety tests exist. Compare local validated staging plus safe remote publishing with private remote-share staging; consider exclusive no-overwrite semantics, incomplete transfer visibility, permissions/ACL, remapping and path races, disconnections, cancellation, cleanup and durability. Never implement by merely disabling the network-output prohibition.

Video/audio transcoding, conditional GPU and automation remain later phases, without implementation authorization.

## November 15, 2026 — PR-08 backend decisions

ADR-041 (proposed implementation under owner-approved B1–B4 scope): replace the
subtitle packet-equality assumption in ADR-030 with independently scanned text cue
and millisecond timing comparisons. MP4 mov_text clear samples describe gaps, not
SRT cues. Audio/video retain positive equal packet scans and timing checks. Failed
checks carry specific invariant codes as well as EXTRACTION_INVALID. Reject malformed,
oversized, unprobeable or unmatched output; never waive independent validation.
Alternatives: suppress validation or count only nonempty output; rejected because
neither verifies retained source cues. Bounded packet dumps trade capacity for
auditable evidence; overflow fails safely. Exact owner MKV failure is unresolved.

ADR-042 (proposed implementation of approved metadata direction, supersedes the
blanket tag exclusion in ADR-022): explicitly preserve tested compatible primary
container and stream tags, retaining unrelated values across edits. Unsupported
names and cross-container losses require acknowledgement; do not promise arbitrary
tags, byte identity or silently normalize unknown names. Known names may change
case through muxing. Independent validation checks promised values. Plan version 2
adds output_format_tags and invalidates version 1 review/confirmation by regeneration;
inspection/extraction presentation versions stay unchanged. Alternative unversioned
semantic change was rejected. Owner review of this version migration remains pending.

ADR-043 (proposed implementation of approved B3/B4): extend only synthetic-tested
compatibility pairs (MP4 VP9/Opus to MKV, explicit mov_text to SubRip in MKV, Matroska
MP3 extraction). Keep one backend policy per operation and audio/video copy only.
Inspect replacement media before replacing session intent; failure retains edits,
but invalidates review authority and rejects stale asynchronous results. Inspection
remains content-based; video eligibility is a separate planning condition.

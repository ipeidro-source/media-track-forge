# 10 — Risks, Technical Debt, and Open Questions

## Risk register

| ID | Risk | Mitigation |
| --- | --- | --- |
| R01 | Output container incompatible with one or more input codecs | Probe each stream and validate the plan; block rather than implicitly transcode; suggest MKV |
| R02 | Text and bitmap subtitles require different operations | Type subtitle streams explicitly; only permit supported text→`mov_text` transformations |
| R03 | Chapters, tags and attachments may disappear during remux | Plan metadata mapping explicitly, test preservation and report omissions |
| R04 | FFmpeg versions/builds have different capabilities | Detect installed executables and verify tested behavior |
| R05 | Corrupt input or failed operations can produce bad output | Staged output, post-run validation, no overwrite of source/destination |
| R06 | File locks, long Windows paths and Unicode issues | Real Windows integration tests; argument arrays; safe path handling |
| R07 | Cancellation can leave orphaned processes | Explicit Windows process-tree management |
| R08 | FFmpeg redistribution and codec patent/license constraints | Keep executables external initially; legal review before bundling |
| R09 | Promised file-size savings may be inaccurate | Separate stream removal from transcoding and disclose estimation uncertainty |
| R10 | Overly broad MVP | Enforce approval gates and small PRs |
| R11 | Mature free competitors limit general converter differentiation | Focus on predictable track operations and later library automation |

## Current open risks and decisions (November 15, 2026)

- PR-08: synthetic MP4 gaps reproduce clear-sample packet mismatch. The local MKV
  SubRip index-5 fixture passes; the exact owner UNC MKV failure is not reproduced
  and must not be attributed to MP4 clear samples. New invariant diagnostics enable
  further diagnosis without vendor logs. No owner media or real SMB evidence exists here.
- PR-08 proposes plan version 2 for metadata preservation (ADR-042), requiring fresh
  review for v1 callers. Compatible known tags are explicitly mapped and validated;
  arbitrary tags, casing and FFmpeg-generated tags cannot be guaranteed byte-identical.
  Unsupported names require acknowledgement. Alternative implicit metadata copying
  was rejected as unverifiable. Owner approval of the migration is pending review.
- Subtitle packet evidence uses the existing 8 MiB probe cap and 100,000 cue limit;
  large dumps, unavailable durations or unsupported text layouts block safely.
- Multi-primary media composition remains future product scope, not PR-08 functionality.
- PR-08 direct metadata language editing validates lowercase three-letter syntax; it
  does not infer or rewrite unknown source codes or certify a complete language registry.
  Native scaling tests do not certify OS DPI, screen readers, multiple monitors or
  consumer Windows ergonomics. Final owner review of the revised workflow is pending.

- NAS/SMB output is an owner-approved **new requirement**, not implemented; choose validated secure staging, exclusive no-overwrite publication and recovery under disconnect/ACL/race conditions. Real share tests required.
- D24 mapped/UNC read support is implemented, but genuine SMB transport acceptance is still pending.
- Windows 10/11 manual UI, accessibility, OS DPI and portable executable acceptance are pending.
- MIT is approved for own code; third-party notices, FFmpeg external dependency checks, winget/update UX and distribution compliance remain outstanding.

## Historical open questions (preserved for traceability)

- Confirm product name, repository slug, trademark availability and final external branding.
- **Resolved direction:** MIT for application code; third-party notices and codec/license checks remain necessary.
- Confirm exact MVP support for external audio and any subtitle formats beyond SRT; test rather than promise broad compatibility.
- Specify behavior for multiple video streams, MKV attachments and chapters, forced/default subtitle flags, and metadata loss when changing containers.
- Determine codec-specific file extensions and bitstream-filter requirements for track extraction.
- Confirm final English UI wording and accessibility expectations.
- **Resolved direction:** standalone `onefile` `.exe` plus portable `onedir` ZIP without installer; external FFmpeg/ffprobe mandatory. Startup and winget guidance are planned.
- Define end-user positioning: general local tool versus library optimization specialist.
- Agree CI/CD versioning and tag/release policy.
- Re-estimate effort after PR-02 and PR-03.

These questions do not prevent initial scaffolding, but the relevant ones must be closed before the MVP is declared complete.

## PR-01 assumptions and contradictions - November 14, 2026

- The request approves Python 3.11+, the tooling stack and PyInstaller portable artifact targets; older proposed/deferred ADR wording is updated. CustomTkinter and the application license remain undecided.
- Initial package version is `0.1.0`; it identifies the scaffold and does not represent a published product. Exact `v<version>` tags are the future policy.
- The older architecture lists specialized modules, while PR-01 requests layers. Use four empty layer namespaces and add specialized modules only when their behavior is implemented. Alternative: a flat package of adapters; rejected because it obscures dependency direction.
- The reference project's floating Windows runners are not reused. Both selected Actions were independently checked for Node 24, release existence and major-version changes. See document 12 for sources.
- Exact development pins are a reproducible resolution baseline, not a hash lock. Cross-platform compatibility requires all CI matrix jobs. Dependabot proposals may require coordinated transitive pin updates.
- Stable Action tags are mutable. SHA pinning is a possible later hardening change; do not claim supply-chain immutability.
- The final application license and dependency notices remain release blockers. Do not invent a LICENSE or bundle FFmpeg/PyInstaller executables now.
- Release infrastructure means a tested version/tag validator plus documented future gates in PR-01. Alternative: runnable placeholder packaging workflow; rejected because executable-specific acceptance cannot yet be meaningful. No release workflow exists.
- Windows Server CI is not evidence of Windows 10/11 GUI compatibility. Native desktop and executable smoke checks remain deferred.

## PR-02 scope and limitations - November 14, 2026

- Owner approved D1-D3: public version 1 JSON, external configurable local-only
  ffprobe and mandatory real synthetic-media integration on both CI platforms.
- Source identity uses path/size/mtime before/after inspection. It is not a hash
  identity or a guarantee against concurrent replacement with unchanged metadata.
- File-only ffprobe protocols and input URL/UNC rejection block direct and nested
  network protocols. They are not an OS sandbox; local demuxer references can read
  local files, and mounted network storage/mapped drives may look like local files.
- Timeout kills/reaps the ffprobe process; trusted overrides that spawn other
  programs are not process-tree sandboxed. Future processing cancellation remains
  separate work. Decode CPU/memory limits require OS-level isolation if later needed.
- Captured output is bounded (8 MiB stdout, 64 KiB stderr); very large metadata is
  rejected with exit 6. Raw diagnostics are suppressed; nonzero exit 4 cannot always
  distinguish corrupt, unsupported or inaccessible media from ffprobe alone.
- Optional invalid scalar metadata becomes null; malformed structural collections
  fail. Empty stream arrays are accepted. Missing chapter arrays are empty.
- Language/title extraction uses exact lowercase ffprobe tag names while preserving
  every string tag verbatim. Unknown case variants remain available in tags.
- CI uses maintained apt/Chocolatey packages rather than pinned binary URLs. Tool
  versions can change; record observed versions and fail missing fixture capabilities.
- Existing architecture prose describes future operations, not PR-02 behavior.
  JSON contract v1 and the inspection implementation take precedence for inspection.
- GUI, licensing, packaging, output compatibility, subtitle import, extraction,
  remuxing and publication questions remain unresolved and outside this PR.

## PR-03 limitations and resolved policy choices

- D4-D8 are owner approved. This PR enables a narrow tested allowlist rather than
  all candidates. DTS, AC-3/E-AC-3, ASS/SSA, image subtitles, FFV1/PCM output and
  unknown combinations stay blocked; they need separate real cross-platform evidence.
- Text/plain null-codec attachments with filename/MIME metadata are the only
  enabled attachments. Other attachment types and all MP4 attachments are blocked.
- MP4 chapter copying remains blocked: it can introduce additional data streams
  and needs a separate expected-output policy. Primary chapter times/titles into
  MKV are tested. Other tags/secondary chapters require explicit loss acknowledgement.
- Real testing found Matroska may omit explicit und language tags; warn without
  silently normalizing requested intent. MP4 metadata semantics are uncertain.
  Stream/global tags outside the supported policy and nonzero other dispositions
  are disclosed losses. Exact metadata or chapter-ID round-tripping is not promised.
- Hosted FFmpeg 6.1.1 shifted chapter bounds by roughly 21 ms in the mixed H.264/AAC
  fixture. Chapter timing is explicitly uncertain and requires acknowledgement;
  the integration test checks a 50 ms fixture tolerance, not a general product
  duration-validation guarantee. FFmpeg 9/local builds did not show the same shift.
- More than one effective default per stream kind blocks. Alternative silent
  default selection was rejected. Missing flags stay absent in domain snapshots;
  command generation disables auto-default but muxers may emit zero-valued flags.
- Warning acknowledgement is bound to the exact immutable plan/diagnostic revision
  and submitted codes, not a persisted authorization. Caller-supplied inspection/external-validation provenance is trusted;
  the planner is not a sandbox for forged in-memory domain objects.
- Source/destination checks are read-only and subject to races, mounted-network
  limitations and noncryptographic size/mtime identities. Missing output parents
  are not created. Future execution must revalidate, stage, validate and publish;
  proposed direct output arguments do not implement that safety workflow.
- Compatibility tests establish tiny representative mux cases on observed builds,
  not every codec profile/player or runtime build. FFmpeg is external. No binary
  bundling, importing, GUI, execution, publication or release policy is changed.

## PR-04 safety assumptions and residual limits

- Staging is same-filesystem, owner-private and exclusive. Filesystem hard-link
  semantics are mandatory, with no unsafe fallback. Unix mode 0600/private Windows
  DACL remains on the final inode. No user output directories are auto-created.
- Trusted local destination namespaces exclude adversarial same-principal/admin
  reparse/inode replacement. Source reinspection and ownership checks detect
  ordinary changes but cannot eliminate all filesystem races or same-metadata
  encoded-content attacks. Final-name collisions are protected by the atomic link.
- Atomic visibility is not transactional crash durability: file data is fsynced,
  directory entries are not universally crash-committed. Network/FAT-like/mapped
  storage is not promised. Unsupported primitives fail rather than copy/rename.
- Windows job assignment has a brief launch interval; malicious overrides escaping
  before assignment and deliberate POSIX new-session children are not sandboxed.
  Ordinary descendants are terminated and quiescence checked. Unverified stop
  retains staging, closes our descriptor and reports cleanup incomplete.
- Timing bounds derive from source/output ticks and frame/packet metadata. Missing
  stream timing or coarse/variable frame clocks reduce guarantees explicitly.
  Metadata inspection does not prove every packet decodes or that indistinguishable
  same-codec streams have byte-identical content; selected tests compare packets.
- ExternalTrack records remain blocked by execution: full SRT importing is deferred.
  Internal approved subtitle conversion is allowed. No codec allowlist expansion,
  signing, bundling, GUI, extraction, cancellation UI or release change is implied.
- Failed cleanup after successful publication reports published=true with failed
  state; it never rolls back by deleting a valid final file. Recovery should inspect
  only the reported destination parent's .mediatrack-* artifacts privately and
  confirm no process writes before manual deletion. Never delete unknown contents.

## PR-05 bounded choices and residual risks

D14-D18 resolve SRT encoding/structure, initial extraction and backend cancellation/
progress within document 16. Older importer/extraction deferrals are historical.
Strict UTF-8/BOM avoids guessing encodings; unsupported legacy files need conversion
outside the product. Cue timing supports 0..999 hours, 8 MiB and 100,000 cues.
PR-05 initially enabled six exact source/codec/format combinations; PR-08 adds
Matroska MP3 extraction. AC-3, MKV video/AAC extraction and other profiles stay blocked. Positive equal full packet counts
provide elementary truncation evidence when timing is absent, not full decoding or
content identity. MP4 AAC edit-list priming/padding is not representable in ADTS.
PR-05 rejected mov_text empty/clear samples when packet counts changed; PR-08
replaces that subtitle-only assumption with independent text/timing cue evidence.
Trusted synchronous listeners must return promptly or they can delay cancellation/
timeout observation; the backend owns no unbounded event queue. GUI integration must
use bounded latest-value delivery. Source snapshot/noncryptographic identity, trusted
filesystem namespace, process containment gaps, private final permissions and lack
of power-loss durability remain unchanged. Release/license/desktop risks remain open.
No G3 acceptance is implied until independent review and owner acceptance.

## PR-06 desktop risks and choices

D19-D23 resolve the GUI toolkit/workflow/threading scope (ADRs 034-038). Initial
all-included intent avoids silent omissions but may require explicit correction
for incompatible streams/default conflicts. No recent-files/history is persisted.
CustomTkinter 6.0.0 and its pinned development dependencies install for CLI users
without initializing a display. Toolkit keyboard focus uses a small canvas adapter
that must be retested on upgrades. Screen-reader/UI Automation/high-contrast support
is limited; actual Windows 10/11 OS-DPI/manual acceptance remains open. Repeated local
Tk roots caused Tcl initialization errors, so native test scenarios run in isolated
processes. Local screen capture was unavailable; screenshots are not fabricated.
Hosted Server 2025 widget tests are not interactive consumer desktop certification.
Unverified termination/cleanup blocks further work and keeps recovery details visible;
the GUI provides no unsafe force-close/kill/delete shortcut. Existing filesystem,
process containment and source identity limits remain. PR-07 license/notices,
packaging, executable validation and owner release approval remain separate work.

## D24 Windows read-only network source limits

ADR-039 supersedes the former UNC input rejection for trusted Windows media/SRT.
Canonical snapshots/reinspection/revisions remain; source input and local-only
output policies are separate. Native Windows remote/unknown volume rejection also
covers mapped destinations retaining drive letters. SMB access depends on session/
permissions/connectivity; OS filesystem I/O can outwait subprocess limits and metadata
may be cached/coarse. Canonical path/size/mtime is not a transaction/content hash.
Aliases not canonicalized by Windows are not universally deduplicated. File-only
FFmpeg protocols do not sandbox Windows filesystem providers. Genuine SMB evidence
is unavailable in this environment (no mapping; enumeration unavailable); offline
simulation and actual local tests must not be presented as proof of remote access.
The explicit real-share utility/manual procedure is in document 17. Network output
requires a separate capability/safety decision. No credentials or shares are created.

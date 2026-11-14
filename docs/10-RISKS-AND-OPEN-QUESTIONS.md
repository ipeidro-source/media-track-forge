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

## Open questions

- Confirm product name, repository slug, trademark availability and final external branding.
- Choose and record the final license for application code; assess FFmpeg redistributions, third-party notices and codec considerations.
- Confirm exact MVP support for external audio and any subtitle formats beyond SRT; test rather than promise broad compatibility.
- Specify behavior for multiple video streams, MKV attachments and chapters, forced/default subtitle flags, and metadata loss when changing containers.
- Determine codec-specific file extensions and bitstream-filter requirements for track extraction.
- Confirm final English UI wording and accessibility expectations.
- Decide portable ZIP versus installer; whether FFmpeg remains an external dependency.
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

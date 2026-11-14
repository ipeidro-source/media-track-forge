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

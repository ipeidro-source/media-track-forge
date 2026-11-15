# 00 — Current Project Status

Snapshot: November 15, 2026. PR-07 documentation is merged at `e3ee5af391`.
PR-01 through PR-06 provide the implementation baseline; their historical
[five-job CI](https://github.com/ipeidro-source/media-track-forge/actions/runs/43630367616)
does not validate PR-08. No GitHub Release has been published.

PR-08 backend work is in progress on a topic branch: subtitle validation diagnostics,
compatible metadata preservation with plan v2, tested compatibility candidates and
failed replacement recovery. UI refinements remain gated on Commit 1 hosted CI.
See [owner audit findings](18-UX-VALIDATION.md), ADRs 041–043 and contracts 14–16.
No exact owner MKV fix, genuine SMB verification or consumer Windows acceptance is claimed.

## Status terminology

**Approved** = owner decision; **Implemented** = merged code; **Automated verified** = relevant passing tests; **Owner accepted** = explicit human acceptance; **Released** = authorized public artifact. These are distinct statuses.

| Scope | Implemented evidence | Pending |
| --- | --- | --- |
| Inspection, planning, stream editing and safe remux | PR-01–PR-04 merged | End-user acceptance |
| External SRT, extraction, cancellation and progress | PR-05 merged | End-user acceptance |
| Windows CustomTkinter GUI | [PR-06](https://github.com/ipeidro-source/media-track-forge/pull/6) merged | UX-01–UX-10 and real Windows 10/11 manual verification |
| Trusted mapped/UNC file **input** | D24/ADR-039 implemented in PR-06 | Real SMB share testing (simulation is not transport evidence) |
| UNC/mapped **output** | **Not implemented; deliberately blocked** | New approved design and safe real-SMB verification |

PR-06 reported 299 unit, 66 real-media integration and 8 native Tk scenarios. Hosted Windows Server 2025 testing is not consumer Windows 10/11 certification.

## Approved delivery directions, not yet implemented

- MIT for application-owned source. Dependency redistribution notices still require review.
- FFmpeg/ffprobe are mandatory external dependencies. Future startup availability/version/capability verification; winget `Gyan.FFmpeg` installation guidance, optional nonblocking update notices; no forced/silent installation.
- Two portable PyInstaller artifacts: **single-file `onefile` `.exe`** and **versioned `onedir` ZIP**, no installer initially. Defer packaging until UX maturity, verify Windows 10/11, third-party notices and checksums before any Release.
- Owner-approved output writing to trusted SMB/UNC/mapped destinations, **not currently supported**. A separate ADR must determine private staging, independent validation, exclusive no-overwrite publication, disconnection/recovery and durability guarantees.
- Selective transcoding, GPU and batch automation remain later phases, without implementation authorization.

## Near-term sequence

Documentation PR → owner review → interactive [UX-01–UX-10](18-UX-VALIDATION.md) → approved GUI refinement specification/PR → independently gated safe NAS output design and implementation → portable Windows packaging → G4/G5 owner acceptance and separately authorized Release. Actual PR numbers are assigned by GitHub, not reserved by a roadmap.

## Source-of-truth map

Vision: [01](01-VISION-AND-SCOPE.md); roadmap/gates: [02](02-ROADMAP.md); requirements: [03](03-MVP-REQUIREMENTS.md); architecture/model/decisions: [04](04-ARCHITECTURE.md), [05](05-DOMAIN-MODEL.md), [06](06-ARCHITECTURE-DECISIONS.md); tests: [07](07-QUALITY-AND-TESTING.md); next work: [08](08-CODEX-IMPLEMENTATION-PLAN.md); risks: [10](10-RISKS-AND-OPEN-QUESTIONS.md); public contracts: [13](13-INSPECTION-CONTRACT.md)–[16](16-EXTERNAL-TRACKS-EXTRACTION-AND-CANCELLATION.md); GUI: [17](17-WINDOWS-DESKTOP-UI.md); UX evidence: [18](18-UX-VALIDATION.md). Historical PR notes remain traceability, not a live current-state statement.

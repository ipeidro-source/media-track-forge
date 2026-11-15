# 18 — Interactive UX Validation

**State:** the owner performed an interactive Windows usability audit of the PR-06
GUI, supplied as the PR-08 implementation request. Findings below are owner-reported;
they do not establish complete UX-01–UX-10 acceptance or exact source-file diagnosis.

| ID | Scenario | State |
| --- | --- | --- |
| UX-01 | First impression and discoverability | Acceptance pending |
| UX-02 | MKV inspection and track information | Acceptance pending |
| UX-03 | Audio track inclusion and removal | Acceptance pending |
| UX-04 | Language, metadata and track order | Acceptance pending |
| UX-05 | External SRT integration | Acceptance pending |
| UX-06 | AVI → MKV stream copy | Original scenario unverified |
| UX-07 | Exact stream extraction | Acceptance pending |
| UX-08 | Error handling and recovery | Acceptance pending |
| UX-09 | Progress and safe cancellation | Acceptance pending |
| UX-10 | Navigation, resizing and ergonomics | Acceptance pending |

**Procedure:** owner attempts each task while ChatGPT records prerequisites/media sample, intended action, observed steps, expectation vs result, exact error where available, reproducibility, suggestions and acceptance criteria. Findings: P0 safety/data-loss or blocked critical workflow, P1 major confusion/failure, P2 moderate friction, P3 polish. Reassess severity after triage.

| Finding | Scenario | Reproduction/expected/actual | Severity | Proposal | Status |
| --- | --- | --- | --- | --- | --- |
| Extraction A | UX-07 | MP4 mov_text, Spanish original index 3 → local SRT: OUTPUT_VALIDATION_FAILED / EXTRACTION_INVALID, unpublished, cleanup complete | P1 | Independent cue validation and specific diagnostics | Synthetic gap reproduction; owner file unverified |
| Extraction B | UX-07/08 | UNC MKV with HEVC/E-AC-3/SubRip, original index 5 → local SRT: same generic error twice | P1 | Diagnose independently of A | Owner confirms corrected extraction at cc592045; separate SMB fault/recovery acceptance pending |
| Replacement | UX-08 | Failed replacement inspection clears valid editing session | P1 | Inspect before replacing session | Implemented on PR-08 branch; regression tests |
| Metadata | UX-04 | Unchanged compatible tags discarded under conservative policy | P1 | Explicit preservation and validation, versioned contract | ADR-042 proposed |
| Navigation/editing | UX-01–05/10 | Oversized initial workspace, confusing metadata keep/set and extraction button, raw technical review, duplicated import feedback | P2 | Approved U1–U7/U10 refinement | Implemented on PR-08 branch; native regressions |
| Destination | UX-08 | Native overwrite prompt conflicts with no-overwrite backend | P2 | Early inline validation and new-name suggestion | Implemented on PR-08 branch; collision/dialog tests |
| Progress | UX-09 | Stale/duplicated results, terminal indeterminate label, raw seconds, animation and cancel reflow | P2 | Stable phase/progress/terminal presentation | Implemented on PR-08 branch; repeat-run/cancellation tests |
| Cancellation | UX-09 | Owner reports successful cancellation during the audit | — | Preserve safe termination and cleanup behavior | Owner observation; full scenario acceptance not asserted |

The scenario table records formal acceptance separately: the supplied audit does
not provide individually completed acceptance records. Automated PR-08 regressions
do not turn these findings into owner acceptance. In particular UX-06
is the original **AVI → MKV stream-copy** scenario, not the subtitle extraction
investigations; no UX-06 pass is claimed. Keep exact owner-file rechecks separate
from local synthetic regressions and real SMB transport verification.

**D24 verification:** real synthetic media and SRT on mapped and UNC trusted SMB shares, identity, account/session, read-only inputs, local-only output, failures and disconnections. Simulated CI coverage does not prove SMB operation.

**Owner MKV retest:** original trusted UNC MKV, HEVC/E-AC-3/SubRip, original index 5
to a new local SRT at PR-08 head `59408c0`: `OUTPUT_VALIDATION_FAILED`,
`EXTRACTION_PACKET_SCAN`, `EXTRACTION_INVALID`, unpublished, cleanup complete.
This is a reproducible owner observation, not simulated evidence. The old combined
scan code does not identify source versus staged output or classify the probe failure.
Read-only diagnosis and the focused diagnostic correction are specified in contract 16;
the original generic code alone could not identify a cause.

**Owner read-only diagnosis:** source packet count, index 5, `TIMEOUT`, limit 30.0
seconds, elapsed 30.078 seconds, 1,660,724,038 bytes, UNC spelling. This confirms
the reproduced source probe deadline failure before output counting. It does not
establish a network transport fault or successful extraction after correction.
The follow-up separates scan/metadata limits while retaining validation and cancellation;
at that checkpoint original-file retesting remained pending. The subsequent owner
success below resolves extraction; complete SMB transport/failure acceptance remains pending.

PR-08 GUI refinement is owner-authorized from these findings; backend reinspection, revision-bound acknowledgements, separate confirmation, staging, validation, no overwrite and cancellation must remain intact. Network **output** requires separate safety architecture and real SMB tests.

## Owner backend acceptance at cc592045 and final wizard approval

The owner reports these real Windows results (supplied with the final redesign request):

- Original trusted UNC MKV, original subtitle index 5 → new local SRT completed;
  1,006 source/output packets and subtitle cues validated, published, cleanup complete.
- MKV → MKV retained visible track structure; title/default/forced metadata edits worked.
- MP4 VP9/Opus/AAC/mov_text → MKV retained all five tracks and converted subtitles
  to SubRip. MKV MP3 extraction succeeded.
- Failed replacement retained the previous editing session.

These are owner manual observations, not simulated fixtures or new agent media tests.
They resolve the original reported extraction blocker after the separate packet-scan
budget correction. The preceding read-only 120-second measurement counted 1,006 packets
in 109.797 seconds; the earlier 30-second scan timed out at 30.078 seconds. They do not
certify arbitrary SMB dialect, faults, permissions, disconnection recovery or remote outputs.
Formal original AVI UX-06 and complete Windows usability acceptance remain distinct.

The owner now approves the final five-step wizard, large stable startup size,
UX-F37 searchable languages, UX-F38 one inspection-failure modal, automatic Review,
one explicit final warning/execution decision preserving internal authorization,
and safe Start over/Close. This supersedes the earlier compact tab proposal.
Implementation on the PR-08 review branch and automated evidence do not establish
owner acceptance of the new wizard. Recheck all five steps, keyboard, real OS-DPI,
small-screen ergonomics, warning visibility, exact extraction selection, imported
metadata, failed replacement, cancellation, reset and unsafe-cleanup recovery.

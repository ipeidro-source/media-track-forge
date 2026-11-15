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
| Extraction B | UX-07/08 | UNC MKV with HEVC/E-AC-3/SubRip, original index 5 → local SRT: same generic error twice | P1 | Diagnose independently of A | Local synthetic MKV passes; exact cause unresolved |
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

PR-08 GUI refinement is owner-authorized from these findings; backend reinspection, revision-bound acknowledgements, separate confirmation, staging, validation, no overwrite and cancellation must remain intact. Network **output** requires separate safety architecture and real SMB tests.

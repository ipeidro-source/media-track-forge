# 18 — Interactive UX Validation

**State:** ten owner-approved scenarios; no human sessions run yet. Test the merged PR-06 GUI. Gather evidence one scenario at a time and do not fabricate results.

| ID | Scenario | State |
| --- | --- | --- |
| UX-01 | First impression and discoverability | Not run |
| UX-02 | MKV inspection and track information | Not run |
| UX-03 | Audio track inclusion and removal | Not run |
| UX-04 | Language, metadata and track order | Not run |
| UX-05 | External SRT integration | Not run |
| UX-06 | AVI → MKV stream copy | Not run |
| UX-07 | Exact stream extraction | Not run |
| UX-08 | Error handling and recovery | Not run |
| UX-09 | Progress and safe cancellation | Not run |
| UX-10 | Navigation, resizing and ergonomics | Not run |

**Procedure:** owner attempts each task while ChatGPT records prerequisites/media sample, intended action, observed steps, expectation vs result, exact error where available, reproducibility, suggestions and acceptance criteria. Findings: P0 safety/data-loss or blocked critical workflow, P1 major confusion/failure, P2 moderate friction, P3 polish. Reassess severity after triage.

| Finding | Scenario | Reproduction/expected/actual | Severity | Proposal | Status |
| --- | --- | --- | --- | --- | --- |
| — | — | Not tested | — | — | Pending |

**D24 verification:** real synthetic media and SRT on mapped and UNC trusted SMB shares, identity, account/session, read-only inputs, local-only output, failures and disconnections. Simulated CI coverage does not prove SMB operation.

GUI refinement is separately authorized after UX evidence; backend reinspection, revision-bound acknowledgements, separate confirmation, staging, validation, no overwrite and cancellation must remain intact. Network **output** requires separate safety architecture and real SMB tests.

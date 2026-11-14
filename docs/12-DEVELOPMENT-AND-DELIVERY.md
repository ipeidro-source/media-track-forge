# Development and delivery foundation

## Implemented in PR-01

An installable Python 3.11+ package, four layer boundaries, offline unit tests,
Ruff, mypy, YAML validation, actionlint, Dependabot and CI. The application only
printed help or `--version` only at PR-01. PR-01 is merged; PR-02 adds inspection
as described below. No GUI, PyInstaller executable, portable package, tags or
Releases are implemented by either PR.

## Local setup

Use native Windows PowerShell and a supported x64 Python installation:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
python -m mediatrack_forge --version
mediatrack-forge --help
```

On Linux use `python3.12 -m venv .venv` and `source .venv/bin/activate`.
There are no Python production dependencies. PR-02 inspection requires external
ffprobe; real integration tests also require FFmpeg. Neither binary is bundled.
The dependency file pins direct and transitive development dependencies. Build
backend pins also appear in `pyproject.toml`; update them together. Pins select
versions, not identical platform wheels or cryptographically locked downloads.
Python patch versions follow setup-python's supported distributions; the CI
matrix verifies Windows 3.11/3.12/3.13 and Linux 3.12 compatibility.

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest tests/unit
python -m pytest tests/integration -m integration -v -s
python scripts/check_yaml.py
actionlint -color
python -m build --no-isolation
```

Install [actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12)
from the official release and verify its published SHA-256 checksum. CI downloads
the Linux x64 archive and checks the recorded hash before execution. This is a
standalone Go binary, with no JavaScript Action runtime. Review its version and
hash manually with workflow changes; Dependabot cannot update this shell URL.

Unit tests use the installed package, including invocation outside the checkout,
and require no media tools. Integration tests use pytest temporary directories
and subsecond locally generated synthetic media; missing tools/fixture encoders
fail rather than skip. With both tools installed, `python -m pytest` runs both.

## External media tools and PR-02 inspection

Install FFmpeg/ffprobe through a trusted distribution. CI uses the verified
[Chocolatey ffmpeg package](https://community.chocolatey.org/packages/ffmpeg)
on Windows (when not already available) and Ubuntu's
[ffmpeg package](https://packages.ubuntu.com/noble/ffmpeg) via apt on Linux:

```powershell
choco install ffmpeg --yes --no-progress
ffmpeg -version
ffprobe -version
mediatrack-forge inspect "C:\Media\example.mkv" --timeout-seconds 30
```

On Ubuntu: `sudo apt-get update` then
`sudo apt-get install --yes --no-install-recommends ffmpeg`.
Existing local installations need not be replaced. CI requires both executables
and prints their versions. These package names/sources were verified, but binary
versions are not pinned; observed hosted versions belong in each PR's evidence.
The local PR-02 baseline used FFmpeg/ffprobe N-127043-g5a54fcf75e-20260930.
Unit tests never need these binaries. Product inspection never invokes FFmpeg;
it is only a test fixture generator. See [schema v1](13-INSPECTION-CONTRACT.md)
for command options, fields, errors and limitations.

## Architecture and versioning

`domain` holds frozen inspection entities; `application` orchestrates inspection
through its `MediaProbe` Protocol; `infrastructure` implements external ffprobe
execution/normalization; `ui` holds CLI and JSON presentation. PR-03 adds the
declarative planning API; media execution, validation and publication remain unimplemented. The CLI does
not import a GUI. The four boundaries and zero Python runtime dependencies remain
unchanged from PR-01.

`mediatrack_forge.__version__` is the single literal version source. Setuptools
derives distribution metadata from it; the CLI and future release validator read
the same value. Initial scaffold version is `0.1.0`, without creating a release.
Use three numeric components and exact `v<version>` release tags. Test equality
against installed metadata. License metadata is intentionally absent while
ADR-008 remains pending; this does not grant a license or authorize distribution.

## CI policy and verified dependencies

Verification date: **November 14, 2026**. CI runs on PRs targeting `main`, pushes
to `main`, and manual dispatch. All four test jobs run lint, format, strict types,
unit tests, YAML validation and source/wheel builds; a separate job runs actionlint.
PR-02 adds mandatory real media integration steps in both Python 3.12 test jobs.
Only the 3.11/3.13 jobs intentionally omit those steps; their unit suite still runs.
Integration fixtures validate required encoders before creation and never skip.
Errors fail their jobs; there is no continue-on-error. Pip caches are keyed using
the dependency file and project configuration. Token access is `contents: read`,
checkout credentials are not persisted, and newer runs cancel duplicate runs.

Stable branch protection candidates (configure after observing successful CI):

- `Test (windows-2025, Python 3.11)`
- `Test (windows-2025, Python 3.12)`
- `Test (windows-2025, Python 3.13)`
- `Test (ubuntu-24.04, Python 3.12)`
- `Workflow validation`

| Action | Selected stable tag | Runtime evidence | Upgrade review |
| --- | --- | --- | --- |
| actions/checkout | v7.0.1 | [action.yml: node24](https://github.com/actions/checkout/blob/v7.0.1/action.yml) | [v7.0.0](https://github.com/actions/checkout/releases/tag/v7.0.0) migrates to ESM and blocks unsafe fork checkout in trusted events; [v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) fixes input handling. This workflow uses ordinary pull_request. |
| actions/setup-python | v7.1.0 | [action.yml: node24](https://github.com/actions/setup-python/blob/v7.1.0/action.yml) | [v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0) migrates to ESM and removes pip-install input; [v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0) adds optional mirror support. Neither removed inputs nor custom mirrors are used. |

These are the only Actions used. Their release records exist and are stable.
Installing Node with setup-node cannot change another Action's internal runtime.
Never accept Node 16/20 Actions or suppress runtime warnings. GitHub-hosted
runners supply the Node 24-capable runner; actual matrix execution must confirm
runtime compatibility before readiness is claimed.

The official [available runner image table](https://github.com/actions/runner-images/blob/main/README.md)
lists `ubuntu-24.04` and `windows-2025` as available, without deprecation markings,
on the verification date. Both are explicitly selected. OS labels still receive
security/toolchain updates and are not immutable VM snapshots. Windows Server
2025 CI does not establish Windows 10/11 desktop GUI compatibility.

Use exact stable Action tags, updated by weekly Dependabot PRs. Tags are readable
but mutable; immutable SHA pinning remains an optional hardening improvement.
Dependabot monitors GitHub Actions and pip manifests weekly; it never bypasses
review or CI. Check transitive pin consistency with `pip check` and all matrix
jobs after updates. Do not enable automatic merging as part of this foundation.
Review runners quarterly and before release, including official retirement
announcements and dependency support; migrate only by reviewed PR.

Before marking any implementation PR ready, inspect actual job results and full
logs, including setup and post-job steps. Search for Node deprecation, unsupported
Actions, runner migration/retirement warnings, dependency conflicts, and skipped
mandatory jobs. Fix avoidable warnings and rerun affected checks. Static validation
alone cannot establish warning-free execution. Record run URLs and actual evidence
in the PR; disclose unavailable logs or blocked execution.

## Release foundation and deferred gates

The YouTube Smart Downloader [CI](https://github.com/ipeidro-source/youtube-smart-downloader/blob/main/.github/workflows/ci.yml)
and [release workflow](https://github.com/ipeidro-source/youtube-smart-downloader/blob/main/.github/workflows/release.yml)
were reviewed. Reused patterns: Python matrix, pip caching, explicit permissions,
timeouts, reusable validation stages in the future release design, version/tag
matching and ancestry gates. Its floating Windows label and mature application
build steps are unsuitable for this scaffold. No media dependencies or release
publication Actions are copied.

Operational today: `python scripts/check_release.py v0.1.0` verifies exact equality
with the canonical application version and rejects mismatches with nonzero status.
It neither checks Git ancestry nor authorizes a release. **No release workflow
is enabled**, so a merge or a tag cannot publish a Release through this repository's
workflows. Source/wheel builds in CI are installation checks, not published assets.

Future owner-authorized release implementation must satisfy these gates in order:

1. Fetch full history/tags, validate `v<version>`, then require
   `git merge-base --is-ancestor HEAD origin/main` against a freshly fetched main.
2. Run the complete mandatory CI suite for that exact commit.
3. On `windows-2025` with a pinned build Python, install a separately locked,
   reviewed PyInstaller toolchain and build `MediaTrackForge.exe`. Validate embedded
   product/file version metadata against the canonical version.
4. Smoke-test startup and error handling meaningfully once application behavior
   exists. Do not pass a placeholder executable off as a product build.
5. Resolve the application license, inventory bundled components, and include the
   approved license and third-party notices. PyInstaller's bootloader exception,
   Python and bundled dependency notices require review. FFmpeg stays external;
   any future bundling requires a separate licensing assessment.
6. Build `MediaTrackForge-<version>-Windows-x64.zip` with the executable and notices;
   calculate SHA-256 for the final EXE and ZIP in `SHA256SUMS.txt`.
7. Validate the final downloaded artifacts, checksum coverage and archive contents,
   then publish only through an explicit owner-approved release event, with write
   permissions restricted to the publish job. Never publish on a normal main push.

All executable, PyInstaller, metadata, ancestry automation, startup, packaging,
checksum and publication steps above are **deferred and untested** in PR-01.
No code signing is authorized. Reproducible dependency selection is established;
bit-identical Windows executables are not promised and need a later investigation.

## PR-03 validation and current delivery scope

Planning requires no new dependencies, executable discovery or product process.
The existing test commands apply unchanged. `python -m pytest tests/unit` includes
all offline planning cases; `python -m pytest tests/integration -m integration -v -s`
also validates the conservative compatibility matrix using temporary test outputs.
The test-only encoders libx264/libx265/libmp3lame/mov_text must be available on both
required CI builds. Missing capabilities fail instead of hiding unsupported entries.
Exact tested builds and observed results belong in the PR evidence. No workflow,
Action version, runner, dependency or release changes are required by PR-03.
Product media execution and portable packaging remain deferred. See the
[plan contract](14-OPERATION-PLAN-CONTRACT.md) before consuming proposed arguments.

## PR-04 local and hosted validation

The existing commands and external tool setup remain valid. All offline execution,
filesystem, validator and Python process-tree tests run in `python -m pytest tests/unit`.
`python -m pytest tests/integration -m integration -v -s` now includes real product
execution E2E and prints filesystem evidence. Windows tests use native security/job
APIs; Linux strict typing can also be checked locally with `python -m mypy --platform linux`.
No dependencies, Actions, runner labels or release workflows change in PR-04.
Exact final counts, observed Windows/Ubuntu builds/filesystems and full log review
belong in the PR. No user-facing remux CLI, GUI or portable Release is introduced.

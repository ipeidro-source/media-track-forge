# 09 — GitHub Repository and Development Environment

## Established repository (historical initial proposal below)

- Product name: **MediaTrack Forge**
- Repository slug: `media-track-forge`
- Python package: `mediatrack_forge`
- Proposed description: `Windows media track manager for inspecting, remuxing, extracting and cleaning video, audio and subtitle streams with FFmpeg.`
- Suggested GitHub topics (once accurate): `ffmpeg`, `ffprobe`, `python`, `windows`, `mkv`, `mp4`, `subtitle-tools`, `media-tools`, `remux`, `customtkinter`.

## Historical repository initialization (do not repeat on existing clone)

1. Open GitHub → **New repository**, under the intended account.
2. Use the name and description above. Make it **Public** if the intent is open source immediately, or **Private** if licensing/publication is undecided.
3. If uploading this existing documentation kit from Windows, create an **empty** repository: do not ask GitHub to generate a README, `.gitignore` or license. This avoids unrelated initial histories.
4. Use `main` as the default branch, enable Issues, and consider automatic head-branch deletion after PR merges.
5. Configure branch protection/rulesets and required checks after CI exists, without locking out the owner. Enable Dependabot and security scanning where supported.
6. Add topics when the repository is populated. Commit an appropriate LICENSE after ADR-008 is approved.

## Development environment

**Recommended:** native Windows + PowerShell + VS Code + Python 3.11+ x64 + Git + the Codex extension. Python/Pylance recommended; GitLens optional.

WSL is not necessary for the MVP because native Windows better reflects the target GUI, path semantics and packaging. Linux CI can independently exercise the headless core.

If starting from an empty repository:

```powershell
mkdir C:\Users\nacho\code\media-track-forge
cd C:\Users\nacho\code\media-track-forge
# Copy the extracted documentation kit into this folder.
git init -b main
git remote add origin https://github.com/ipeidro-source/media-track-forge.git
git add .
git commit -m "docs: initialize MediaTrack Forge project"
git push -u origin main
code .
```

**Do not run `git init` inside an existing clone.** If you have already cloned a non-empty repository, copy the kit into that clone and use normal `git add`, `git commit`, and `git push`.

## Dependencies and media fixtures

For PR-01, create a project-local `.venv` using the setup below. FFmpeg and ffprobe are not required yet. Starting with PR-02, install or configure the external tools and check:

```powershell
ffmpeg -version
ffprobe -version
```

Use synthetic files (typically under 10 seconds) for automated tests. Do not commit private videos, secrets, downloaded personal content, or very large binaries.

## Git workflow

Use `feat/...`, `fix/...`, and `docs/...` branches; submit PRs to `main`; require green CI before merging. Never force-push `main`.

When working in parallel with Codex, fetch remote changes before editing or rebasing, and use separate worktrees for separate agent sessions.

## PR-01 implemented foundation

See [development and delivery](12-DEVELOPMENT-AND-DELIVERY.md) for exact setup and check commands, the Windows 3.11/3.12/3.13 and Linux 3.12 matrix, verified Node 24 Actions, explicit runner images, weekly dependency reviews, actionlint and CI log requirements. Media, GUI and executable validation described above remains future work. No release workflow is enabled.

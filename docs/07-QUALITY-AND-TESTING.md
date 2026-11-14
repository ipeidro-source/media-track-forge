# 07 — Quality and Test Strategy

## Test pyramid

1. **Unit tests:** ffprobe parsing, languages, stream mapping, compatibility policy, destination collisions, and job state transitions.
2. **Local integration:** create tiny synthetic fixtures with FFmpeg (`lavfi` test sources, tones, sample SRT files) and verify them with ffprobe; no network calls.
3. **Windows E2E:** real FFmpeg/ffprobe, subprocess cancellation, Unicode and spaced paths, temporary-output safety.
4. **GUI smoke:** create a window, inspect sample media, display tracks, preview a plan and execute a short sample case.

## Minimum coverage matrix

- H.264/AAC MP4 with one and multiple streams; video-only MP4.
- MKV with multiple audio/subtitle streams and supported SRT; optional ASS only if explicitly supported.
- Synthetic AVI with a stream-copy compatible path to MKV.
- Unknown/data/attachment streams, chapters, missing language metadata, malformed subtitles.
- Incompatible codec/container, truncated input, missing FFmpeg, unwritable destination, low disk space, and permission errors.
- Cancellation, process failure, retry, occupied output filename, Unicode paths.

## Result validation

Compare expected/observed stream types, number, codec identifiers, language tags, default/disposition data, ordering, duration within documented tolerances, and ffprobe readability. Add partial decoding tests where critical. Changing containers does not imply byte-identical container files.

## CI and releases

Use Windows CI for tests, lint, typing and media integration cases. A secondary Ubuntu job may test cross-platform non-GUI logic. Explicitly declare supported Python versions.

Do not publish a Release on every merge. A manual version tag triggers a validated release workflow only after the owner explicitly authorizes release. Review dependency versions, notices, license obligations, Dependabot, and security tooling as appropriate.

## PR quality checklist

- Summarize the problem and linked requirements.
- Include/update tests and documentation for affected behaviors.
- Report exact checks performed and observed results.
- Do not commit personal media, real copyrighted test content, secrets, or large binaries.
- Keep public API and JSON contracts documented when they change.

## Definition of done for MVP

All AC-01 through AC-12 pass with evidence; the original files are verified unchanged on failure/cancel; GUI and Windows packaging are smoke-tested; the user approves publishing a release.

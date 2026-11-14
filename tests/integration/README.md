# Local media integration tests

Run `python -m pytest tests/integration -m integration -v -s` with external FFmpeg
and ffprobe on PATH. Missing tools or required fixture encoders fail the suite;
there are no silent skips. Tests generate subsecond media in pytest `tmp_path`.
MP4 (with and without audio), AVI, MOV and multi-track MKV inspection is covered,
including Unicode paths, metadata, chapters and an attachment. Source identities
and contents are checked. A local playlist verifies blocked HTTP access without
making a network request. Unit tests require neither executable.

Never download test media or require personal files, credentials, or network
access. Keep generated fixtures out of version control. FFmpeg is only a fixture
generator; the product runs ffprobe only and never writes media.

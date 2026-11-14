# Future media integration tests

PR-01 contains no media integration implementation. PR-02 will introduce tests
marked `integration`, generating tiny synthetic media in pytest `tmp_path` using
external FFmpeg and ffprobe. Never download test media or require personal files,
credentials, or network access. Keep generated fixtures out of version control.

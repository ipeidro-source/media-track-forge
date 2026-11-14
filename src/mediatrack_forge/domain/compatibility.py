"""Conservative allowlist exercised by mandatory real-mux integration tests."""

from mediatrack_forge.domain.media import Stream

# Each enabled entry has a real copy/conversion case in test_planning_mux.py.
COPY_CODECS: dict[str, dict[str, frozenset[str]]] = {
    "mkv": {
        "video": frozenset({"h264", "hevc", "mpeg4"}),
        "audio": frozenset({"aac", "mp3"}),
        "subtitle": frozenset({"subrip"}),
    },
    "mp4": {
        "video": frozenset({"h264", "hevc"}),
        "audio": frozenset({"aac", "mp3"}),
        "subtitle": frozenset({"mov_text"}),
    },
}


def codec_action(stream: Stream, container: str) -> tuple[str, str | None] | None:
    """Return an allowed action/target codec, never an audio/video encoder."""
    if stream.codec in COPY_CODECS.get(container, {}).get(stream.kind, frozenset()):
        return "copy", stream.codec
    if container == "mp4" and stream.kind == "subtitle" and stream.codec == "subrip":
        return "convert_subtitle", "mov_text"
    if stream.kind == "attachment" and container == "mkv":
        tags = dict(stream.tags)
        if stream.codec is None and tags.get("mimetype") == "text/plain" and tags.get("filename"):
            return "copy", None
    return None

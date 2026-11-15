"""Tested, explicit metadata policy; unknown tag names retain their source spelling."""

from mediatrack_forge.domain.media import Tags

FORMAT_TAGS = frozenset(
    {"title", "artist", "album", "comment", "genre", "date", "copyright", "description"}
)
STREAM_TAGS = {
    "mkv": frozenset({"language", "title", "comment", "description", "filename", "mimetype"}),
    "mp4": frozenset({"language", "title", "handler_name"}),
}


def compatible_tags(tags: Tags, allowed: frozenset[str]) -> Tags:
    # Only known names are case-insensitive; unknown keys are never normalized/copied.
    return tuple((key, value) for key, value in tags if key.lower() in allowed)


def metadata_value(tags: Tags, key: str) -> str | None:
    return next((value for name, value in tags if name.lower() == key.lower()), None)

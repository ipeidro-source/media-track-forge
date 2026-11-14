"""Explicit version 1 presentation contract; never expose raw ffprobe dictionaries."""

import json
from dataclasses import asdict

from mediatrack_forge.domain.media import MediaAsset


def inspection_document(asset: MediaAsset) -> dict[str, object]:
    """Build the documented contract with null scalars and ordered collections."""
    return {
        "schema_version": 1,
        "source": {
            "path": str(asset.source.path),
            "size_bytes": asset.source.size_bytes,
            "modified_time_ns": asset.source.modified_time_ns,
        },
        "format": {
            "name": asset.format.name,
            "long_name": asset.format.long_name,
            "duration_seconds": asset.format.duration_seconds,
            "bit_rate_bps": asset.format.bit_rate_bps,
            "tags": dict(asset.format.tags),
        },
        "streams": [
            {
                "index": stream.index,
                "kind": stream.kind,
                "codec": stream.codec,
                "language": stream.language,
                "title": stream.title,
                "disposition": dict(stream.disposition),
                "duration_seconds": stream.duration_seconds,
                "properties": asdict(stream.properties),
                "tags": dict(stream.tags),
            }
            for stream in asset.streams
        ],
        "chapters": [
            {
                "id": chapter.id,
                "start_seconds": chapter.start_seconds,
                "end_seconds": chapter.end_seconds,
                "title": chapter.title,
                "tags": dict(chapter.tags),
            }
            for chapter in asset.chapters
        ],
    }


def serialize_inspection(asset: MediaAsset) -> str:
    """Use ASCII escapes so Unicode metadata is safe on Windows legacy consoles."""
    return json.dumps(
        inspection_document(asset), ensure_ascii=True, allow_nan=False, sort_keys=True
    )

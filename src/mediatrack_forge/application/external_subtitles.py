"""Validate local SRT structure and independently inspect its actual stream identity."""

from pathlib import Path

from mediatrack_forge.application.execution_ports import Inspector
from mediatrack_forge.application.inspection import snapshot_source
from mediatrack_forge.domain.execution import ExecutionFailure
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import ExternalTrack, MetadataIntent
from mediatrack_forge.infrastructure.srt import validate_srt


class ExternalSubtitleService:
    def __init__(self, inspector: Inspector) -> None:
        self._inspector = inspector

    def import_srt(
        self,
        path: str | Path,
        metadata: MetadataIntent | None = None,
        *,
        timeout_seconds: float = 30.0,
    ) -> tuple[MediaAsset, ExternalTrack]:
        path = Path(path)
        metadata = metadata if metadata is not None else MetadataIntent()
        validate_srt(path)
        asset = self._inspector.inspect(path, timeout_seconds=timeout_seconds)
        validate_srt(path)
        if snapshot_source(path) != asset.source:
            raise ExecutionFailure("INVALID_EXTERNAL_SRT")
        if (
            len(asset.streams) != 1
            or asset.streams[0].kind != "subtitle"
            or asset.streams[0].codec != "subrip"
            or asset.format.name != "srt"
        ):
            raise ExecutionFailure("INVALID_EXTERNAL_SRT")
        stream = asset.streams[0]
        return asset, ExternalTrack(
            asset.source, "subtitle", stream.index, stream.codec, asset.format.name, metadata, True
        )

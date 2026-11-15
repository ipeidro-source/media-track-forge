"""Real independently validated compatibility and metadata round trips."""

from pathlib import Path

import pytest

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import ExecutionRequest, ProcessConfiguration
from mediatrack_forge.domain.metadata import metadata_value
from mediatrack_forge.domain.planning import (
    MetadataIntent,
    OutputProfile,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter

from .conftest import AUDIO, VIDEO, generate
from .test_planning_mux import planning_tools as planning_tools
from .test_pr05_e2e import digest, packets


@pytest.mark.integration
@pytest.mark.parametrize(
    "video,audio,container,target",
    [
        ("vp9", "aac", "mp4", "mkv"),
        ("h264", "opus", "mp4", "mkv"),
        ("h264", "aac", "mkv", "mkv"),
        ("h264", "aac", "mkv", "mp4"),
    ],
)
@pytest.mark.parametrize("edit", [None, "Changed", ""])
def test_preserved_metadata_and_compatible_copy(
    tmp_path: Path,
    planning_tools: tuple[str, str],
    video: str,
    audio: str,
    container: str,
    edit: str | None,
    target: str,
) -> None:
    source = tmp_path / f"source.{container}"
    generate(
        planning_tools[0],
        [
            *VIDEO,
            *AUDIO,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libvpx-vp9" if video == "vp9" else "libx264",
            "-threads",
            "1",
            "-c:a",
            "libopus" if audio == "opus" else "aac",
            "-metadata",
            "title=Container title",
            "-metadata",
            "artist=Creator",
            "-metadata",
            "album=Collection",
            "-metadata",
            "comment=Container comment",
            "-metadata",
            "genre=Test",
            "-metadata",
            "date=2026",
            "-metadata",
            "copyright=Synthetic",
            "-metadata",
            "description=Description",
            "-metadata:s:0",
            "title=Video title",
            "-metadata:s:0",
            "comment=Stream comment",
            "-metadata:s:0",
            "description=Stream description",
        ],
        source,
    )
    inspector = InspectionService(FFprobeAdapter(planning_tools[1]))
    asset = inspector.inspect(source)
    selections = tuple(
        TrackSelection(
            StreamReference(asset.source, s.index),
            metadata=MetadataIntent(title=edit) if s.kind == "video" else MetadataIntent(),
        )
        for s in asset.streams
    )
    planner = OperationPlanningService()
    profile = OutputProfile(target, str(tmp_path / f"output.{target}"))
    plan = planner.plan((asset,), selections, profile)
    plan = planner.plan(
        (asset,),
        selections,
        profile,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    before = digest(source)
    result = RemuxExecutionService().execute(
        ExecutionRequest(
            plan,
            plan.revision,
            plan.revision,
            ProcessConfiguration(ffmpeg=planning_tools[0], ffprobe=planning_tools[1]),
        )
    )
    assert result.published, result.validation
    assert digest(source) == before
    actual = inspector.inspect(profile.path)
    assert [s.codec for s in actual.streams] == [video, audio]
    for original, output in zip(asset.streams, actual.streams, strict=True):
        assert packets(planning_tools[1], source, original.index) == packets(
            planning_tools[1], Path(profile.path), output.index
        )
    assert metadata_value(actual.format.tags, "title") == "Container title"
    assert metadata_value(actual.format.tags, "artist") == "Creator"
    for key in ("album", "comment", "genre", "date", "copyright", "description"):
        assert metadata_value(actual.format.tags, key) == metadata_value(asset.format.tags, key)
    if container == "mkv" and target == "mkv":
        assert metadata_value(actual.streams[0].tags, "title") == (
            "Video title" if edit is None else edit or None
        )
        assert metadata_value(actual.streams[0].tags, "comment") == "Stream comment"
        assert metadata_value(actual.streams[0].tags, "description") == "Stream description"

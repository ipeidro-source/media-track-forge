"""Synthetic audit regressions; local files do not establish SMB transport evidence."""

from pathlib import Path

import pytest

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import ExecutionRequest, ProcessConfiguration
from mediatrack_forge.domain.planning import OutputProfile, StreamReference, TrackSelection
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.subtitle_packets import subtitle_cues
from mediatrack_forge.ui.presentation_model import DesktopBackend

from .conftest import VIDEO, generate
from .test_planning_mux import planning_tools as planning_tools
from .test_pr05_e2e import digest


@pytest.mark.integration
@pytest.mark.parametrize("container,index", [("mp4", 3), ("mkv", 5)])
def test_gapped_subtitle_extraction(
    tmp_path: Path, planning_tools: tuple[str, str], container: str, index: int
) -> None:
    srt = tmp_path / "captions.srt"
    srt.write_text(
        "1\n00:00:00,100 --> 00:00:00,200\nFirst\n\n2\n00:00:00,300 --> 00:00:00,400\nSecond\n",
        encoding="utf-8",
    )
    source = tmp_path / f"source.{container}"
    generate(
        planning_tools[0],
        [
            *VIDEO,
            "-i",
            str(srt),
            "-map",
            "0:v:0",
            *[arg for _ in range(index) for arg in ("-map", "1:s:0")],
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:s",
            "mov_text" if container == "mp4" else "srt",
        ],
        source,
    )
    inspector = InspectionService(FFprobeAdapter(planning_tools[1]))
    asset = inspector.inspect(source)
    reference = StreamReference(asset.source, index)
    planner = ExtractionPlanningService()
    output = tmp_path / "extracted.srt"
    plan = planner.plan(asset, reference, str(output))
    plan = planner.plan(
        asset,
        reference,
        str(output),
        acknowledged_warnings=frozenset(plan.pending_warnings),
        acknowledged_revision=plan.revision,
    )
    before = digest(source)
    result = ExtractionExecutionService().execute(
        ExecutionRequest(
            plan,
            plan.revision,
            plan.revision,
            ProcessConfiguration(ffmpeg=planning_tools[0], ffprobe=planning_tools[1]),
        )
    )
    assert result.published, result.validation
    assert digest(source) == before
    assert "First" in output.read_text(encoding="utf-8")
    assert "Second" in output.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".mediatrack-*"))
    if container == "mp4":
        remuxer = OperationPlanningService()
        selections = tuple(
            TrackSelection(StreamReference(asset.source, s.index), include=s.index in (0, index))
            for s in asset.streams
        )
        profile = OutputProfile("mkv", str(tmp_path / "converted.mkv"))
        remux = remuxer.plan((asset,), selections, profile)
        assert "SUBTITLE_FORMATTING_MAY_CHANGE" in remux.pending_warnings
        remux = remuxer.plan(
            (asset,),
            selections,
            profile,
            acknowledged_warnings=frozenset(remux.pending_warnings),
            acknowledged_revision=remux.revision,
        )
        result = RemuxExecutionService().execute(
            ExecutionRequest(
                remux,
                remux.revision,
                remux.revision,
                ProcessConfiguration(ffmpeg=planning_tools[0], ffprobe=planning_tools[1]),
            )
        )
        assert result.published, result.validation
        actual = inspector.inspect(profile.path)
        assert [s.codec for s in actual.streams] == ["h264", "subrip"]
        assert subtitle_cues(source, index, "mov_text", planning_tools[1], 30) == subtitle_cues(
            Path(profile.path), 1, "subrip", planning_tools[1], 30
        )
        assert digest(source) == before


@pytest.mark.integration
@pytest.mark.parametrize("subtitle", [False, True])
def test_content_inspection_and_video_eligibility_are_separate(
    tmp_path: Path, planning_tools: tuple[str, str], subtitle: bool
) -> None:
    path = tmp_path / ("captions.mkv" if subtitle else "video.txt")
    if subtitle:
        path.write_text("1\n00:00:00,000 --> 00:00:00,300\nSynthetic\n", encoding="utf-8")
    else:
        generate(
            planning_tools[0],
            [*VIDEO, "-map", "0:v:0", "-c:v", "libx264", "-threads", "1", "-f", "matroska"],
            path,
        )
    backend = DesktopBackend(ProcessConfiguration(ffprobe=planning_tools[1]))
    asset = backend.inspect(str(path))
    assert asset.format.name == ("srt" if subtitle else "matroska,webm")
    plan = OperationPlanningService().plan(
        (asset,),
        tuple(TrackSelection(StreamReference(asset.source, s.index)) for s in asset.streams),
        OutputProfile("mkv", str(tmp_path / "output.mkv")),
    )
    assert any(issue.code == "VIDEO_REQUIRED" for issue in plan.issues) == subtitle
    assert not Path(plan.output.path).exists()

"""Real-media external SRT, elementary extraction, cancellation and progress evidence."""

import hashlib
import json
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from mediatrack_forge.application.control import ExecutionControl, ProgressEvent
from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.external_subtitles import ExternalSubtitleService
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import (
    ExecutionFailure,
    ExecutionRequest,
    ProcessConfiguration,
    ProcessOutcome,
)
from mediatrack_forge.domain.extraction import EXTRACTION_MATRIX
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import (
    MetadataIntent,
    OperationPlan,
    OutputProfile,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.ffmpeg_process import FFmpegProcessRunner
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.staging import PrivateStage

from .conftest import AUDIO, VIDEO, generate
from .test_execution_e2e import media
from .test_planning_mux import planning_tools as planning_tools

pytestmark = pytest.mark.integration
SRT = "1\n00:00:00,000 --> 00:00:00,300\nSynthetic 日本語\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packets(tool: str, path: Path, index: int) -> list[str]:
    response = subprocess.run(
        [
            tool,
            "-v",
            "error",
            "-select_streams",
            str(index),
            "-show_packets",
            "-show_data_hash",
            "sha256",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=20,
    )
    return [p["data_hash"] for p in json.loads(response.stdout)["packets"]]


@pytest.mark.parametrize(
    "kind,container,count",
    [("avi", "mkv", 1), ("mp4", "mp4", 1), ("silent", "mkv", 1), ("mp4", "mkv", 2)],
)
def test_external_srt_product_e2e(
    tmp_path: Path, planning_tools: tuple[str, str], kind: str, container: str, count: int
) -> None:
    tools = planning_tools
    inspector = InspectionService(FFprobeAdapter(tools[1]))
    if kind == "silent":
        path = tmp_path / "silent 日本語.mp4"
        generate(tools[0], [*VIDEO, "-map", "0:v:0", "-c:v", "libx264", "-threads", "1"], path)
        source = inspector.inspect(path)
    else:
        source = media(tmp_path, tools, kind)
    assets = [source]
    tracks = []
    selections = [TrackSelection(StreamReference(source.source, s.index)) for s in source.streams]
    for number in range(count):
        path = tmp_path / f"external {number} 日本語.srt"
        path.write_text(SRT, encoding="utf-8-sig")
        metadata = MetadataIntent(
            language="eng" if number == 0 else "fra",
            title=f"Subtitle {number}",
            default=number == 0,
            forced=number == 1,
        )
        asset, track = ExternalSubtitleService(inspector).import_srt(path, metadata)
        assets.append(asset)
        tracks.append(track)
        selections.append(
            TrackSelection(
                StreamReference(asset.source, track.stream_index or 0), metadata=metadata
            )
        )
    output = OutputProfile(container, str(tmp_path / f"output 日本語.{container}"))
    planner = OperationPlanningService()
    plan = planner.plan(tuple(assets), tuple(selections), output, external_tracks=tuple(tracks))
    assert plan.intrinsically_valid, plan.issues
    if container == "mp4":
        assert "SUBTITLE_FORMATTING_MAY_CHANGE" in plan.pending_warnings
    plan = planner.plan(
        tuple(assets),
        tuple(selections),
        output,
        external_tracks=tuple(tracks),
        acknowledged_warnings=frozenset(plan.pending_warnings),
        acknowledged_revision=plan.revision,
    )
    assert [(s.input_index, s.reference.index) for s in plan.included][-count:] == [
        (n + 1, assets[n + 1].streams[0].index) for n in range(count)
    ]
    originals = {a.source.path: digest(a.source.path) for a in assets}
    events: list[ProgressEvent] = []
    result = RemuxExecutionService().execute(
        ExecutionRequest(
            plan,
            plan.revision,
            plan.revision,
            ProcessConfiguration(ffmpeg=tools[0], ffprobe=tools[1]),
        ),
        control=ExecutionControl(listener=events.append),
    )
    assert result.published and result.state == "completed", (
        result.diagnostics,
        result.validation.checks if result.validation else None,
    )
    assert result.destination is not None
    actual = inspector.inspect(result.destination)
    assert [s.codec for s in actual.streams] == [s.target_codec for s in plan.included]
    assert sum(s.kind == "audio" for s in actual.streams) == (0 if kind == "silent" else 1)
    for index, stream in enumerate(source.streams):
        assert packets(tools[1], source.source.path, stream.index) == packets(
            tools[1], result.destination, index
        )
    if container == "mkv":
        for number in range(count):
            assert packets(tools[1], assets[number + 1].source.path, 0) == packets(
                tools[1], result.destination, len(source.streams) + number
            )
            assert actual.streams[len(source.streams) + number].language == (
                "eng" if number == 0 else "fra"
            )
    assert all(digest(path) == value for path, value in originals.items())
    assert not list(tmp_path.glob(".mediatrack-*"))
    assert events[0].phase == "preparing" and events[-1].phase == "completed"
    assert events[-1].percent == 100 and all(e.percent != 100 for e in events[:-1])
    assert {"running", "validating", "publishing"} <= {e.phase for e in events}


@pytest.mark.parametrize("row", EXTRACTION_MATRIX)
def test_every_enabled_extraction_pair(
    tmp_path: Path, planning_tools: tuple[str, str], row: tuple[str, str, str, str, str | None]
) -> None:
    codec, family, extension, muxer, filter_name = row
    tools = planning_tools
    source = tmp_path / ("input 日本語." + {"matroska": "mkv"}.get(family, family))
    srt = tmp_path / "fixture.srt"
    srt.write_text(SRT, encoding="utf-8")
    if codec in ("h264", "hevc"):
        options = [
            *VIDEO,
            "-map",
            "0:v:0",
            "-c:v",
            "libx264" if codec == "h264" else "libx265",
            "-threads",
            "1",
        ]
        if codec == "hevc":
            options += ["-x265-params", "pools=1:frame-threads=1"]
    elif codec in ("aac", "mp3"):
        options = [*AUDIO, "-map", "0:a:0", "-c:a", "aac" if codec == "aac" else "libmp3lame"]
        if codec == "mp3":
            options = [
                *VIDEO,
                *AUDIO,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "mpeg4",
                "-c:a",
                "libmp3lame",
                "-threads",
                "1",
            ]
    else:
        options = [
            *VIDEO,
            "-i",
            str(srt),
            "-map",
            "0:v:0",
            "-map",
            "1:s:0",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:s",
            "mov_text" if codec == "mov_text" else "srt",
        ]
    generate(tools[0], options, source)
    inspector = InspectionService(FFprobeAdapter(tools[1]))
    asset = inspector.inspect(source)
    selected = next(s for s in asset.streams if s.codec == codec)
    planner = ExtractionPlanningService()
    path = str(tmp_path / f"extracted 日本語.{extension}")
    reference = StreamReference(asset.source, selected.index)
    plan = planner.plan(asset, reference, path)
    plan = planner.plan(
        asset,
        reference,
        path,
        acknowledged_warnings=frozenset(plan.pending_warnings),
        acknowledged_revision=plan.revision,
    )
    assert plan.execution_allowed, plan.issues
    assert plan.bitstream_filters == ((filter_name,) if filter_name else ())
    original = digest(source)
    result = ExtractionExecutionService(ffprobe=tools[1]).execute(
        ExecutionRequest(
            plan,
            plan.revision,
            plan.revision,
            ProcessConfiguration(ffmpeg=tools[0], ffprobe=tools[1]),
        )
    )
    assert result.published and result.state == "completed", (
        result.diagnostics,
        result.validation.checks if result.validation else None,
    )
    assert result.destination is not None and digest(source) == original
    actual = inspector.inspect(result.destination)
    assert len(actual.streams) == 1 and actual.streams[0].codec == plan.included[0].target_codec
    assert actual.format.name == ("aac" if muxer == "adts" else muxer)
    # Normalize framing through the same explicit format/filter for a packet-level oracle.
    oracle = tmp_path / f"oracle.{extension}"
    arguments = [
        "-i",
        str(source),
        "-map",
        f"0:{selected.index}",
        "-c:0",
        "srt" if codec == "mov_text" else "copy",
    ]
    if filter_name:
        arguments += ["-bsf:0", filter_name]
    generate(tools[0], [*arguments, "-f", muxer], oracle)
    assert packets(tools[1], oracle, 0) == packets(tools[1], result.destination, 0)
    if extension == "srt":
        assert "Synthetic 日本語" in result.destination.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".mediatrack-*"))


def test_malformed_and_changed_external_srt(
    tmp_path: Path, planning_tools: tuple[str, str]
) -> None:
    tools = planning_tools
    source = media(tmp_path, tools, "mp4")
    inspector = InspectionService(FFprobeAdapter(tools[1]))
    path = tmp_path / "external.srt"
    path.write_text("1\n00:00:05,000 --> 00:00:01,000\nMalformed\n", encoding="utf-8")
    with pytest.raises(ExecutionFailure, match="INVALID_EXTERNAL_SRT"):
        ExternalSubtitleService(inspector).import_srt(path)
    path.write_text(SRT, encoding="utf-8")
    subtitle, track = ExternalSubtitleService(inspector).import_srt(path)
    planner = OperationPlanningService()
    selections = tuple(
        TrackSelection(StreamReference(a.source, s.index))
        for a in (source, subtitle)
        for s in a.streams
    )
    plan = planner.plan(
        (source, subtitle),
        selections,
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
        external_tracks=(track,),
    )
    plan = replace(
        plan,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    path.write_text(SRT + "\n2\n00:00:00,300 --> 00:00:00,400\nChanged\n", encoding="utf-8")
    result = RemuxExecutionService().execute(ExecutionRequest(plan, plan.revision, plan.revision))
    assert not result.published and result.state == "failed"
    assert not (tmp_path / "out.mkv").exists() and not list(tmp_path.glob(".mediatrack-*"))


class RealtimeRunner(FFmpegProcessRunner):
    def run_controlled(
        self, arguments: tuple[str, ...], timeout_seconds: float, control: ExecutionControl | None
    ) -> ProcessOutcome:
        args = list(arguments)
        args.insert(args.index("-i"), "-re")
        return super().run_controlled(tuple(args), timeout_seconds, control)


@pytest.mark.parametrize("extract", [False, True])
def test_cancel_actual_running_operation(
    tmp_path: Path, planning_tools: tuple[str, str], extract: bool
) -> None:
    tools = planning_tools
    source = tmp_path / "long 日本語.mp4"
    generate(
        tools[0],
        [
            "-f",
            "lavfi",
            "-i",
            "color=s=64x48:r=10:d=8",
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-threads",
            "1",
        ],
        source,
    )
    inspector = InspectionService(FFprobeAdapter(tools[1]))
    asset = inspector.inspect(source)
    reference = StreamReference(asset.source, 0)
    plan: OperationPlan
    service: RemuxExecutionService
    if extract:
        plan = ExtractionPlanningService().plan(asset, reference, str(tmp_path / "out.h264"))
        plan = replace(
            plan,
            acknowledged_revision=plan.revision,
            acknowledged_warnings=frozenset(plan.pending_warnings),
        )
        service = ExtractionExecutionService(runner=RealtimeRunner(), ffprobe=tools[1])
    else:
        plan = OperationPlanningService().plan(
            (asset,), (TrackSelection(reference),), OutputProfile("mkv", str(tmp_path / "out.mkv"))
        )
        plan = replace(
            plan,
            acknowledged_revision=plan.revision,
            acknowledged_warnings=frozenset(plan.pending_warnings),
        )
        service = RemuxExecutionService(runner=RealtimeRunner())
    control = ExecutionControl()
    running = threading.Event()

    def listen(event: ProgressEvent) -> None:
        if event.phase == "running" and event.processed_seconds is not None:
            running.set()
            control.cancellation.cancel()

    control.listener = listen
    original = digest(source)
    result = service.execute(
        ExecutionRequest(
            plan,
            plan.revision,
            plan.revision,
            ProcessConfiguration(ffmpeg=tools[0], ffprobe=tools[1]),
        ),
        control=control,
    )
    assert running.is_set() and result.state == "cancelled" and result.cleanup_complete, result
    assert not result.published and digest(source) == original
    assert not list(tmp_path.glob("out.*")) and not list(tmp_path.glob(".mediatrack-*"))


@pytest.mark.parametrize("after", [False, True])
def test_publication_commit_boundary(
    tmp_path: Path, planning_tools: tuple[str, str], monkeypatch: pytest.MonkeyPatch, after: bool
) -> None:
    from .test_execution_e2e import confirmed

    source = media(tmp_path, planning_tools, "mp4")
    execution = confirmed(source, tmp_path / "out.mp4", planning_tools)
    control = ExecutionControl()
    cancellers: list[threading.Thread] = []
    accepted: list[bool] = []
    if after:
        original = PrivateStage.publish

        def publish(stage: PrivateStage, path: Path) -> None:
            original(stage, path)
            entered = threading.Event()

            def cancel_after_link() -> None:
                entered.set()
                accepted.append(control.cancellation.cancel())

            thread = threading.Thread(target=cancel_after_link)
            cancellers.append(thread)
            thread.start()
            assert entered.wait(3)

        monkeypatch.setattr(PrivateStage, "publish", publish)

        def listener(event: ProgressEvent) -> None:
            if event.phase == "completed":
                assert not control.cancellation.cancel()

        control.listener = listener
    else:

        def cancel_before(event: ProgressEvent) -> None:
            if event.phase == "publishing":
                control.cancellation.cancel()

        control.listener = cancel_before
    result = RemuxExecutionService().execute(execution, control=control)
    for thread in cancellers:
        thread.join(3)
        assert not thread.is_alive()
    if after:
        assert (
            accepted == [False] and result.destination is not None and result.destination.exists()
        )
    assert result.published == after and result.state == ("completed" if after else "cancelled")


def test_indeterminate_real_remux_progress(tmp_path: Path, planning_tools: tuple[str, str]) -> None:
    tools = planning_tools
    source = media(tmp_path, tools, "mp4")
    source = replace(
        source,
        format=replace(source.format, duration_seconds=None),
        streams=tuple(
            replace(
                s, duration_seconds=None, tags=tuple((k, v) for k, v in s.tags if k != "DURATION")
            )
            for s in source.streams
        ),
    )
    real = InspectionService(FFprobeAdapter(tools[1]))

    class UnknownSourceTiming:
        def inspect(self, path: str | Path, *, timeout_seconds: float = 30.0) -> MediaAsset:
            return (
                source
                if Path(path) == source.source.path
                else real.inspect(path, timeout_seconds=timeout_seconds)
            )

    planner = OperationPlanningService()
    selections = tuple(
        TrackSelection(StreamReference(source.source, s.index)) for s in source.streams
    )
    plan = planner.plan((source,), selections, OutputProfile("mkv", str(tmp_path / "out.mkv")))
    plan = replace(
        plan,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    events: list[ProgressEvent] = []
    result = RemuxExecutionService(inspector=UnknownSourceTiming()).execute(
        ExecutionRequest(plan, plan.revision, plan.revision),
        control=ExecutionControl(listener=events.append),
    )
    assert result.published and result.state == "completed"
    assert all(not e.determinate and e.percent is None for e in events if e.phase != "completed")


def test_external_srt_changed_during_execution_blocks_publication(
    tmp_path: Path, planning_tools: tuple[str, str]
) -> None:
    source = media(tmp_path, planning_tools, "mp4")
    inspector = InspectionService(FFprobeAdapter(planning_tools[1]))
    path = tmp_path / "sub.srt"
    path.write_text(SRT, encoding="utf-8")
    subtitle, track = ExternalSubtitleService(inspector).import_srt(path)
    selections = tuple(
        TrackSelection(StreamReference(a.source, s.index))
        for a in (source, subtitle)
        for s in a.streams
    )
    plan = OperationPlanningService().plan(
        (source, subtitle),
        selections,
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
        external_tracks=(track,),
    )
    plan = replace(
        plan,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )

    def mutate(event: ProgressEvent) -> None:
        if event.phase == "validating":
            path.write_text(SRT.replace("Synthetic", "Changed"), encoding="utf-8")

    result = RemuxExecutionService().execute(
        ExecutionRequest(plan, plan.revision, plan.revision),
        control=ExecutionControl(listener=mutate),
    )
    assert not result.published and result.state == "failed" and result.cleanup_complete
    assert not list(tmp_path.glob("out.*")) and not list(tmp_path.glob(".mediatrack-*"))


@pytest.mark.parametrize("race", [False, True])
def test_extraction_exclusive_destination_collision(
    tmp_path: Path, planning_tools: tuple[str, str], race: bool
) -> None:
    source = media(tmp_path, planning_tools, "mp4")
    destination = tmp_path / "out.h264"
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 0), str(destination)
    )
    plan = replace(
        plan,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(plan.pending_warnings),
    )
    original = digest(source.source.path)
    control = ExecutionControl()
    if race:

        def occupy(event: ProgressEvent) -> None:
            if event.phase == "publishing":
                destination.write_bytes(b"competitor")

        control.listener = occupy
    else:
        destination.write_bytes(b"competitor")
    result = ExtractionExecutionService().execute(
        ExecutionRequest(plan, plan.revision, plan.revision), control=control
    )
    assert not result.published and result.state == "failed" and result.cleanup_complete
    assert destination.read_bytes() == b"competitor" and digest(source.source.path) == original
    assert not list(tmp_path.glob(".mediatrack-*"))

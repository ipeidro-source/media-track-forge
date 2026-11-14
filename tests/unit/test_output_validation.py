"""Independent staged-output validation with normalized synthetic observations."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_planning import acknowledged, asset, select, stream

from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.media import Chapter
from mediatrack_forge.domain.planning import OperationPlan, OutputProfile
from mediatrack_forge.infrastructure.output_validation import FFprobeOutputValidator, timing_budget


@pytest.fixture
def validation_plan(tmp_path: Path) -> OperationPlan:
    video = stream(3, "video", "h264") | {
        "duration": "10",
        "avg_frame_rate": "25/1",
        "time_base": "1/1000",
        "width": 64,
        "height": 48,
        "tags": {"language": "eng", "title": "Selected"},
    }
    audio = stream(8, "audio", "aac") | {"duration": "10", "sample_rate": "48000", "channels": 1}
    source = asset(tmp_path, [video, audio])
    return acknowledged(
        OperationPlanningService().plan(
            (source,),
            (select(source, 3), select(source, 8)),
            OutputProfile("mkv", str(tmp_path / "out.mkv")),
        )
    )


def test_validator_mismatches_block_publication(
    validation_plan: OperationPlan, tmp_path: Path
) -> None:
    original = validation_plan.sources[0]
    observed = replace(
        original, format=replace(original.format, name="matroska,webm", duration_seconds=10)
    )
    staged = tmp_path / "stage.part"
    staged.write_bytes(b"nonempty")
    observations = [
        (replace(observed, format=replace(observed.format, name="mp4")), "CONTAINER"),
        (replace(observed, streams=observed.streams[:1]), "STREAM_COUNT"),
        (replace(observed, streams=tuple(reversed(observed.streams))), "STREAM_KIND"),
        (
            replace(
                observed, streams=(replace(observed.streams[0], codec="hevc"), observed.streams[1])
            ),
            "STREAM_CODEC",
        ),
        (
            replace(
                observed, streams=(observed.streams[0], replace(observed.streams[1], codec="mp3"))
            ),
            "STREAM_CODEC",
        ),
        (
            replace(
                observed,
                streams=(
                    replace(observed.streams[0], tags=(("title", "Wrong"),)),
                    observed.streams[1],
                ),
            ),
            "STREAM_METADATA",
        ),
        (
            replace(
                observed,
                streams=(
                    replace(observed.streams[0], disposition=(("default", 1),)),
                    observed.streams[1],
                ),
            ),
            "STREAM_DISPOSITION",
        ),
        (replace(observed, format=replace(observed.format, duration_seconds=1)), "DURATION"),
        (
            replace(
                observed,
                streams=(replace(observed.streams[0], duration_seconds=1), observed.streams[1]),
            ),
            "DURATION",
        ),
        (replace(observed, chapters=(Chapter(0, 0, 10, "unexpected", ()),)), "CHAPTER_COUNT"),
    ]
    inspector = Mock()
    inspector.inspect.return_value = observed
    assert FFprobeOutputValidator().validate(validation_plan, staged, inspector, 5).passed
    for changed, expected in observations:
        inspector.inspect.return_value = changed
        report = FFprobeOutputValidator().validate(validation_plan, staged, inspector, 5)
        assert not report.passed
        assert any(c.code == expected and c.status == "error" for c in report.checks)


def test_missing_empty_and_unprobeable_output(
    validation_plan: OperationPlan, tmp_path: Path
) -> None:
    inspector = Mock()
    path = tmp_path / "stage.part"
    for contents in (None, b""):
        if contents is not None:
            path.write_bytes(contents)
        assert not FFprobeOutputValidator().validate(validation_plan, path, inspector, 5).passed
    path.write_bytes(b"invalid")
    inspector.inspect.side_effect = ValueError()
    assert not FFprobeOutputValidator().validate(validation_plan, path, inspector, 5).passed


def test_missing_duration_is_explicitly_unverified(
    validation_plan: OperationPlan, tmp_path: Path
) -> None:
    source = validation_plan.sources[0]
    unknown = replace(
        source,
        streams=tuple(replace(s, duration_seconds=None) for s in source.streams),
        format=replace(source.format, name="matroska", duration_seconds=None),
    )
    plan = replace(
        validation_plan,
        sources=(unknown,),
        included=tuple(
            replace(p, source_stream=unknown.streams[i])
            for i, p in enumerate(validation_plan.included)
        ),
    )
    inspector = Mock()
    inspector.inspect.return_value = unknown
    path = tmp_path / "stage.part"
    path.write_bytes(b"output")
    report = FFprobeOutputValidator().validate(plan, path, inspector, 5)
    assert report.passed and any(c.code == "DURATION_UNVERIFIED" for c in report.checks)
    assert timing_budget(source.streams) == pytest.approx(0.042)


def test_subtitle_attachment_and_chapter_guarantees(tmp_path: Path) -> None:
    source = asset(
        tmp_path,
        [
            stream(0, "video", "h264"),
            stream(4, "subtitle", "subrip"),
            stream(9, "attachment", None)
            | {"tags": {"filename": "note.txt", "mimetype": "text/plain"}},
        ],
        chapters=[{"id": 2, "start_time": "0", "end_time": "1", "tags": {"title": "Opening"}}],
    )
    plan = acknowledged(
        OperationPlanningService().plan(
            (source,),
            tuple(select(source, s.index) for s in source.streams),
            OutputProfile("mkv", str(tmp_path / "out.mkv")),
        )
    )
    observed = replace(source, format=replace(source.format, name="matroska"))
    path = tmp_path / "stage.part"
    path.write_bytes(b"output")
    inspector = Mock()
    cases = [
        (
            replace(
                observed,
                streams=(
                    source.streams[0],
                    replace(source.streams[1], codec="mov_text"),
                    source.streams[2],
                ),
            ),
            "STREAM_CODEC",
        ),
        (replace(observed, streams=source.streams[:2]), "STREAM_COUNT"),
        (
            replace(observed, streams=(*source.streams[:2], replace(source.streams[2], tags=()))),
            "STREAM_METADATA",
        ),
        (replace(observed, chapters=()), "CHAPTER_COUNT"),
        (
            replace(observed, chapters=(replace(source.chapters[0], title="Wrong"),)),
            "CHAPTER_TITLE",
        ),
    ]
    for changed, code in cases:
        inspector.inspect.return_value = changed
        report = FFprobeOutputValidator().validate(plan, path, inspector, 5)
        assert not report.passed and any(
            c.code == code and c.status == "error" for c in report.checks
        )


def test_mp4_only_acknowledged_metadata_uncertainty_can_warn(
    validation_plan: OperationPlan,
    tmp_path: Path,
) -> None:
    source = validation_plan.sources[0]
    plan = acknowledged(
        OperationPlanningService().plan(
            (source,), validation_plan.selections, OutputProfile("mp4", str(tmp_path / "out.mp4"))
        )
    )
    observed = replace(
        source,
        format=replace(source.format, name="mov,mp4", duration_seconds=10),
        streams=(
            replace(source.streams[0], tags=(), disposition=(("default", 1),)),
            source.streams[1],
        ),
    )
    inspector = Mock()
    inspector.inspect.return_value = observed
    path = tmp_path / "stage.part"
    path.write_bytes(b"output")
    report = FFprobeOutputValidator().validate(plan, path, inspector, 5)
    assert report.passed and any(
        c.code == "STREAM_METADATA" and c.status == "warning" for c in report.checks
    )
    inspector.inspect.return_value = replace(observed, streams=tuple(reversed(observed.streams)))
    assert not FFprobeOutputValidator().validate(plan, path, inspector, 5).passed


@pytest.mark.parametrize(
    "before,after,has_budget,code,status",
    [
        (10.0, 1.0, False, "DURATION_TOLERANCE_UNAVAILABLE", "error"),
        (10.0, 10.0, False, "DURATION_TOLERANCE_UNAVAILABLE", "error"),
        (10.0, None, False, "DURATION_UNVERIFIABLE", "error"),
        (10.0, None, True, "DURATION_UNVERIFIABLE", "error"),
        (10.0, 10.0, True, "DURATION", "passed"),
        (None, 1.0, False, "DURATION_UNVERIFIED", "warning"),
        (None, 1.0, True, "DURATION_UNVERIFIED", "warning"),
    ],
)
def test_duration_integrity_requires_tolerance_for_known_source(
    validation_plan: OperationPlan,
    tmp_path: Path,
    before: float | None,
    after: float | None,
    has_budget: bool,
    code: str,
    status: str,
) -> None:
    original = validation_plan.sources[0]
    source_streams = tuple(
        replace(
            s,
            duration_seconds=before,
            properties=s.properties
            if has_budget
            else replace(
                s.properties, time_base=None, average_frame_rate=None, sample_rate_hz=None
            ),
        )
        for s in original.streams
    )
    source = replace(original, streams=source_streams)
    plan = replace(
        validation_plan,
        sources=(source,),
        included=tuple(
            replace(p, source_stream=source_streams[i])
            for i, p in enumerate(validation_plan.included)
        ),
    )
    observed = replace(
        source,
        format=replace(source.format, name="matroska", duration_seconds=after),
        streams=tuple(replace(s, duration_seconds=after) for s in source_streams),
    )
    assert (timing_budget(source.streams + observed.streams) is not None) is has_budget
    inspector = Mock()
    inspector.inspect.return_value = observed
    path = tmp_path / "duration-stage.part"
    path.write_bytes(b"nonempty")
    report = FFprobeOutputValidator().validate(plan, path, inspector, 5)
    matching = [check for check in report.checks if check.code == code]
    assert matching and all(check.status == status for check in matching)
    assert report.passed is (status != "error")
    assert all(
        check.expected_seconds == before and check.observed_seconds == after for check in matching
    )
    if not has_budget:
        assert all(check.tolerance_seconds is None for check in matching)

"""Planning-only acceptance coverage; no FFmpeg, GUI, network or output writes."""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from mediatrack_forge.application.inspection import snapshot_source
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.media import MediaAsset
from mediatrack_forge.domain.planning import (
    ExternalTrack,
    MetadataIntent,
    OperationPlan,
    OutputProfile,
    StreamReference,
    TrackSelection,
)
from mediatrack_forge.infrastructure.ffmpeg_arguments import build_arguments
from mediatrack_forge.infrastructure.ffprobe_json import parse_response
from mediatrack_forge.infrastructure.planning_paths import equivalent_paths
from mediatrack_forge.ui.operation_plan_json import plan_document, serialize_plan


def asset(
    tmp_path: Path,
    streams: list[dict[str, object]],
    *,
    name: str = "source.mkv",
    chapters: list[dict[str, object]] | None = None,
) -> MediaAsset:
    path = tmp_path / name
    path.write_bytes(b"synthetic unit source")
    return parse_response(
        json.dumps(
            {"format": {"format_name": "synthetic"}, "streams": streams, "chapters": chapters or []}
        ).encode(),
        snapshot_source(path),
    )


def stream(index: int, kind: str, codec: str | None) -> dict[str, object]:
    return {
        "index": index,
        "codec_type": kind,
        "codec_name": codec,
        "disposition": {"default": 0, "forced": 0},
    }


def select(
    source: MediaAsset,
    index: int,
    *,
    include: bool = True,
    metadata: MetadataIntent | None = None,
) -> TrackSelection:
    return TrackSelection(
        StreamReference(source.source, index), include, metadata or MetadataIntent()
    )


def acknowledged(plan: OperationPlan) -> OperationPlan:
    return OperationPlanningService().plan(
        plan.sources,
        plan.selections,
        plan.output,
        external_tracks=plan.external_tracks,
        preserve_chapters=plan.preserve_chapters,
        acknowledged_revision=plan.revision,
        acknowledged_warnings=frozenset(
            item.code for item in plan.issues if item.severity == "warning"
        ),
    )


def codes(plan: OperationPlan) -> set[str]:
    return {item.code for item in plan.issues}


def test_ac01_ac05_video_only_mp4_plan(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(5, "video", "h264"), stream(9, "audio", "aac")])
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 5), select(source, 9, include=False)),
        OutputProfile("mp4", str(tmp_path / "silent.mp4")),
    )
    plan = acknowledged(plan)
    assert plan.execution_allowed
    assert [(s.reference.index, s.output_index) for s in plan.included] == [(5, 0)]
    assert [(s.reference.index, s.explicit, s.action) for s in plan.excluded] == [
        (9, True, "exclude")
    ]
    assert plan.arguments is not None and "0:5" in plan.arguments and "0:9" not in plan.arguments
    assert not (tmp_path / "silent.mp4").exists()


def test_ac02_exact_audio_selection_and_subtitle_removal(tmp_path: Path) -> None:
    source = asset(
        tmp_path,
        [
            stream(0, "video", "h264"),
            stream(2, "audio", "aac"),
            stream(8, "audio", "mp3"),
            stream(11, "subtitle", "subrip"),
        ],
    )
    plan = OperationPlanningService().plan(
        (source,),
        tuple(select(source, i, include=i in (0, 8)) for i in (0, 2, 8, 11)),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
    )
    assert plan.execution_allowed
    assert [s.reference.index for s in plan.included] == [0, 8]
    assert [s.reference.index for s in plan.excluded] == [2, 11]


def test_ac10_grouping_preserves_requested_order_and_distinct_output_indices(
    tmp_path: Path,
) -> None:
    source = asset(
        tmp_path,
        [
            stream(10, "video", "h264"),
            stream(4, "audio", "aac"),
            stream(30, "video", "hevc"),
            stream(25, "audio", "mp3"),
        ],
    )
    plan = OperationPlanningService().plan(
        (source,),
        tuple(select(source, i) for i in (25, 30, 4, 10)),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
    )
    assert [s.reference.index for s in plan.included] == [30, 10, 25, 4]
    assert [s.output_index for s in plan.included] == [0, 1, 2, 3]
    assert plan.arguments is not None
    assert [plan.arguments[i + 1] for i, arg in enumerate(plan.arguments) if arg == "-map"] == [
        "0:30",
        "0:10",
        "0:25",
        "0:4",
    ]


@pytest.mark.parametrize(
    "container,codec,kind,supported",
    [
        ("mp4", "h264", "video", True),
        ("mkv", "mpeg4", "video", True),
        ("mp4", "mpeg4", "video", False),
        ("mp4", "dts", "audio", False),
        ("mkv", "dts", "audio", False),
        ("mkv", "ac3", "audio", False),
        ("mp4", "eac3", "audio", False),
        ("mkv", "ass", "subtitle", False),
        ("mkv", "hdmv_pgs_subtitle", "subtitle", False),
        ("mkv", "future", "video", False),
        ("mp4", None, "unknown", False),
        ("mkv", "bin_data", "data", False),
    ],
)
def test_ac03_ac06_conservative_codec_policy(
    tmp_path: Path, container: str, codec: str | None, kind: str, supported: bool
) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264"), stream(7, kind, codec)])
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0), select(source, 7)),
        OutputProfile(container, str(tmp_path / f"out.{container}")),
    )
    assert ("UNSUPPORTED_CODEC_FOR_CONTAINER" not in codes(plan)) == supported
    if not supported:
        assert not plan.intrinsically_valid and plan.arguments is None


@pytest.mark.parametrize(
    "container,action,target", [("mkv", "copy", "subrip"), ("mp4", "convert_subtitle", "mov_text")]
)
def test_ac04_ac05_subtitle_actions(
    tmp_path: Path, container: str, action: str, target: str
) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264"), stream(4, "subtitle", "subrip")])
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0), select(source, 4)),
        OutputProfile(container, str(tmp_path / f"out.{container}")),
    )
    assert plan.included[1].action == action and plan.included[1].target_codec == target
    if container == "mp4":
        assert "SUBTITLE_FORMATTING_MAY_CHANGE" in plan.pending_warnings
        assert not plan.execution_allowed and plan.arguments is None
    assert acknowledged(plan).execution_allowed


def test_external_srt_not_fabricated_from_filename(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264")])
    external_path = tmp_path / "future.srt"
    external_path.write_text("not imported", encoding="utf-8")
    external = ExternalTrack(snapshot_source(external_path), "subtitle")
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0),),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
        external_tracks=(external,),
    )
    assert "EXTERNAL_TRACK_NOT_VALIDATED" in codes(plan)
    assert plan.arguments is None
    assert external.codec is None and external.stream_index is None


def test_validated_external_reference_has_distinct_input_position(tmp_path: Path) -> None:
    primary = asset(tmp_path, [stream(3, "video", "h264")])
    subtitle = asset(tmp_path, [stream(7, "subtitle", "subrip")], name="inspected.srt")
    external = ExternalTrack(subtitle.source, "subtitle", 7, "subrip", "synthetic", validated=True)
    plan = OperationPlanningService().plan(
        (primary, subtitle),
        (select(primary, 3), select(subtitle, 7)),
        OutputProfile("mp4", str(tmp_path / "out.mp4")),
        external_tracks=(external,),
    )
    plan = acknowledged(plan)
    assert plan.execution_allowed and plan.arguments is not None
    assert "0:3" in plan.arguments and "1:7" in plan.arguments
    assert plan.included[1].action == "convert_subtitle"
    bad = replace(external, codec="ass")
    assert "EXTERNAL_TRACK_NOT_VALIDATED" in codes(
        OperationPlanningService().plan(
            plan.sources, plan.selections, plan.output, external_tracks=(bad,)
        )
    )


def test_duplicate_missing_and_stale_references(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264")])
    output = OutputProfile("mkv", str(tmp_path / "out.mkv"))
    for selections, expected in [
        ((select(source, 0), select(source, 0)), "DUPLICATE_SELECTION"),
        ((select(source, 99),), "UNKNOWN_STREAM_REFERENCE"),
    ]:
        plan = OperationPlanningService().plan((source,), selections, output)
        assert expected in codes(plan) and plan.arguments is None
    source.source.path.write_bytes(b"changed source")
    assert "SOURCE_CHANGED" in codes(
        OperationPlanningService().plan((source,), (select(source, 0),), output)
    )


def test_metadata_intent_source_immutable_and_default_conflicts(tmp_path: Path) -> None:
    source = asset(
        tmp_path, [stream(0, "video", "h264"), stream(2, "audio", "aac"), stream(9, "audio", "mp3")]
    )
    selection = select(source, 2, metadata=MetadataIntent("qzz", "日本語 title", True, True))
    output = OutputProfile("mkv", str(tmp_path / "out.mkv"))
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0), selection, select(source, 9, metadata=MetadataIntent(default=True))),
        output,
    )
    assert "CONFLICTING_DEFAULT_FLAGS" in codes(plan) and plan.arguments is None
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0), selection, select(source, 9, metadata=MetadataIntent(default=False))),
        output,
    )
    assert plan.execution_allowed
    assert dict(plan.included[1].output_tags) == {"language": "qzz", "title": "日本語 title"}
    assert dict(plan.included[1].output_disposition) == {"default": 1, "forced": 1}
    assert source.streams[1].language is None
    assert plan.arguments is not None and "default+forced" in plan.arguments


def test_metadata_loss_and_implicit_exclusions_require_acknowledgement(tmp_path: Path) -> None:
    video = stream(0, "video", "h264") | {
        "tags": {"language": "und", "unvalidated_tag": "significant"},
        "disposition": {"default": 0, "forced": 0, "original": 1},
    }
    source = asset(tmp_path, [video, stream(3, "data", "bin_data"), stream(7, "unknown", None)])
    plan = OperationPlanningService().plan(
        (source,), (select(source, 0),), OutputProfile("mkv", str(tmp_path / "out.mkv"))
    )
    assert {"STREAM_METADATA_EXCLUDED", "STREAM_IMPLICITLY_OMITTED", "DISPOSITION_LOSS"} <= codes(
        plan
    )
    assert plan.intrinsically_valid and not plan.execution_allowed
    assert len(plan.excluded) == 2 and all(not s.explicit for s in plan.excluded)
    assert dict(plan.included[0].output_tags)["language"] == "und"
    assert acknowledged(plan).execution_allowed


@pytest.mark.parametrize("container", ["mkv", "mp4"])
def test_attachments_and_chapters_are_explicit(tmp_path: Path, container: str) -> None:
    attachment = stream(9, "attachment", None) | {
        "tags": {"filename": "note.txt", "mimetype": "text/plain"}
    }
    source = asset(
        tmp_path,
        [stream(0, "video", "h264"), attachment],
        chapters=[{"id": 4, "start_time": "0", "end_time": "1", "tags": {"title": "Opening"}}],
    )
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0), select(source, 9)),
        OutputProfile(container, str(tmp_path / f"out.{container}")),
    )
    if container == "mkv":
        assert "CHAPTER_TIMESTAMPS_UNCERTAIN" in plan.pending_warnings
        assert not plan.execution_allowed
        plan = acknowledged(plan)
        assert plan.chapter_input_index == 0 and plan.execution_allowed
        assert dict(plan.included[1].output_tags) == {
            "filename": "note.txt",
            "mimetype": "text/plain",
        }
    else:
        assert {"CHAPTER_COPY_UNVALIDATED", "UNSUPPORTED_CODEC_FOR_CONTAINER"} <= codes(plan)
        assert not plan.execution_allowed


def test_ac07_ac12_destination_checks(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264")])
    existing = tmp_path / "existing.mkv"
    existing.write_bytes(b"keep")
    cases = [
        (str(source.source.path), "mkv", "SOURCE_DESTINATION_CONFLICT"),
        (str(existing), "mkv", "DESTINATION_EXISTS"),
        ("", "mkv", "INVALID_DESTINATION"),
        ("https://example.invalid/out.mkv", "mkv", "INVALID_DESTINATION"),
        (str(tmp_path / "out.avi"), "avi", "UNSUPPORTED_OUTPUT_CONTAINER"),
        (str(tmp_path / "out.mp4"), "mkv", "OUTPUT_EXTENSION_MISMATCH"),
    ]
    for path, container, expected in cases:
        plan = OperationPlanningService().plan(
            (source,), (select(source, 0),), OutputProfile(container, path)
        )
        assert expected in codes(plan) and plan.arguments is None
    assert existing.read_bytes() == b"keep"
    assert equivalent_paths(Path("C:/Media/FILE.mkv"), Path("c:/media/file.MKV"), windows=True)


def test_no_video_and_no_sources_block(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(0, "audio", "aac")])
    for sources in [(), (source,)]:
        plan = OperationPlanningService().plan(
            sources, (), OutputProfile("mkv", str(tmp_path / "out.mkv"))
        )
        assert "VIDEO_REQUIRED" in codes(plan) and not plan.execution_allowed


def test_additional_source_and_external_destination_conflicts(tmp_path: Path) -> None:
    primary = asset(tmp_path, [stream(0, "video", "h264")])
    extra = asset(tmp_path, [stream(0, "audio", "aac")], name="extra.mkv")
    plan = OperationPlanningService().plan(
        (primary, extra), (select(primary, 0),), OutputProfile("mkv", str(extra.source.path))
    )
    assert "SOURCE_DESTINATION_CONFLICT" in codes(plan)
    external = ExternalTrack(extra.source, "audio")
    plan = OperationPlanningService().plan(
        (primary,),
        (select(primary, 0),),
        OutputProfile("mkv", str(extra.source.path)),
        external_tracks=(external,),
    )
    assert "SOURCE_DESTINATION_CONFLICT" in codes(plan)


def test_metadata_clearing_missing_flags_and_und_warning(tmp_path: Path) -> None:
    source = asset(
        tmp_path,
        [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "tags": {"title": "Old", "language": "und"},
            }
        ],
    )
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0, metadata=MetadataIntent(title="")),),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
    )
    assert {"DISPOSITION_ABSENCE_UNCERTAIN", "LANGUAGE_UND_UNCERTAIN"} <= codes(plan)
    assert plan.included[0].output_disposition == ()
    assert dict(plan.included[0].output_tags) == {"language": "und", "title": ""}
    assert acknowledged(plan).execution_allowed


def test_chapter_exclusion_and_non_directory_parent(tmp_path: Path) -> None:
    source = asset(
        tmp_path,
        [stream(0, "video", "h264")],
        chapters=[{"id": 1, "start_time": "0", "end_time": "1"}],
    )
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0),),
        OutputProfile("mp4", str(tmp_path / "out.mp4")),
        preserve_chapters=False,
    )
    assert "CHAPTERS_EXCLUDED" in codes(plan) and plan.chapter_input_index is None
    plan = acknowledged(plan)
    assert plan.execution_allowed
    bad_parent = source.source.path / "out.mkv"
    assert "INVALID_DESTINATION" in codes(
        OperationPlanningService().plan(
            (source,), (select(source, 0),), OutputProfile("mkv", str(bad_parent))
        )
    )


def test_duplicate_sources_and_changed_snapshot_reference_block(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(0, "video", "h264")])
    request = select(source, 0)
    stale = replace(request, reference=StreamReference(replace(source.source, size_bytes=999), 0))
    plan = OperationPlanningService().plan(
        (source,), (stale,), OutputProfile("mkv", str(tmp_path / "out.mkv"))
    )
    assert "UNKNOWN_STREAM_REFERENCE" in codes(plan)
    plan = OperationPlanningService().plan((source, source), (request,), plan.output)
    assert "DUPLICATE_SOURCE" in codes(plan)


def test_unvalidated_attachment_mime_and_nul_metadata_block(tmp_path: Path) -> None:
    source = asset(
        tmp_path,
        [
            stream(0, "video", "h264"),
            stream(1, "attachment", None)
            | {"tags": {"filename": "font.ttf", "mimetype": "font/ttf"}},
        ],
    )
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0), select(source, 1)),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
    )
    assert "UNSUPPORTED_CODEC_FOR_CONTAINER" in codes(plan)
    plan = OperationPlanningService().plan(
        (source,), (select(source, 0, metadata=MetadataIntent(title="bad\x00title")),), plan.output
    )
    assert "INVALID_METADATA" in codes(plan) and plan.arguments is None


def test_public_contract_deterministic_and_command_policy(tmp_path: Path) -> None:
    source = asset(tmp_path, [stream(5, "video", "h264")])
    selections = (select(source, 5),)
    output = OutputProfile("mkv", str(tmp_path / "space 日本語.mkv"))
    plan = OperationPlanningService().plan((source,), selections, output)
    document = plan_document(plan)
    assert set(document) == {
        "output_format_tags",
        "plan_version",
        "revision",
        "acknowledged_revision",
        "sources",
        "output",
        "selections",
        "external_tracks",
        "included",
        "excluded",
        "preserve_chapters",
        "chapter_input_index",
        "preservation",
        "issues",
        "intrinsically_valid",
        "acknowledged_warnings",
        "pending_warnings",
        "execution_allowed",
        "confirmation_required",
        "arguments",
    }
    assert document["included"] == [
        {
            "reference": {
                "source": {
                    "path": str(source.source.path),
                    "size_bytes": source.source.size_bytes,
                    "modified_time_ns": source.source.modified_time_ns,
                },
                "index": 5,
            },
            "input_index": 0,
            "output_index": 0,
            "kind": "video",
            "source_codec": "h264",
            "target_codec": "h264",
            "action": "copy",
            "output_tags": {},
            "output_disposition": {"default": 0, "forced": 0},
        }
    ]
    assert document["plan_version"] == 2 and document["confirmation_required"] is True
    assert json.loads(serialize_plan(plan)) == document
    assert serialize_plan(plan) == serialize_plan(
        OperationPlanningService().plan((source,), selections, output)
    )
    assert plan.arguments is not None
    assert "-n" in plan.arguments and "-y" not in plan.arguments
    assert plan.arguments[plan.arguments.index("-c:0") + 1] == "copy"
    assert plan.arguments[plan.arguments.index("-map_metadata:s") + 1] == "-1"
    with pytest.raises(FrozenInstanceError):
        plan.__setattr__("plan_version", 2)
    blocked = (
        replace(plan, issues=(replace(plan.issues[0], severity="error"),))
        if plan.issues
        else replace(plan, acknowledged_warnings=frozenset())
    )
    # Command generation independently rejects an invalid or unacknowledged plan.
    invalid = OperationPlanningService().plan((source,), (), output)
    with pytest.raises(ValueError):
        build_arguments(invalid)
    assert blocked.plan_version == 2


def test_complete_documented_example_is_stable_contract(tmp_path: Path) -> None:
    text = (Path(__file__).resolve().parents[2] / "docs/14-OPERATION-PLAN-CONTRACT.md").read_text(
        encoding="utf-8"
    )
    expected = json.loads(text.split("```json\n", 1)[1].split("```", 1)[0])
    source = asset(tmp_path, [stream(5, "video", "h264")])
    plan = OperationPlanningService().plan(
        (source,), (select(source, 5),), OutputProfile("mkv", str(tmp_path / "out.mkv"))
    )
    source_data = {
        "path": str(source.source.path),
        "size_bytes": source.source.size_bytes,
        "modified_time_ns": source.source.modified_time_ns,
    }
    expected["sources"][0]["source"] = source_data
    expected["sources"][0]["format"]["name"] = "synthetic"
    expected["selections"][0]["reference"]["source"] = source_data
    expected["included"][0]["reference"]["source"] = source_data
    for decision in expected["preservation"]:
        if decision["reference"] is not None:
            decision["reference"]["source"] = source_data
    expected["output"]["path"] = str(plan.destination_path)
    expected["output"]["requested_path"] = plan.output.path
    expected["revision"] = plan.revision
    expected["arguments"] = [
        arg.replace("/examples/source.mkv", str(source.source.path)).replace(
            "/examples/output.mkv", str(plan.destination_path)
        )
        for arg in expected["arguments"]
    ]
    assert plan_document(plan) == expected

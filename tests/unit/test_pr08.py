"""Independent evidence failures, metadata semantics and replacement recovery."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_desktop_controller import model as model
from test_desktop_controller import settle
from test_planning import asset, select, stream

from mediatrack_forge.application.extraction import ExtractionPlanningService
from mediatrack_forge.application.inspection import InvalidInputError
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.planning import MetadataIntent, OutputProfile, StreamReference
from mediatrack_forge.domain.subtitles import SubtitleCue
from mediatrack_forge.infrastructure.extraction_validation import ExtractionValidator
from mediatrack_forge.infrastructure.output_validation import FFprobeOutputValidator
from mediatrack_forge.ui.presentation_model import DesktopBackend, DesktopController
from mediatrack_forge.ui.worker import WorkerReply


@pytest.mark.parametrize("failure", ["text", "timing", "count", "structure", "scan"])
def test_subtitle_independent_invariant_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source = asset(tmp_path, [stream(5, "subtitle", "subrip")])
    source = replace(source, format=replace(source.format, name="matroska"))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 5), str(tmp_path / "out.srt")
    )
    output = tmp_path / "staged.part"
    output.write_text(
        "invalid" if failure == "structure" else "1\n00:00:00,100 --> 00:00:00,200\nText\n",
        encoding="utf-8",
    )
    inspector = Mock()
    inspector.inspect.return_value = replace(source, format=replace(source.format, name="srt"))
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.packet_count", Mock(return_value=1)
    )
    cue = SubtitleCue(100, 200, "Changed" if failure == "text" else "Text")
    if failure == "timing":
        cue = replace(cue, end_ms=500)
    scanner = Mock(return_value=() if failure == "count" else (cue,))
    if failure == "scan":
        scanner.side_effect = ValueError
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.subtitle_cues", scanner
    )
    report = ExtractionValidator().validate(plan, output, inspector, 30)
    expected = {
        "text": "TEXT",
        "timing": "TIMING",
        "count": "CUE_COUNT",
        "structure": "STRUCTURE",
        "scan": "SOURCE_SCAN",
    }[failure]
    assert not report.passed
    assert any(c.status == "error" and c.code.endswith(expected) for c in report.checks)


def test_metadata_preserves_unrelated_and_blocks_changed_output(tmp_path: Path) -> None:
    source = asset(
        tmp_path,
        [
            stream(0, "video", "h264")
            | {"tags": {"title": "Original", "comment": "Keep", "PrivateUnknown": "Unverified"}}
        ],
    )
    source = replace(
        source, format=replace(source.format, name="matroska", tags=(("title", "Container"),))
    )
    plan = OperationPlanningService().plan(
        (source,),
        (select(source, 0, metadata=MetadataIntent(title="")),),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
    )
    assert plan.plan_version == 2
    assert dict(plan.output_format_tags) == {"title": "Container"}
    assert dict(plan.included[0].output_tags) == {"title": "", "comment": "Keep"}
    assert any("PrivateUnknown" in i.message for i in plan.issues)
    output = tmp_path / "staged.part"
    output.write_bytes(b"staged")
    inspector = Mock()
    inspector.inspect.return_value = replace(
        source, format=replace(source.format, tags=(("title", "Lost"),))
    )
    report = FFprobeOutputValidator().validate(plan, output, inspector, 30)
    assert any(c.code == "FORMAT_METADATA" and c.status == "error" for c in report.checks)


def test_failed_replacement_retains_exact_intent_and_rejects_stale_result(
    model: DesktopController,
) -> None:
    reference = model.intent.selections[1].reference
    model.edit_track(reference, include=False, metadata=MetadataIntent(title="Pending"))
    before = model.intent
    backend = Mock(spec=DesktopBackend)
    backend.inspect.side_effect = InvalidInputError("Choose a readable file.")
    model.backend = backend
    model.open_media("unavailable")
    settle(model)
    assert model.intent == before and model.error and model.plan is None
    model.apply(WorkerReply(model.generation - 1, "inspect", before.sources[0]))
    assert model.intent == before

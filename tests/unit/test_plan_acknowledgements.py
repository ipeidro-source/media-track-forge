"""A reviewed revision cannot acknowledge different intent or diagnostic occurrences."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_planning import asset, select, stream

from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.planning import (
    CompatibilityIssue,
    ExternalTrack,
    MetadataIntent,
    OperationPlan,
    OutputProfile,
    StreamReference,
)
from mediatrack_forge.infrastructure.ffmpeg_arguments import build_arguments
from mediatrack_forge.ui.operation_plan_json import plan_document


def review(plan: OperationPlan, *, revision: str | None = None) -> OperationPlan:
    return OperationPlanningService().plan(
        plan.sources,
        plan.selections,
        plan.output,
        external_tracks=plan.external_tracks,
        preserve_chapters=plan.preserve_chapters,
        acknowledged_warnings=frozenset(plan.pending_warnings),
        acknowledged_revision=revision,
    )


@pytest.fixture
def base(tmp_path: Path) -> OperationPlan:
    source = asset(
        tmp_path,
        [stream(0, "video", "h264"), stream(2, "video", "hevc"), stream(3, "audio", "aac")],
    )
    # A constant warning category present for both MKV and MP4.
    source = replace(source, format=replace(source.format, tags=(("comment", "original"),)))
    return OperationPlanningService().plan(
        (source,),
        tuple(select(source, i) for i in (0, 2, 3)),
        OutputProfile("mkv", str(tmp_path / "out.mkv")),
    )


def test_codes_alone_do_not_acknowledge(base: OperationPlan) -> None:
    assert base.pending_warnings
    result = review(base)
    assert result.intrinsically_valid and result.pending_warnings == base.pending_warnings
    assert result.arguments is None and not result.execution_allowed
    with pytest.raises(ValueError):
        build_arguments(result)


def test_exact_revision_acknowledgement_does_not_change_revision(base: OperationPlan) -> None:
    result = review(base, revision=base.revision)
    assert result.revision == base.revision
    assert result.execution_allowed and not result.pending_warnings
    assert result.confirmation_required  # Final confirmation is still separate.
    assert review(base, revision=base.revision) == result
    assert len(result.revision) == 64


@pytest.mark.parametrize(
    "change",
    [
        "sources",
        "selection",
        "ordering",
        "metadata",
        "destination",
        "container",
        "chapters",
        "external",
    ],
)
def test_same_warning_codes_cannot_transfer_to_changed_intent(
    base: OperationPlan,
    change: str,
    tmp_path: Path,
) -> None:
    sources = base.sources
    selections = base.selections
    output = base.output
    preserve_chapters = base.preserve_chapters
    external: tuple[ExternalTrack, ...] = ()
    if change == "sources":
        original = sources[0]
        replacement = asset(
            tmp_path,
            [stream(0, "video", "h264"), stream(2, "video", "hevc"), stream(3, "audio", "aac")],
            name="other.mkv",
        )
        replacement = replace(replacement, format=original.format)
        sources = (replacement,)
        selections = tuple(
            replace(item, reference=StreamReference(replacement.source, item.reference.index))
            for item in selections
        )
    elif change == "selection":
        selections = (*selections[:2], replace(selections[2], include=False))
    elif change == "ordering":
        selections = (selections[1], selections[0], selections[2])
    elif change == "metadata":
        selections = (
            replace(selections[0], metadata=MetadataIntent(title="changed")),
            *selections[1:],
        )
    elif change == "destination":
        output = OutputProfile("mkv", str(tmp_path / "other.mkv"))
    elif change == "container":
        # Clear effective metadata flags on a separate base so MP4 adds no warnings;
        # both changed/base plans still have the same global-tag warning.
        sources = (
            replace(
                sources[0], streams=tuple(replace(s, disposition=()) for s in sources[0].streams)
            ),
        )
        base = OperationPlanningService().plan(sources, selections, output)
        # MP4 adds a metadata uncertainty only if output tags/flags are present.
        output = OutputProfile("mp4", str(tmp_path / "out.mp4"))
    elif change == "chapters":
        preserve_chapters = False
    elif change == "external":
        original = sources[0]
        external = (
            ExternalTrack(original.source, "audio", 3, "aac", original.format.name, validated=True),
        )
    changed = OperationPlanningService().plan(
        sources,
        selections,
        output,
        external_tracks=external,
        preserve_chapters=preserve_chapters,
        acknowledged_warnings=frozenset(base.pending_warnings),
        acknowledged_revision=base.revision,
    )
    assert changed.intrinsically_valid
    assert {i.code for i in changed.issues} == {i.code for i in base.issues}
    assert changed.revision != base.revision
    assert changed.pending_warnings and changed.arguments is None and not changed.execution_allowed
    assert plan_document(changed)["acknowledged_warnings"] == []
    with pytest.raises(ValueError):
        build_arguments(changed)
    assert review(changed, revision=changed.revision).execution_allowed


@pytest.mark.parametrize(
    "change", ["message", "severity", "suggestion", "reference", "multiplicity"]
)
def test_diagnostic_details_and_occurrences_invalidate_acknowledgement(
    base: OperationPlan,
    change: str,
) -> None:
    accepted = review(base, revision=base.revision)
    issue = base.issues[0]
    if change == "message":
        issue = replace(issue, message="Different content is lost.")
    elif change == "severity":
        issue = replace(issue, severity="error")
    elif change == "suggestion":
        issue = replace(issue, suggestion="Review the updated plan.")
    elif change == "reference":
        issue = replace(issue, reference=base.selections[0].reference)
    issues = (issue, issue) if change == "multiplicity" else (issue,)
    changed = replace(accepted, issues=issues)
    assert changed.revision != accepted.revision
    assert not changed.effective_acknowledged_warnings
    assert not changed.execution_allowed
    assert changed.arguments is None
    with pytest.raises(ValueError):
        build_arguments(changed)


def test_blockers_cannot_be_acknowledged_into_validity(base: OperationPlan) -> None:
    blocked = replace(
        base, issues=(*base.issues, CompatibilityIssue("BLOCKED", "error", "Blocked."))
    )
    accepted = replace(
        blocked,
        acknowledged_revision=blocked.revision,
        acknowledged_warnings=frozenset(i.code for i in blocked.issues),
    )
    assert not accepted.intrinsically_valid and not accepted.pending_warnings
    assert accepted.arguments is None and not accepted.execution_allowed
    with pytest.raises(ValueError):
        build_arguments(accepted)


def test_partial_acknowledgement_still_has_no_arguments(base: OperationPlan) -> None:
    changed = replace(
        base,
        issues=(
            *base.issues,
            CompatibilityIssue("SECOND_WARNING", "warning", "Review additional loss."),
        ),
    )
    partial = replace(
        changed,
        acknowledged_revision=changed.revision,
        acknowledged_warnings=frozenset(base.pending_warnings),
    )
    assert partial.intrinsically_valid
    assert partial.pending_warnings == ("SECOND_WARNING",)
    assert partial.arguments is None and not partial.execution_allowed
    assert partial.confirmation_required

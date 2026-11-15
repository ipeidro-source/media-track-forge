"""Authorization races and navigation are tested without a display or media fakes as evidence."""

import threading
from dataclasses import replace
from pathlib import Path
from typing import Literal
from unittest.mock import Mock

import pytest
from test_desktop_controller import model, settle

from mediatrack_forge.domain.execution import ExecutionResult
from mediatrack_forge.ui.languages import LANGUAGES, language_choices
from mediatrack_forge.ui.presentation_model import DesktopController, EditingIntent
from mediatrack_forge.ui.wizard import Step, WizardState
from mediatrack_forge.ui.worker import WorkerReply

__all__ = ["model"]


def review(model: DesktopController) -> None:
    model.edit_track(model.intent.selections[-1].reference, include=False)
    model.generate_plan()
    settle(model)
    assert model.plan and model.plan.intrinsically_valid and model.plan.pending_warnings


def test_sequential_navigation_and_no_execution_backdoor() -> None:
    wizard = WizardState()
    with pytest.raises(ValueError):
        wizard.next(inspected=False, busy=False)
    with pytest.raises(ValueError):
        wizard.review(busy=False)
    wizard.next(inspected=True, busy=False)
    assert wizard.step == Step.METADATA
    wizard.next(inspected=True, busy=False)
    wizard.review(busy=False)
    assert int(wizard.step) == Step.REVIEW
    with pytest.raises(ValueError):
        wizard.back(busy=True, recovery_required=False)
    wizard.back(busy=False, recovery_required=False)
    assert int(wizard.step) == Step.OPERATION
    wizard.executing()
    with pytest.raises(ValueError):
        wizard.back(busy=False, recovery_required=False)
    with pytest.raises(ValueError):
        wizard.reset(safe=False)
    wizard.reset(safe=True)
    assert int(wizard.step) == Step.MEDIA


def test_warning_decision_acknowledges_exact_revision_then_confirms_once(
    model: DesktopController,
) -> None:
    review(model)
    assert model.plan
    reviewed = model.plan
    regenerate = model.backend.plan
    acknowledgement = Mock(wraps=regenerate)
    executed = Mock(return_value=ExecutionResult("completed", (), ()))
    model.backend.plan = acknowledgement  # type: ignore[method-assign]
    model.backend.execute = executed  # type: ignore[method-assign]
    assert model.can_authorize and not model.can_execute
    assert not executed.called  # Displaying Review is never authorization.
    model.accept_and_execute()
    with pytest.raises(ValueError):
        model.accept_and_execute()
    settle(model)
    acknowledgement.assert_called_once_with(
        model.intent, codes=frozenset(reviewed.pending_warnings), revision=reviewed.revision
    )
    executed.assert_called_once()
    request = executed.call_args.args[0]
    assert request.reviewed_revision == request.confirmed_revision == reviewed.revision
    assert request.plan.issues == reviewed.issues
    assert not request.plan.pending_warnings
    assert not model.can_authorize


def test_warning_free_explicit_decision_still_confirms_revision(model: DesktopController) -> None:
    review(model)
    assert model.plan
    model.acknowledge(frozenset(model.plan.pending_warnings), model.plan.revision)
    settle(model)
    execute = Mock(return_value=ExecutionResult("failed", (), ()))
    model.backend.execute = execute  # type: ignore[method-assign]
    assert model.plan and not model.plan.pending_warnings
    revision = model.plan.revision
    assert not execute.called
    model.accept_and_execute()
    settle(model)
    assert execute.call_args.args[0].confirmed_revision == revision


@pytest.mark.parametrize("change", ["revision", "warnings", "rejected", "exception"])
def test_changed_or_rejected_acknowledgement_never_executes(
    model: DesktopController,
    change: str,
) -> None:
    review(model)
    original = model.backend.plan
    execute = Mock()
    model.backend.execute = execute  # type: ignore[method-assign]

    def altered(intent: EditingIntent, **kwargs: object) -> object:
        if change == "exception":
            raise RuntimeError("Private uncontrolled error")
        plan = (
            original(
                intent, codes=frozenset(model.plan.pending_warnings), revision=model.plan.revision
            )
            if model.plan
            else None
        )
        assert plan
        if change == "revision":
            return replace(plan, preserve_chapters=not plan.preserve_chapters)
        if change == "warnings":
            return replace(plan, issues=plan.issues + (plan.issues[0],))
        return replace(plan, acknowledged_warnings=frozenset())

    model.backend.plan = altered  # type: ignore[method-assign, assignment]
    model.accept_and_execute()
    settle(model)
    assert not execute.called and model.error
    assert "Private" not in model.error


def test_intent_generation_change_and_unrelated_reply_never_autostart(
    model: DesktopController,
) -> None:
    review(model)
    original = model.backend.plan
    release = threading.Event()
    execute = Mock()
    model.backend.execute = execute  # type: ignore[method-assign]

    def wait_plan(intent: EditingIntent, *, codes: frozenset[str], revision: str | None) -> object:
        assert release.wait(3)
        return original(intent, codes=codes, revision=revision)

    model.backend.plan = wait_plan  # type: ignore[method-assign, assignment]
    model.accept_and_execute()
    model.invalidate()  # Models superseding a captured view while a reply is outstanding.
    release.set()
    settle(model)
    assert not execute.called and model.plan is None
    model.apply(WorkerReply(model.generation, "destination", ""))
    assert not execute.called


def test_cancel_during_acknowledgement_revokes_the_execution_decision(
    model: DesktopController,
) -> None:
    review(model)
    original = model.backend.plan
    release = threading.Event()
    executed = Mock()
    model.backend.execute = executed  # type: ignore[method-assign]

    def waiting(intent: EditingIntent, *, codes: frozenset[str], revision: str | None) -> object:
        assert release.wait(3)
        return original(intent, codes=codes, revision=revision)

    model.backend.plan = waiting  # type: ignore[method-assign, assignment]
    model.accept_and_execute()
    assert not model.request_close(True)
    release.set()
    settle(model)
    assert not executed.called and model.safe_to_close


@pytest.mark.parametrize("state", ["completed", "cancelled", "failed"])
def test_reset_requires_safe_result_and_keeps_media(
    model: DesktopController,
    state: Literal["completed", "cancelled", "failed"],
    tmp_path: Path,
) -> None:
    published = tmp_path / "published.mkv"
    published.write_bytes(b"Retain this output")
    sources = tuple(a.source.path for a in model.intent.sources)
    with pytest.raises(ValueError):
        model.start_over()
    model.result = ExecutionResult(
        state, (), (), destination=published, published=True, cleanup_complete=False
    )
    model.recovery_required = True
    with pytest.raises(ValueError):
        model.start_over()
    model.recovery_required = False
    model.result = replace(model.result, cleanup_complete=True)
    generation = model.generation
    model.start_over()
    assert model.intent == EditingIntent() and model.generation > generation
    assert model.plan is None and model.result is None and model.progress is None
    assert model.reviewed_revision is None and model.confirmed_revision is None
    assert published.read_bytes() == b"Retain this output" and all(p.exists() for p in sources)
    model.apply(WorkerReply(generation, "inspect", object()))
    assert not model.intent.sources


def test_catalog_search_and_preservation_do_not_rewrite_original_codes() -> None:
    assert len(LANGUAGES) > 70
    assert language_choices("japan", "ger") == [("jpn", "Japanese (jpn)")]
    assert ("", "Unspecified") in language_choices("", "ger")
    assert ("ger", "Preserve original code (ger)") in language_choices("", "ger")
    assert ("zzz", "Preserve original code (zzz)") in language_choices("zzz", "zzz")
    assert all(not code or len(code) == 3 and code.islower() for code in LANGUAGES)

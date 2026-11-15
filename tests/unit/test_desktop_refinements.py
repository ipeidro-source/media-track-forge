"""Review and early destination feedback preserve backend authority and user intent."""

from pathlib import Path

import pytest
from test_desktop_controller import model as model
from test_desktop_controller import settle

from mediatrack_forge.domain.planning import MetadataIntent
from mediatrack_forge.ui.display import clock_text, review_summary, size_text
from mediatrack_forge.ui.presentation_model import DesktopBackend, DesktopController, EditingIntent


def test_review_is_changed_values_and_final_order_without_technical_authority(
    model: DesktopController,
) -> None:
    reference = model.intent.selections[1].reference
    model.edit_track(reference, metadata=MetadataIntent(title="Main", language="spa"))
    model.edit_track(model.intent.selections[-1].reference, include=False)
    model.generate_plan()
    settle(model)
    assert model.plan is not None
    text = review_summary(model.plan)
    assert "Requires acknowledgement" in text
    assert "Spanish (spa)" in text and "Main" in text
    assert text.index("Source") < text.index("Changes") < text.index("Destination")
    assert "MetadataIntent(" not in text and model.plan.revision not in text
    assert "original index 8" in text and "Exclude data" in text


@pytest.mark.parametrize("value", [None, float("nan"), -1])
def test_unknown_timing_never_fabricates_clock(value: float | None) -> None:
    assert clock_text(value) == "Unknown"


def test_human_units_and_long_media_time() -> None:
    assert clock_text(3661.99) == "01:01:01"
    assert size_text(1024 * 1024) == "1.0 MiB"


def test_destination_feedback_and_free_name_do_not_write(tmp_path: Path) -> None:
    path = tmp_path / "output.mkv"
    intent = EditingIntent(destination=str(path))
    assert DesktopBackend.destination_feedback(intent, "mkv") == ""
    assert not path.exists()
    path.write_bytes(b"original destination")
    assert "exists" in DesktopBackend.destination_feedback(intent, "mkv")
    suggestion = DesktopBackend.suggest_destination(intent, "output.mkv")
    assert Path(suggestion) != path and not Path(suggestion).exists()
    assert path.read_bytes() == b"original destination"
    assert "extension" in DesktopBackend.destination_feedback(intent, "mp4")
    assert DesktopBackend.destination_feedback(
        EditingIntent(destination="https://invalid/output.mkv"), "mkv"
    )

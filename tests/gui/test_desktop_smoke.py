"""Run each native GUI case in a fresh process, matching the single-root application."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "case",
    [
        "test_native_window_track_identity_metadata_review_and_cancel",
        "test_native_review_invalidated_by_unapplied_metadata_and_destination",
        "test_native_close_waits_for_safe_cancellation",
        "test_real_gui_to_backend_video_only_remux",
        "test_native_theme_scaling_and_resize[Light-1.0]",
        "test_native_theme_scaling_and_resize[Dark-1.25]",
        "test_native_theme_scaling_and_resize[Light-1.5]",
        "test_native_failure_preserves_published_cleanup_evidence",
        "test_refined_metadata_extraction_destination_and_recovery",
        "test_refined_progress_repeated_execution_and_variable_teardown",
        "test_refined_external_subtitle_group_and_duplicate_feedback",
    ],
)
def test_native_desktop_smoke(case: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"tests/gui/scenarios.py::{case}",
            "-v",
            "-s",
            "-W",
            "error",
        ],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
    print(result.stdout.decode("utf-8", errors="replace"))
    assert not result.stderr.strip(), result.stderr.decode("utf-8", errors="replace")

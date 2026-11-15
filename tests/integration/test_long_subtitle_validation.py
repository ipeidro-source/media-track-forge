"""Local two-hour subtitle evidence; controlled timeout injection is not SMB evidence."""

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from mediatrack_forge.application.control import CancellationToken
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import InspectionService, ProbeTimeoutError
from mediatrack_forge.domain.execution import ExecutionRequest, ProcessConfiguration
from mediatrack_forge.domain.planning import StreamReference
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter, run_bounded
from mediatrack_forge.infrastructure.srt import validate_srt

from .conftest import AUDIO, VIDEO, generate
from .test_planning_mux import planning_tools as planning_tools
from .test_pr05_e2e import digest


def timestamp(milliseconds: int) -> str:
    seconds, ms = divmod(milliseconds, 1000)
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02},{ms:03}"


@pytest.mark.integration
@pytest.mark.parametrize("failed_side", [None, "source", "output", "timing", "cancel"])
def test_two_hour_subrip_validation_and_failure_publication_boundary(
    tmp_path: Path,
    planning_tools: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    failed_side: str | None,
) -> None:
    cues = 2400
    subtitle = tmp_path / "synthetic.srt"
    subtitle.write_text(
        "\n\n".join(
            f"{n + 1}\n{timestamp(n * 3000)} --> {timestamp(n * 3000 + 1800)}\n"
            f"Synthetic caption {n + 1}"
            for n in range(cues)
        )
        + "\n",
        encoding="utf-8",
    )
    source = tmp_path / "two-hour-subtitles.mkv"
    generate(
        planning_tools[0],
        [
            *VIDEO,
            *AUDIO,
            "-i",
            str(subtitle),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *[arg for _ in range(4) for arg in ("-map", "2:s:0")],
            "-c:v",
            "libx265",
            "-threads",
            "1",
            "-x265-params",
            "pools=1:frame-threads=1:log-level=error:bframes="
            + ("4" if failed_side == "timing" else "0"),
            "-c:a",
            "eac3",
            # Keep encoder priming away from zero across FFmpeg versions, so the
            # video/subtitle clock, rather than unselected audio delay, sets origin.
            "-af",
            "asetpts=PTS+1/TB",
            "-c:s",
            "srt",
            "-avoid_negative_ts",
            "disabled",
            *(["-output_ts_offset", "1"] if failed_side == "timing" else []),
        ],
        source,
    )
    inspector = InspectionService(FFprobeAdapter(planning_tools[1]))
    asset = inspector.inspect(source)
    origin = json.loads(
        run_bounded(
            [
                planning_tools[1],
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-show_entries",
                "format=start_time",
                "-of",
                "json",
                "-i",
                str(source),
            ],
            30,
        )
    )["format"]["start_time"]
    assert float(origin) == (1 if failed_side == "timing" else 0)
    assert [s.codec for s in asset.streams] == [
        "hevc",
        "eac3",
        "subrip",
        "subrip",
        "subrip",
        "subrip",
    ]
    assert asset.format.duration_seconds is not None and asset.format.duration_seconds > 7198
    assert source.stat().st_size < 2 * 1024 * 1024
    original = digest(source)
    output = tmp_path / "extracted.srt"
    reference = StreamReference(asset.source, 5)
    planner = ExtractionPlanningService()
    plan = planner.plan(asset, reference, str(output))
    plan = planner.plan(
        asset,
        reference,
        str(output),
        acknowledged_warnings=frozenset(plan.pending_warnings),
        acknowledged_revision=plan.revision,
    )
    limits: list[float] = []

    def limited_probe(
        arguments: list[str], timeout: float, *, cancellation: CancellationToken | None = None
    ) -> bytes:
        limits.append(timeout)
        is_source = arguments[-1] == str(source)
        if is_source and failed_side == "cancel":
            assert cancellation is not None
            timer = threading.Timer(0.2, cancellation.cancel)
            timer.start()
            try:
                return run_bounded(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    timeout,
                    cancellation=cancellation,
                )
            finally:
                timer.cancel()
                timer.join()
        # Controlled cost model, not real network latency: the legacy 30-second
        # budget cannot finish this source scan; complete native probing still runs.
        if (is_source and timeout < 45) or (
            failed_side in ("source", "output") and is_source == (failed_side == "source")
        ):
            raise ProbeTimeoutError("private vendor or filesystem message")
        return run_bounded(arguments, timeout, cancellation=cancellation)

    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.run_bounded", limited_probe
    )
    result = ExtractionExecutionService().execute(
        ExecutionRequest(
            plan,
            plan.revision,
            plan.revision,
            ProcessConfiguration(ffmpeg=planning_tools[0], ffprobe=planning_tools[1]),
        )
    )
    assert digest(source) == original and result.cleanup_complete
    assert not list(tmp_path.glob(".mediatrack-*"))
    assert limits and all(limit == 300 for limit in limits)
    if failed_side == "cancel":
        assert result.state == "cancelled" and not result.published and not output.exists()
        return
    assert result.validation is not None
    if failed_side == "timing":
        # Reordered HEVC packets shift the MKV clock origin; FFmpeg extraction rebases it.
        # This is a distinct later validation failure, not a packet-count/SMB failure.
        assert not result.published and not output.exists()
        assert any(c.code == "EXTRACTION_SUBTITLE_TIMING" for c in result.validation.checks)
        assert all(c.status == "passed" for c in result.validation.checks[:2])
    elif failed_side:
        assert not result.published and not output.exists()
        assert any(
            c.code == f"EXTRACTION_{failed_side.upper()}_PACKET_SCAN_TIMEOUT"
            for c in result.validation.checks
        )
        assert "private" not in str(result.validation.checks)
    else:
        assert result.published, [(c.code, c.detail) for c in result.validation.checks]
        assert len(validate_srt(output)) == cues
        command = [
            sys.executable,
            "scripts/diagnose_extraction_packets.py",
            "--source",
            str(source),
            "--stream-index",
            "5",
            "--output",
            str(output),
            "--ffprobe",
            planning_tools[1],
        ]
        diagnosed = subprocess.run(command, capture_output=True, check=True, timeout=75)
        assert not diagnosed.stderr
        data = json.loads(diagnosed.stdout)
        assert [r["packet_count"] for r in data["results"]] == [cues, cues]
        assert all(r["status"] == "passed" for r in data["results"])
        assert (
            str(source).encode() not in diagnosed.stdout
            and b"Synthetic caption" not in diagnosed.stdout
        )

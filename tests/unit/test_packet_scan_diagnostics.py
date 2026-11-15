"""Packet scans identify the operation and failure without exposing private tool output."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_planning import asset, stream

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import (
    ExecutableError,
    ProbeFailedError,
    ProbeOutputLimitError,
    ProbeTimeoutError,
)
from mediatrack_forge.domain.execution import ExecutionRequest, ProcessConfiguration
from mediatrack_forge.domain.planning import StreamReference
from mediatrack_forge.domain.subtitles import SubtitleCue
from mediatrack_forge.infrastructure.extraction_validation import ExtractionValidator, packet_count
from mediatrack_forge.infrastructure.packet_probe import PacketScanError
from scripts.diagnose_extraction_packets import main


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"not JSON", "JSON_INVALID"),
        (b"\xff", "JSON_INVALID"),
        (b"[]", "STREAM_LAYOUT"),
        (b'{"streams":[]}', "STREAM_LAYOUT"),
        (b'{"streams":[1]}', "STREAM_LAYOUT"),
        (b'{"streams":[{}]}', "COUNT_UNAVAILABLE"),
        (b'{"streams":[{"nb_read_packets":"N/A"}]}', "COUNT_UNAVAILABLE"),
        (b'{"streams":[{"nb_read_packets":true}]}', "COUNT_INVALID"),
        (b'{"streams":[{"nb_read_packets":"-1"}]}', "COUNT_INVALID"),
        (b'{"streams":[{"nb_read_packets":"0"}]}', "COUNT_EMPTY"),
    ],
)
def test_packet_count_rejects_invalid_evidence(
    monkeypatch: pytest.MonkeyPatch, raw: bytes, code: str
) -> None:
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.shutil.which",
        lambda _: sys.executable,
    )
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.run_bounded", Mock(return_value=raw)
    )
    with pytest.raises(PacketScanError) as failure:
        packet_count(Path("synthetic.mkv"), 5, None, 30)
    assert failure.value.code == code


@pytest.mark.parametrize(
    "error,code",
    [
        (ProbeTimeoutError("private source details"), "TIMEOUT"),
        (ProbeOutputLimitError("stdout"), "STDOUT_LIMIT"),
        (ProbeOutputLimitError("stderr"), "STDERR_LIMIT"),
        (ExecutableError("private executable path"), "EXECUTABLE"),
        (ProbeFailedError("private vendor log and subtitle text"), "PROBE_FAILED"),
        (OSError("private network path"), "IO"),
    ],
)
def test_packet_count_classifies_probe_failures(
    monkeypatch: pytest.MonkeyPatch, error: Exception, code: str
) -> None:
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.shutil.which",
        lambda _: sys.executable,
    )
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.run_bounded", Mock(side_effect=error)
    )
    with pytest.raises(PacketScanError) as failure:
        packet_count(Path("synthetic.mkv"), 5, None, 30)
    assert failure.value.code == code and "private" not in failure.value.detail


@pytest.mark.parametrize("role", ["SOURCE", "OUTPUT"])
def test_validator_distinguishes_failed_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    source = asset(tmp_path, [stream(5, "subtitle", "subrip")])
    source = replace(source, format=replace(source.format, name="matroska"))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 5), str(tmp_path / "out.srt")
    )
    output = tmp_path / "staged.part"
    output.write_bytes(b"synthetic staged file")
    actual = replace(
        source,
        format=replace(source.format, name="srt"),
        streams=(replace(source.streams[0], index=0),),
    )
    inspector = Mock()
    inspector.inspect.return_value = actual
    failure = PacketScanError("TIMEOUT", "Full scan exceeded its limit.")
    count = Mock(side_effect=[failure] if role == "SOURCE" else [2160, failure])
    monkeypatch.setattr("mediatrack_forge.infrastructure.extraction_validation.packet_count", count)
    report = ExtractionValidator().validate(plan, output, inspector, 30)
    assert not report.passed
    assert any(c.code == f"EXTRACTION_{role}_PACKET_SCAN_TIMEOUT" for c in report.checks)
    assert count.call_args_list[0].args[:2] == (source.source.path, 5)
    assert count.call_count == (1 if role == "SOURCE" else 2)
    if role == "OUTPUT":
        assert count.call_args_list[1].args[:2] == (output, 0)
        assert report.checks[0].code == "EXTRACTION_SOURCE_PACKET_SCAN"


def test_unc_command_keeps_original_path_and_index_without_protocols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Command construction only: no network request or SMB verification.
    path = Path(r"\\server\share\trusted fixture.mkv")
    runner = Mock(return_value=b'{"streams":[{"nb_read_packets":"2160"}]}')
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.shutil.which",
        lambda _: sys.executable,
    )
    monkeypatch.setattr("mediatrack_forge.infrastructure.extraction_validation.run_bounded", runner)
    assert packet_count(path, 5, None, 30) == 2160
    args, timeout = runner.call_args.args
    assert args[-2:] == ["-i", str(path)] and timeout == 30
    assert args[args.index("-select_streams") + 1] == "5"
    assert args[args.index("-protocol_whitelist") + 1] == "file"
    assert "-show_data" not in args and "-show_packets" not in args


def test_scan_budget_is_separate_from_metadata_and_bound_to_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = asset(tmp_path, [stream(5, "subtitle", "subrip")])
    source = replace(source, format=replace(source.format, name="matroska"))
    plan = ExtractionPlanningService().plan(
        source, StreamReference(source.source, 5), str(tmp_path / "out.srt")
    )
    config = ProcessConfiguration(packet_scan_timeout_seconds=123)
    control = ExecutionControl()
    validator = ExtractionExecutionService()._validator_for(
        ExecutionRequest(plan, plan.revision, plan.revision, config), control
    )
    output = tmp_path / "staged.part"
    output.write_text("1\n00:00:00,100 --> 00:00:00,200\nText\n", encoding="utf-8")
    inspector = Mock()
    inspector.inspect.return_value = replace(
        source,
        format=replace(source.format, name="srt"),
        streams=(replace(source.streams[0], index=0),),
    )
    counts = Mock(return_value=1)
    cues = Mock(return_value=(SubtitleCue(100, 200, "Text"),))
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.extraction_validation.packet_count", counts
    )
    monkeypatch.setattr("mediatrack_forge.infrastructure.extraction_validation.subtitle_cues", cues)
    assert validator.validate(plan, output, inspector, config.probe_timeout_seconds).passed
    assert inspector.inspect.call_args.kwargs["timeout_seconds"] == 30
    assert all(
        call.args[-1] == 123 and call.kwargs["cancellation"] is control.cancellation
        for call in counts.call_args_list
    )
    assert (
        cues.call_args.args[-1] == 123
        and cues.call_args.kwargs["cancellation"] is control.cancellation
    )


def test_read_only_diagnostic_output_has_no_paths_or_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "private-source.mkv"
    source.write_bytes(b"private contents")
    monkeypatch.setattr(
        "scripts.diagnose_extraction_packets.packet_count",
        Mock(side_effect=PacketScanError("TIMEOUT", "Full scan exceeded its limit.")),
    )
    assert main(["--source", str(source), "--stream-index", "5"]) == 1
    text = capsys.readouterr().out
    assert "private" not in text and str(tmp_path) not in text
    result = json.loads(text)["results"][0]
    assert result["role"] == "source" and result["failure"] == "TIMEOUT"
    assert result["timeout_seconds"] == 30
    assert source.read_bytes() == b"private contents"


def test_invalid_cli_arguments_do_not_echo_private_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--source", "private-path", "--stream-index", "private-value"]) == 2
    assert (
        capsys.readouterr().out.strip() == '{"diagnostic_version":1,"failure":"INVALID_ARGUMENTS"}'
    )


@pytest.mark.parametrize("limit", ["nan", "inf", "-1", "0", "301"])
def test_diagnostic_rejects_unbounded_or_invalid_limits(
    limit: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["--source", "private-path", "--stream-index", "5", "--timeout-seconds", limit]) == 2
    )
    assert "private" not in capsys.readouterr().out

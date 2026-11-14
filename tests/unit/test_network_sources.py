"""Simulated Windows file-share regressions; these are not real SMB evidence."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any
from unittest.mock import Mock

import pytest

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.external_subtitles import ExternalSubtitleService
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import (
    InspectionService,
    InvalidInputError,
    ProbeFailedError,
    snapshot_source,
)
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import (
    ExecutionFailure,
    ExecutionRequest,
    ProcessOutcome,
    ValidationReport,
)
from mediatrack_forge.domain.planning import OutputProfile, StreamReference, TrackSelection
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.ffprobe_json import parse_response
from mediatrack_forge.infrastructure.planning_paths import destination_path
from mediatrack_forge.infrastructure.staging import PrivateStagingStore
from mediatrack_forge.infrastructure.windows_paths import require_local_volume


@pytest.fixture
def network_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> tuple[str, Path, Path]:
    variant = getattr(request, "param", "mkv")
    suffix = "mkv" if variant == "extended" else variant
    mapped = rf"Z:\Media\movie.{suffix}"
    canonical = Path(
        (
            "\\\\?\\UNC\\trusted-server\\media\\"
            if variant == "extended"
            else "\\\\trusted-server\\media\\"
        )
        + f"movie.{suffix}"
    )
    backing = tmp_path / "simulated-network-content"
    backing.write_bytes(
        b"1\n00:00:00,000 --> 00:00:00,300\nSynthetic\n"
        if suffix == "srt"
        else b"synthetic simulated share"
    )
    original_resolve, original_stat, original_open = Path.resolve, Path.stat, Path.open

    def resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if str(path) == mapped or path == canonical:
            return canonical
        return original_resolve(path, strict=bool(kwargs.get("strict", False)))

    def stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        return original_stat(
            backing if path == canonical or str(path) == mapped else path,
            follow_symlinks=follow_symlinks,
        )

    def open_file(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        if path == canonical or str(path) == mapped:
            assert mode == "rb", "Network sources must only be opened read-only"
            return original_open(backing, "rb")
        return original_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr("mediatrack_forge.application.inspection.os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(Path, "open", open_file)
    return mapped, canonical, backing


@pytest.mark.parametrize("network_file", ["srt"], indirect=True)
@pytest.mark.parametrize("direct", [False, True])
def test_external_srt_on_mapped_and_unc_sources(
    network_file: tuple[str, Path, Path], direct: bool
) -> None:
    mapped, canonical, backing = network_file
    inspector = Mock()
    response = json.dumps(
        {
            "format": {"format_name": "srt"},
            "streams": [{"index": 9, "codec_type": "subtitle", "codec_name": "subrip"}],
        }
    ).encode()
    inspector.inspect.side_effect = lambda path, **kwargs: parse_response(
        response, snapshot_source(path)
    )
    original = backing.read_bytes()
    asset, track = ExternalSubtitleService(inspector).import_srt(canonical if direct else mapped)
    assert asset.source.path == canonical and track.source == asset.source
    assert track.validated and track.stream_index == 9
    assert backing.read_bytes() == original


@pytest.mark.parametrize("network_file", ["mkv", "extended"], indirect=True)
def test_mapped_and_direct_unc_share_one_canonical_identity(
    network_file: tuple[str, Path, Path],
) -> None:
    mapped, canonical, backing = network_file
    first = snapshot_source(mapped)
    assert first == snapshot_source(canonical) == snapshot_source(mapped)
    assert first.path == canonical and first.size_bytes == backing.stat().st_size
    backing.write_bytes(b"changed synthetic share content")
    assert snapshot_source(mapped) != first


def test_unc_probe_keeps_file_protocol_and_original_indices(
    network_file: tuple[str, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    mapped, canonical, _ = network_file
    response = json.dumps(
        {
            "format": {"format_name": "matroska"},
            "streams": [
                {"index": 7, "codec_type": "video", "codec_name": "h264"},
                {"index": 19, "codec_type": "audio", "codec_name": "aac"},
            ],
        }
    ).encode()
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.ffprobe.shutil.which", lambda _: "ffprobe.exe"
    )
    run = Mock(return_value=response)
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.run_bounded", run)
    asset = InspectionService(FFprobeAdapter()).inspect(mapped)
    assert asset.source.path == canonical and [s.index for s in asset.streams] == [7, 19]
    args = run.call_args.args[0]
    assert args[-1] == str(canonical)
    assert args[args.index("-protocol_whitelist") + 1] == "file"


@pytest.mark.parametrize(
    "failure,expected",
    [
        (FileNotFoundError(), "Cannot find"),
        (PermissionError(), "access was denied"),
        (OSError(53, "untrusted vendor text"), "network connection"),
    ],
)
def test_network_input_failures_are_controlled(
    network_file: tuple[str, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError,
    expected: str,
) -> None:
    monkeypatch.setattr(Path, "resolve", Mock(side_effect=failure))
    with pytest.raises(InvalidInputError, match=expected) as error:
        snapshot_source(network_file[0])
    assert "untrusted vendor" not in str(error.value)


def test_network_change_during_probe_invalidates_snapshot(
    network_file: tuple[str, Path, Path],
) -> None:
    mapped, _, backing = network_file
    probe = Mock()

    def change(*args: object, **kwargs: object) -> object:
        backing.write_bytes(b"changed while inspecting")
        return None

    probe.inspect.side_effect = change
    with pytest.raises(ProbeFailedError, match="changed during inspection"):
        InspectionService(probe).inspect(mapped)


@pytest.mark.parametrize("extract", [False, True])
def test_network_input_to_local_staging_uses_reviewed_identity(
    network_file: tuple[str, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extract: bool,
) -> None:
    mapped, canonical, backing = network_file
    asset = parse_response(
        json.dumps(
            {
                "format": {"format_name": "mp4" if extract else "matroska"},
                "streams": [
                    {
                        "index": 7,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "disposition": {"default": 0, "forced": 0},
                    }
                ],
            }
        ).encode(),
        snapshot_source(mapped),
    )
    planner = OperationPlanningService()
    selection = (TrackSelection(StreamReference(asset.source, 7)),)
    output = OutputProfile("mkv", str(tmp_path / "local-output.mkv"))
    plan = planner.plan((asset,), selection, output)
    plan = planner.plan(
        (asset,),
        selection,
        output,
        acknowledged_warnings=frozenset(plan.pending_warnings),
        acknowledged_revision=plan.revision,
    )
    if extract:
        extraction = ExtractionPlanningService()
        plan = extraction.plan(asset, selection[0].reference, str(tmp_path / "local-output.h264"))
        plan = extraction.plan(
            asset,
            selection[0].reference,
            plan.output.path,
            acknowledged_warnings=frozenset(plan.pending_warnings),
            acknowledged_revision=plan.revision,
        )
    assert plan.arguments is not None and str(canonical) in plan.arguments
    inspector = Mock()
    inspector.inspect.return_value = asset
    runner = Mock()

    def write(arguments: tuple[str, ...], timeout: float) -> ProcessOutcome:
        assert str(canonical) in arguments and arguments[arguments.index("-map") + 1] == "0:7"
        assert Path(arguments[-1]).parent.parent == tmp_path
        Path(arguments[-1]).write_bytes(b"simulated validated output")
        return ProcessOutcome(0)

    runner.run.side_effect = write
    validator = Mock()
    validator.validate.return_value = ValidationReport((), None, ())
    monkeypatch.setattr(
        "mediatrack_forge.application.execution.discover_ffmpeg", lambda _: "ffmpeg"
    )
    original = backing.read_bytes()
    service = RemuxExecutionService(inspector=inspector, runner=runner, validator=validator)
    if extract:
        monkeypatch.setattr(ExtractionExecutionService, "_validator_for", lambda *args: validator)
        service = ExtractionExecutionService(inspector=inspector, runner=runner)
    result = service.execute(ExecutionRequest(plan, plan.revision, plan.revision))
    assert result.published and result.cleanup_complete and backing.read_bytes() == original
    assert not list(tmp_path.glob(".mediatrack-*"))
    backing.write_bytes(b"changed after review")
    fresh = planner.plan(
        (asset,),
        selection,
        OutputProfile("mkv", str(tmp_path / "another.mkv")),
        acknowledged_warnings=plan.acknowledged_warnings,
        acknowledged_revision=plan.revision,
    )
    assert fresh.revision != plan.revision and not fresh.execution_allowed
    assert any(issue.code == "SOURCE_CHANGED" for issue in fresh.issues)


@pytest.mark.parametrize(
    "path", [r"\\trusted-server\share\out.mkv", "//trusted-server/share/out.mkv"]
)
def test_unc_output_is_still_rejected_without_filesystem_access(path: str) -> None:
    with pytest.raises(ValueError, match="local output"):
        destination_path(path)


def test_mapped_output_resolving_to_unc_is_rejected(
    network_file: tuple[str, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.planning_paths.os", SimpleNamespace(name="nt")
    )
    with pytest.raises(ValueError, match="Network output"):
        destination_path(network_file[0])


@pytest.mark.parametrize("drive_type", [0, 1, 2, 3, 4, 5, 6])
def test_native_volume_classification_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drive_type: int
) -> None:
    kernel = Mock()

    def volume(path: str, buffer: object, size: int) -> bool:
        buffer.value = "Z:\\"  # type: ignore[attr-defined]
        return True

    kernel.GetVolumePathNameW.side_effect = volume
    kernel.GetDriveTypeW.return_value = drive_type
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.windows_paths.sys", SimpleNamespace(platform="win32")
    )
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.windows_paths.ctypes.WinDLL",
        lambda *a, **k: kernel,
        raising=False,
    )
    if drive_type in (2, 3, 6):
        require_local_volume(tmp_path / "output.mkv")
    else:
        with pytest.raises(ValueError, match="Network or unverified"):
            require_local_volume(tmp_path / "output.mkv")


def test_staging_and_publication_recheck_local_only_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "output.mkv"
    store = PrivateStagingStore()
    stage = store.allocate(destination)
    stage.path.write_bytes(b"owned validated output")
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.staging.destination_path",
        Mock(side_effect=ValueError("remote")),
    )
    with pytest.raises(ExecutionFailure, match="INVALID_DESTINATION"):
        store.allocate(destination)
    with pytest.raises(ExecutionFailure, match="INVALID_DESTINATION"):
        stage.publish(destination)
    assert not destination.exists()
    stage.cleanup()
    assert not list(tmp_path.glob(".mediatrack-*"))

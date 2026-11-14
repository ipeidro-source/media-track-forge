"""Offline checks for the installed package and minimal application contract."""

import importlib
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

from mediatrack_forge import __version__
from mediatrack_forge.ui.cli import main
from scripts.check_release import validate_tag


@pytest.mark.parametrize("layer", ["domain", "application", "infrastructure", "ui"])
def test_layer_imports(layer: str) -> None:
    assert importlib.import_module(f"mediatrack_forge.{layer}")


def test_installed_version_matches_package() -> None:
    assert importlib.metadata.version("mediatrack-forge") == __version__


def test_only_approved_desktop_runtime_dependency() -> None:
    assert importlib.metadata.requires("mediatrack-forge") == ["customtkinter==6.0.0"]


def test_default_entry_point_shows_scope(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "Inspect filesystem media" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_information_options(option: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([option])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert (__version__ if option == "--version" else "usage:") in output


def test_unimplemented_command_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["remux"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_module_entry_point_outside_repository(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mediatrack_forge", "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == f"MediaTrack Forge {__version__}"
    assert not result.stderr


def test_matching_release_tag() -> None:
    assert validate_tag(f"v{__version__}") == __version__


@pytest.mark.parametrize("tag", ["", "0.1.0", "v9.9.9", "v0.1.0-rc1", "v0.1.0\n"])
def test_invalid_release_tag(tag: str) -> None:
    with pytest.raises(ValueError, match="Release tag must be"):
        validate_tag(tag)

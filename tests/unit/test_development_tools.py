"""Validate development tool failure paths without network access."""

import pytest
import yaml

from scripts.check_release import main
from scripts.check_yaml import UniqueKeyLoader


def test_yaml_duplicate_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        yaml.load("permissions: read\npermissions: write", Loader=UniqueKeyLoader)


def test_yaml_nested_duplicate_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        yaml.load("job:\n  name: first\n  name: second", Loader=UniqueKeyLoader)


def test_release_cli_rejects_mismatch(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["v9.9.9"])
    assert exc.value.code == 2
    assert "Release tag must be" in capsys.readouterr().err

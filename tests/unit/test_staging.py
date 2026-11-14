"""Exclusive local publication and ownership-aware cleanup without media tools."""

import errno
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from mediatrack_forge.domain.execution import ExecutionFailure
from mediatrack_forge.infrastructure.staging import PrivateStagingStore


def test_private_unique_stage_and_exclusive_publication(tmp_path: Path) -> None:
    destination = tmp_path / "final.mkv"
    store = PrivateStagingStore()
    first, second = store.allocate(destination), store.allocate(destination)
    assert first.path != second.path and first.directory != second.directory
    assert first.directory.parent == destination.parent
    assert first.path.stat().st_size == 0
    if os.name != "nt":
        assert first.directory.stat().st_mode & 0o077 == 0
        assert first.path.stat().st_mode & 0o077 == 0
    first.path.write_bytes(b"validated output")
    first.flush()
    first.publish(destination)
    assert destination.read_bytes() == b"validated output"
    assert destination.stat().st_ino == first.path.stat().st_ino
    first.cleanup()
    second.cleanup()
    assert destination.read_bytes() == b"validated output"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("kind", ["file", "directory", "source_alias"])
def test_existing_destination_and_symlinks_never_overwritten(tmp_path: Path, kind: str) -> None:
    destination = tmp_path / "final.mkv"
    stage = PrivateStagingStore().allocate(destination)
    stage.path.write_bytes(b"validated output")
    source = tmp_path / "source.mkv"
    source.write_bytes(b"original")
    if kind == "directory":
        destination.mkdir()
    elif kind == "source_alias":
        os.link(source, destination)
    else:
        destination.write_bytes(b"competitor")
    with pytest.raises(ExecutionFailure, match="DESTINATION_COLLISION"):
        stage.publish(destination)
    stage.cleanup()
    assert source.read_bytes() == b"original"
    assert os.path.lexists(destination)
    if kind == "file":
        assert destination.read_bytes() == b"competitor"


def test_last_moment_collision_is_decided_by_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "final.mkv"
    stage = PrivateStagingStore().allocate(destination)
    original_link = os.link

    def race(source: Path, target: Path, *, follow_symlinks: bool) -> None:
        target.write_bytes(b"competing file")
        original_link(source, target, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "link", race)
    with pytest.raises(ExecutionFailure, match="DESTINATION_COLLISION"):
        stage.publish(destination)
    stage.cleanup()
    assert destination.read_bytes() == b"competing file"


def test_unsupported_link_has_no_unsafe_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "final.mkv"
    stage = PrivateStagingStore().allocate(destination)
    monkeypatch.setattr(os, "link", Mock(side_effect=OSError(errno.ENOTSUP, "unsupported")))
    with pytest.raises(ExecutionFailure, match="PUBLICATION_UNSUPPORTED"):
        stage.publish(destination)
    stage.cleanup()
    assert not destination.exists()


def test_cleanup_refuses_foreign_artifact(tmp_path: Path) -> None:
    stage = PrivateStagingStore().allocate(tmp_path / "final.mkv")
    # Rename rather than unlink while the owned descriptor is open on Windows.
    stage.flush()
    stage._close()
    original = stage.path.with_suffix(".original")
    stage.path.rename(original)
    stage.path.write_bytes(b"foreign")
    with pytest.raises(ExecutionFailure):
        stage.cleanup()
    assert stage.path.read_bytes() == b"foreign"
    assert original.exists()
    stage.path.unlink()
    original.unlink()
    stage.directory.rmdir()


def test_dangling_symlink_uses_lexists_not_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "final.mkv"
    stage = PrivateStagingStore().allocate(destination)
    original = os.path.lexists
    monkeypatch.setattr(
        os.path, "lexists", lambda path: True if path == destination else original(path)
    )
    link = Mock()
    monkeypatch.setattr(os, "link", link)
    assert not destination.exists()
    with pytest.raises(ExecutionFailure, match="DESTINATION_COLLISION"):
        stage.publish(destination)
    link.assert_not_called()
    stage.cleanup()


def test_missing_output_directory_is_not_created(tmp_path: Path) -> None:
    parent = tmp_path / "missing"
    with pytest.raises(ExecutionFailure, match="INVALID_DESTINATION"):
        PrivateStagingStore().allocate(parent / "final.mkv")
    assert not parent.exists()


def test_exclusive_allocation_never_reuses_a_foreign_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = tmp_path / ".mediatrack-collision"
    foreign.mkdir()
    (foreign / "keep").write_bytes(b"foreign content")
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.staging.secrets.token_hex", lambda _: "collision"
    )
    with pytest.raises(ExecutionFailure, match="STAGING_FAILED"):
        PrivateStagingStore().allocate(tmp_path / "final.mkv")
    assert (foreign / "keep").read_bytes() == b"foreign content"

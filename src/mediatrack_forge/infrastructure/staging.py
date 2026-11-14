"""Owned private staging and same-filesystem exclusive hard-link publication."""

import errno
import os
import secrets
import stat
import tempfile
from pathlib import Path

from mediatrack_forge.domain.execution import ExecutionFailure
from mediatrack_forge.infrastructure.planning_paths import destination_path


def _local_destination(path: Path) -> None:
    try:
        if destination_path(str(path)) != path:
            raise ValueError("Destination normalization changed")
    except (OSError, ValueError, RuntimeError) as exc:
        raise ExecutionFailure("INVALID_DESTINATION") from exc


def _identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_ino == 0:
        raise ExecutionFailure("STAGING_OWNERSHIP_LOST")
    return info.st_dev, info.st_ino


class PrivateStage:
    def __init__(self, directory: Path, path: Path, descriptor: int) -> None:
        self.directory = directory
        self.path = path
        self._descriptor: int | None = descriptor
        self._directory_identity = _identity(directory)
        self._file_identity = _identity(path)

    def verify(self) -> None:
        if (
            _identity(self.directory) != self._directory_identity
            or _identity(self.path) != self._file_identity
            or not stat.S_ISREG(self.path.lstat().st_mode)
        ):
            raise ExecutionFailure("STAGING_OWNERSHIP_LOST")
        if self._descriptor is not None:
            info = os.fstat(self._descriptor)
            if (info.st_dev, info.st_ino) != self._file_identity:
                raise ExecutionFailure("STAGING_OWNERSHIP_LOST")

    def flush(self) -> None:
        self.verify()
        if self._descriptor is None:
            raise ExecutionFailure("STAGING_OWNERSHIP_LOST")
        os.fsync(self._descriptor)

    def _close(self) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None

    def release(self) -> None:
        """Release our descriptor without touching a potentially active output."""
        self._close()

    def publish(self, destination: Path) -> None:
        _local_destination(destination)
        self.verify()
        if destination.parent != self.directory.parent:
            raise ExecutionFailure("PUBLICATION_FAILED")
        if os.path.lexists(destination):
            raise ExecutionFailure("DESTINATION_COLLISION")
        # No rename/copy fallback: the link itself is the no-overwrite authority.
        try:
            os.link(self.path, destination, follow_symlinks=False)
        except FileExistsError as exc:
            raise ExecutionFailure("DESTINATION_COLLISION") from exc
        except OSError as exc:
            unsupported = {errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS}
            code = "PUBLICATION_UNSUPPORTED" if exc.errno in unsupported else "PUBLICATION_FAILED"
            raise ExecutionFailure(code) from exc
        if _identity(destination) != self._file_identity:
            raise ExecutionFailure("PUBLICATION_FAILED")

    def cleanup(self) -> None:
        # Verify against the still-open identity before Windows requires closing it.
        try:
            if _identity(self.directory) != self._directory_identity:
                raise ExecutionFailure("TEMPORARY_CLEANUP_FAILED")
            if os.path.lexists(self.path):
                self.verify()
        finally:
            self._close()
        if os.path.lexists(self.path):
            self.verify()
            self.path.unlink()
        self.directory.rmdir()  # Never recursively remove foreign entries.


class PrivateStagingStore:
    def allocate(self, destination: Path) -> PrivateStage:
        _local_destination(destination)
        parent = destination.parent
        if not parent.is_dir():
            raise ExecutionFailure("INVALID_DESTINATION")
        for _ in range(10):
            directory = parent / f".mediatrack-{secrets.token_hex(16)}"
            try:
                if os.name == "nt":
                    from mediatrack_forge.infrastructure.windows_security import private_directory

                    private_directory(directory)
                else:
                    directory.mkdir(mode=0o700)
                    if directory.stat().st_mode & 0o077:
                        try:
                            directory.rmdir()
                        except OSError as exc:
                            raise ExecutionFailure("TEMPORARY_CLEANUP_FAILED") from exc
                        raise ExecutionFailure("STAGING_FAILED")
                break
            except FileExistsError:
                continue
            except OSError as exc:
                raise ExecutionFailure("STAGING_FAILED") from exc
        else:
            raise ExecutionFailure("STAGING_FAILED")
        descriptor: int | None = None
        filename: str | None = None
        directory_identity = _identity(directory)
        try:
            descriptor, filename = tempfile.mkstemp(prefix="output-", suffix=".part", dir=directory)
            return PrivateStage(directory, Path(filename), descriptor)
        except Exception as exc:
            try:
                if descriptor is not None:
                    info = os.fstat(descriptor)
                    os.close(descriptor)
                    if filename is not None:
                        artifact = Path(filename)
                        if _identity(artifact) != (info.st_dev, info.st_ino):
                            raise ExecutionFailure("TEMPORARY_CLEANUP_FAILED")
                        artifact.unlink()
                if _identity(directory) != directory_identity:
                    raise ExecutionFailure("TEMPORARY_CLEANUP_FAILED")
                directory.rmdir()
            except Exception as cleanup_error:
                raise ExecutionFailure("TEMPORARY_CLEANUP_FAILED") from cleanup_error
            raise ExecutionFailure("STAGING_FAILED") from exc

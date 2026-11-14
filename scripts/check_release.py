"""Validate a future release tag; this script never builds or publishes artifacts."""

import argparse
from collections.abc import Sequence

from mediatrack_forge import __version__


def validate_tag(tag: str) -> str:
    """Require the exact v-prefixed application version, without normalization."""
    expected = f"v{__version__}"
    if tag != expected:
        raise ValueError(f"Release tag must be {expected}; received {tag!r}.")
    return __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Check an explicitly supplied tag for future release preflight use."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    args = parser.parse_args(argv)
    try:
        print(validate_tag(args.tag))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

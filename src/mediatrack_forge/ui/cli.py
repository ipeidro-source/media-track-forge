"""Minimal development entry point; media commands arrive in subsequent PRs."""

import argparse
from collections.abc import Sequence

from mediatrack_forge import __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Show development help or version without opening files or launching processes."""
    parser = argparse.ArgumentParser(
        prog="mediatrack-forge",
        description=(
            "MediaTrack Forge development foundation. Media operations are not available yet."
        ),
    )
    parser.add_argument("--version", action="version", version=f"MediaTrack Forge {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0

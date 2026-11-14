"""Command-line presentation for read-only filesystem media inspection."""

import argparse
import math
import sys
from collections.abc import Sequence

from mediatrack_forge import __version__
from mediatrack_forge.application.inspection import InspectionError, InspectionService
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.ui.inspection_json import serialize_inspection


def _positive_seconds(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Timeout must be a positive number.") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Timeout must be a finite positive number.")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect media with JSON-only stdout; ordinary errors never expose tracebacks."""
    parser = argparse.ArgumentParser(
        prog="mediatrack-forge",
        description="Inspect filesystem media read-only, including trusted Windows shares.",
    )
    parser.add_argument("--version", action="version", version=f"MediaTrack Forge {__version__}")
    commands = parser.add_subparsers(dest="command")
    inspect = commands.add_parser(
        "inspect", help="Inspect a filesystem media source as versioned JSON."
    )
    inspect.add_argument("path")
    inspect.add_argument("--ffprobe", help="Trusted external ffprobe executable name or path.")
    inspect.add_argument("--timeout-seconds", type=_positive_seconds, default=30.0)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        asset = InspectionService(FFprobeAdapter(args.ffprobe)).inspect(
            args.path, timeout_seconds=args.timeout_seconds
        )
        print(serialize_inspection(asset))
        return 0
    except InspectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code

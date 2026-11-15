"""Read-only, bounded-output packet-count diagnosis; no media text or tool logs printed."""

import argparse
import json
import math
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from mediatrack_forge.application.inspection import InspectionError, snapshot_source
from mediatrack_forge.infrastructure.extraction_validation import packet_count
from mediatrack_forge.infrastructure.packet_probe import PacketScanError
from mediatrack_forge.infrastructure.planning_paths import destination_path


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Invalid diagnostic arguments; use --help.")


def diagnose(
    path: str, index: int, role: str, executable: str | None, timeout: float
) -> dict[str, object]:
    started = time.monotonic()
    result: dict[str, object] = {
        "operation": "packet_count",
        "role": role,
        "stream_index": index,
        "timeout_seconds": timeout,
        "status": "failed",
        "failure": None,
    }
    try:
        checked_path = destination_path(path) if role == "output" else Path(path)
        source = snapshot_source(checked_path)
        result["file_size_bytes"] = source.size_bytes
        result["path_kind"] = (
            "UNC_FILE" if str(source.path).startswith("\\\\") else "FILESYSTEM_FILE"
        )
        result["packet_count"] = packet_count(source.path, index, executable, timeout)
        if snapshot_source(source.path) != source:
            result["failure"] = "FILE_CHANGED"
        else:
            result["status"] = "passed"
    except PacketScanError as exc:
        result["failure"] = exc.code
        result["detail"] = exc.detail
    except (InspectionError, OSError, ValueError, RuntimeError):
        result["failure"] = "FILE_UNAVAILABLE"
        result["detail"] = "Check the file path, access permissions, user session and connection."
    except Exception:
        result["failure"] = "UNEXPECTED_FAILURE"
        result["detail"] = (
            "Diagnostic could not complete; no raw exception or media data is printed."
        )
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Original file; the path is never printed.")
    parser.add_argument("--stream-index", required=True, type=int, help="Original subtitle index.")
    parser.add_argument(
        "--output", help="Optional existing local SRT to count separately; never created."
    )
    parser.add_argument("--ffprobe", help="Optional trusted native ffprobe executable.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30,
        help="Explicit per-probe limit, at most 300 seconds; no automatic retries.",
    )
    try:
        args = parser.parse_args(argv)
        if (
            not math.isfinite(args.timeout_seconds)
            or not 0 < args.timeout_seconds <= 300
            or args.stream_index < 0
        ):
            raise ValueError
    except (ValueError, argparse.ArgumentError):
        print('{"diagnostic_version":1,"failure":"INVALID_ARGUMENTS"}')
        return 2
    results = [
        diagnose(args.source, args.stream_index, "source", args.ffprobe, args.timeout_seconds)
    ]
    if args.output:
        results.append(diagnose(args.output, 0, "output", args.ffprobe, args.timeout_seconds))
    print(json.dumps({"diagnostic_version": 1, "results": results}, allow_nan=False))
    return 0 if all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

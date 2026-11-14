"""Opt-in real Windows share evidence using owner-supplied tiny synthetic inputs."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from mediatrack_forge.application.execution import RemuxExecutionService
from mediatrack_forge.application.external_subtitles import ExternalSubtitleService
from mediatrack_forge.application.extraction import (
    ExtractionExecutionService,
    ExtractionPlanningService,
)
from mediatrack_forge.application.inspection import InspectionError, InspectionService
from mediatrack_forge.application.planning import OperationPlanningService
from mediatrack_forge.domain.execution import ExecutionFailure, ExecutionRequest
from mediatrack_forge.domain.planning import OutputProfile, StreamReference, TrackSelection
from mediatrack_forge.infrastructure.ffprobe import FFprobeAdapter
from mediatrack_forge.infrastructure.planning_paths import destination_path


def bounded_hash(path: Path) -> str:
    with path.open("rb") as source:
        data = source.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Use synthetic inputs of at most 16 MiB for this evidence check.")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unc-media", required=True, help="Real trusted UNC synthetic H.264/AAC MP4 input."
    )
    parser.add_argument(
        "--mapped-media", required=True, help="Existing mapped drive path to the same media file."
    )
    parser.add_argument("--unc-srt", required=True, help="Real trusted UNC UTF-8 SRT input.")
    parser.add_argument(
        "--local-directory",
        required=True,
        help="Existing local directory; evidence outputs are retained.",
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        print("Real Windows network evidence requires Windows; no test was executed.")
        return 1
    try:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_type = kernel.GetDriveTypeW
        get_type.argtypes = [wintypes.LPCWSTR]
        get_type.restype = wintypes.UINT
        unc, mapped, srt = Path(args.unc_media), Path(args.mapped_media), Path(args.unc_srt)
        if not unc.drive.startswith("\\\\") or not srt.drive.startswith("\\\\"):
            raise ValueError("Supply genuine UNC media and SRT sources, not local aliases.")
        if mapped.drive.startswith("\\\\") or get_type(mapped.anchor) != 4:
            raise ValueError("The mapped media must be on an actual Windows remote drive.")
        local = Path(args.local_directory).resolve(strict=True)
        destination_path(
            str(local / "network-evidence.mkv")
        )  # Reject remote output before writing.
        if not local.is_dir():
            raise ValueError("Choose an existing local evidence directory.")
        inspector = InspectionService(FFprobeAdapter())
        asset = inspector.inspect(unc)
        if inspector.inspect(mapped) != asset or not asset.source.path.drive.startswith("\\\\"):
            raise ValueError("Mapped and UNC inspections must identify the same canonical input.")
        subtitle, track = ExternalSubtitleService(inspector).import_srt(srt)
        originals = {a.source.path: bounded_hash(a.source.path) for a in (asset, subtitle)}
        # Retain this unique local directory for independent review; never clean a share.
        evidence = Path(tempfile.mkdtemp(prefix="mtf-network-evidence-", dir=local))
        sources = (asset, subtitle)
        selections = tuple(
            TrackSelection(StreamReference(a.source, stream.index))
            for a in sources
            for stream in a.streams
        )
        planner = OperationPlanningService()
        output = OutputProfile("mkv", str(evidence / "remux.mkv"))
        plan = planner.plan(sources, selections, output, external_tracks=(track,))
        plan = planner.plan(
            sources,
            selections,
            output,
            external_tracks=(track,),
            acknowledged_warnings=frozenset(plan.pending_warnings),
            acknowledged_revision=plan.revision,
        )
        if not plan.execution_allowed:
            raise ValueError(
                "Synthetic remux input is unsupported: " + ", ".join(i.code for i in plan.issues)
            )
        remux = RemuxExecutionService().execute(
            ExecutionRequest(plan, plan.revision, plan.revision)
        )
        selected = next(stream for stream in asset.streams if stream.codec == "h264")
        extraction = ExtractionPlanningService()
        reference = StreamReference(asset.source, selected.index)
        extracted = extraction.plan(asset, reference, str(evidence / "video.h264"))
        extracted = extraction.plan(
            asset,
            reference,
            extracted.output.path,
            acknowledged_warnings=frozenset(extracted.pending_warnings),
            acknowledged_revision=extracted.revision,
        )
        result = ExtractionExecutionService().execute(
            ExecutionRequest(extracted, extracted.revision, extracted.revision)
        )
        unchanged = all(bounded_hash(path) == digest for path, digest in originals.items())
        passed = (
            remux.state == result.state == "completed"
            and remux.published
            and result.published
            and remux.cleanup_complete
            and result.cleanup_complete
            and unchanged
        )
        print(
            json.dumps(
                {
                    "passed": passed,
                    "actual_windows_unc_and_mapped_inputs": True,
                    "mapped_canonical_identity_matches": True,
                    "external_srt_inspected": True,
                    "remux": remux.state,
                    "extraction": result.state,
                    "sources_unchanged": unchanged,
                    "local_evidence_directory": str(evidence),
                    "transport_note": "Record Get-SmbConnection for SMB transport/dialect.",
                }
            )
        )
        return 0 if passed else 1
    except (InspectionError, ExecutionFailure, OSError, ValueError, StopIteration):
        print(
            "Network evidence failed. Check share access, fixture codecs and local output support."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

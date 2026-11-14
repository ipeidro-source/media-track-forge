"""Explicit public plan_version 1 serialization, separate from inspection schema v1."""

import json
from dataclasses import asdict

from mediatrack_forge.domain.media import MediaSource
from mediatrack_forge.domain.planning import OperationPlan, StreamReference
from mediatrack_forge.ui.inspection_json import inspection_document


def _source(source: MediaSource) -> dict[str, object]:
    return {
        "path": str(source.path),
        "size_bytes": source.size_bytes,
        "modified_time_ns": source.modified_time_ns,
    }


def _reference(reference: StreamReference) -> dict[str, object]:
    return {
        "source": _source(reference.source),
        "index": reference.index,
    }


def plan_document(plan: OperationPlan) -> dict[str, object]:
    return {
        "plan_version": plan.plan_version,
        "revision": plan.revision,
        "acknowledged_revision": plan.acknowledged_revision,
        "sources": [inspection_document(asset) for asset in plan.sources],
        "output": {
            "container": plan.output.container,
            "requested_path": plan.output.path,
            "path": str(plan.destination_path) if plan.destination_path is not None else None,
        },
        "selections": [
            {
                "reference": _reference(item.reference),
                "include": item.include,
                "metadata": asdict(item.metadata),
            }
            for item in plan.selections
        ],
        "external_tracks": [
            {
                "source": _source(item.source),
                "intended_kind": item.intended_kind,
                "stream_index": item.stream_index,
                "codec": item.codec,
                "format_name": item.format_name,
                "metadata": asdict(item.metadata),
                "validated": item.validated,
            }
            for item in plan.external_tracks
        ],
        "included": [
            {
                "reference": _reference(item.reference),
                "input_index": item.input_index,
                "output_index": item.output_index,
                "kind": item.source_stream.kind,
                "source_codec": item.source_stream.codec,
                "target_codec": item.target_codec,
                "action": item.action,
                "output_tags": dict(item.output_tags),
                "output_disposition": dict(item.output_disposition),
            }
            for item in plan.included
        ],
        "excluded": [
            {
                "reference": _reference(item.reference),
                "explicit": item.explicit,
                "action": item.action,
            }
            for item in plan.excluded
        ],
        "preserve_chapters": plan.preserve_chapters,
        "chapter_input_index": plan.chapter_input_index,
        "preservation": [
            {
                "category": item.category,
                "status": item.status,
                "detail": item.detail,
                "reference": _reference(item.reference) if item.reference else None,
            }
            for item in plan.preservation
        ],
        "issues": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "suggestion": item.suggestion,
                "reference": _reference(item.reference) if item.reference else None,
            }
            for item in plan.issues
        ],
        "intrinsically_valid": plan.intrinsically_valid,
        "acknowledged_warnings": sorted(plan.effective_acknowledged_warnings),
        "pending_warnings": list(plan.pending_warnings),
        "execution_allowed": plan.execution_allowed,
        "confirmation_required": plan.confirmation_required,
        "arguments": list(plan.arguments) if plan.arguments is not None else None,
    }


def serialize_plan(plan: OperationPlan) -> str:
    return json.dumps(plan_document(plan), ensure_ascii=True, allow_nan=False, sort_keys=True)

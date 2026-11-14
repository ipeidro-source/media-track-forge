"""Distinct extraction v1 serialization; remux and inspection schemas stay unchanged."""

import json
from typing import cast

from mediatrack_forge.domain.extraction import ExtractionPlan
from mediatrack_forge.ui.operation_plan_json import plan_document


def extraction_document(plan: ExtractionPlan) -> dict[str, object]:
    shared = plan_document(plan)
    return {
        "extraction_version": plan.extraction_version,
        "revision": plan.revision,
        "sources": shared["sources"],
        "selection": cast(list[object], shared["selections"])[0],
        "output": shared["output"],
        "included": shared["included"],
        "bitstream_filters": list(plan.bitstream_filters),
        "issues": shared["issues"],
        "acknowledged_revision": plan.acknowledged_revision,
        "acknowledged_warnings": sorted(plan.effective_acknowledged_warnings),
        "pending_warnings": list(plan.pending_warnings),
        "intrinsically_valid": plan.intrinsically_valid,
        "execution_allowed": plan.execution_allowed,
        "confirmation_required": True,
        "arguments": list(plan.arguments) if plan.arguments is not None else None,
    }


def serialize_extraction(plan: ExtractionPlan) -> str:
    return json.dumps(extraction_document(plan), ensure_ascii=True, sort_keys=True, allow_nan=False)

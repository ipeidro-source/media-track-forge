"""Small presentation helpers; compatibility decisions remain in application services."""

import math

from mediatrack_forge.domain.extraction import ExtractionPlan
from mediatrack_forge.domain.metadata import metadata_value
from mediatrack_forge.domain.planning import OperationPlan


def clock_text(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "Unknown"
    total = int(seconds)
    return f"{total // 3600:02}:{total // 60 % 60:02}:{total % 60:02}"


def size_text(size: int) -> str:
    number = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024 or unit == "TiB":
            return f"{number:.1f} {unit}"
        number /= 1024
    raise AssertionError("Unreachable size unit")


def language_text(code: str | None) -> str:
    names = {
        "eng": "English",
        "spa": "Spanish",
        "fra": "French",
        "deu": "German",
        "ita": "Italian",
        "por": "Portuguese",
        "jpn": "Japanese",
        "und": "Undetermined",
    }
    return f"{names[code]} ({code})" if code in names else code or "Unspecified"


def codec_text(codec: str | None) -> str:
    names = {
        "h264": "H.264",
        "hevc": "HEVC",
        "aac": "AAC",
        "mp3": "MP3",
        "vp9": "VP9",
        "opus": "Opus",
        "subrip": "SubRip / SRT",
        "mov_text": "MP4 text",
    }
    return f"{names[codec]} ({codec})" if codec in names else codec or "Unknown"


def review_summary(plan: OperationPlan) -> str:
    state = (
        "Cannot execute"
        if not plan.intrinsically_valid
        else "Requires acknowledgement"
        if plan.pending_warnings
        else "Ready to execute"
    )
    lines = [state, "", "Source"]
    lines.extend(str(a.source.path) for a in plan.sources)
    lines += [
        "",
        "Changes",
        "Extract one track" if isinstance(plan, ExtractionPlan) else "Create a new media container",
    ]
    for stream in plan.included:
        source = stream.source_stream
        language = (
            source.language
            if isinstance(plan, ExtractionPlan)
            else metadata_value(stream.output_tags, "language")
        )
        title = (
            source.title
            if isinstance(plan, ExtractionPlan)
            else metadata_value(stream.output_tags, "title")
        )
        lines.append(
            f"{stream.output_index + 1}. {source.kind.capitalize()} · {codec_text(source.codec)} · "
            f"{language_text(language)} · {title or 'Untitled'} · "
            f"original index {stream.reference.index}"
        )
        if stream.action != "copy":
            lines.append(f"   Convert subtitles to {stream.target_codec}; formatting may change.")
        intent = next(s.metadata for s in plan.selections if s.reference == stream.reference)
        for field in ("language", "title", "default", "forced"):
            value = getattr(intent, field)
            original = (
                getattr(source, field)
                if field in ("language", "title")
                else bool(dict(source.disposition).get(field, 0))
            )
            if value is not None and value != original:
                before = original if original is not None else "unspecified"
                lines.append(
                    f"   {field.capitalize()}: {before} → {value if value != '' else 'cleared'}"
                )
    lines.extend(
        f"Exclude {s.source_stream.kind}, original index {s.reference.index}: "
        f"{s.reference.source.path.name}"
        for s in plan.excluded
    )
    lines += [
        "",
        "Destination",
        str(plan.destination_path or plan.output.path),
        f"Format: {plan.output.container.upper()}",
    ]
    if plan.issues:
        lines += ["", "Compatibility and metadata"]
        for issue in plan.issues:
            affected = f" [track {issue.reference.index}]" if issue.reference else ""
            lines.append(f"{issue.severity.upper()}{affected}: {issue.message}")
            if issue.suggestion:
                lines.append(f"   {issue.suggestion}")
    return "\n".join(lines)

"""Pure command specification generation. This module never invokes FFmpeg."""

from mediatrack_forge.domain.planning import OperationPlan


def build_arguments(plan: OperationPlan) -> tuple[str, ...]:
    """Only intrinsically valid, acknowledged plans may expose proposed arguments."""
    if not plan.intrinsically_valid or plan.pending_warnings or plan.destination_path is None:
        raise ValueError("Blocked or unacknowledged plans have no executable command.")
    if not plan.included:
        raise ValueError("Explicit output mappings are required.")
    args = ["ffmpeg", "-nostdin", "-v", "error", "-n"]
    for asset in plan.sources:
        args += ["-protocol_whitelist", "file", "-i", str(asset.source.path)]
    for stream in plan.included:
        args += ["-map", f"{stream.input_index}:{stream.reference.index}"]
    args += [
        "-map_metadata",
        "-1",
        "-map_metadata:s",
        "-1",
        "-map_chapters",
        str(plan.chapter_input_index) if plan.chapter_input_index is not None else "-1",
    ]
    if plan.chapter_input_index is not None:
        for chapter_index, chapter in enumerate(plan.sources[plan.chapter_input_index].chapters):
            for key, value in chapter.tags:
                if key == "title":
                    args += [f"-metadata:c:{chapter_index}", f"{key}={value}"]
    for key, value in plan.output_format_tags:
        args += ["-metadata", f"{key}={value}"]
    for stream in plan.included:
        index = stream.output_index
        codec = "copy" if stream.action == "copy" else stream.target_codec
        if stream.action != "copy" and not (
            stream.action == "convert_subtitle"
            and stream.source_stream.kind == "subtitle"
            and (stream.source_stream.codec, plan.output.container, stream.target_codec)
            in (("subrip", "mp4", "mov_text"), ("mov_text", "mkv", "subrip"))
        ):
            raise ValueError("Only validated subtitle conversion is permitted.")
        args += [f"-c:{index}", codec or "copy"]
        for key, value in stream.output_tags:
            args += [f"-metadata:s:{index}", f"{key}={value}"]
        flags = "+".join(key for key, value in stream.output_disposition if value)
        args += [f"-disposition:{index}", flags or "0"]
    args += [
        "-f",
        "matroska" if plan.output.container == "mkv" else "mp4",
        str(plan.destination_path),
    ]
    return tuple(args)

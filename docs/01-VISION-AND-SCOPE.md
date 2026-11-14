# 01 — Product Vision and Scope

**Status:** initial accepted planning baseline; unresolved assumptions remain explicitly tracked.

## Problem

Managing media tracks, languages, subtitles, and container conversion often requires FFmpeg command-line knowledge or multiple tools. Users need a clear view of exactly what a file contains and a predictable way to retain, remove, extract, and add tracks—without loss of quality when audio/video re-encoding is unnecessary.

## Target user

Windows users managing local recordings, personal archives, or media they are authorized to process. Typical needs include removing unwanted language tracks, adding SRT subtitles, retaining video without any audio track, extracting tracks, and safely remuxing media containers.

This is not a timeline video editor, downloader, or media streaming platform.

## Core value proposition

**Inspect → select streams → review plan → execute → validate output.**

Local-first privacy, explicit stream operations, stream-copy by default, and evidence-based output verification.

## Planned product capabilities

- Read local video and media files, including video-only inputs and containers with multiple video, audio, and subtitle streams.
- Inspect streams via ffprobe: source index, type, codec, language, title, disposition, duration, and other available properties.
- Retain, remove, add, extract, and reorder individual streams; set supported metadata including language and default flags.
- Remux into MKV and MP4 using a tested compatibility policy. Accept AVI inputs whenever FFmpeg can probe and remux their streams.
- In later phases: selectively transcode audio/video, apply presets, use hardware acceleration, process batches, and automate media library maintenance.

## MVP exclusions

No online downloads, frame-accurate editing, video cutting, bitmap-subtitle OCR, burned-in subtitles, machine translation, AI, built-in player, cloud distribution, NAS/Docker service, GPU acceleration, advanced compression, or intelligent file-size prediction.

These ideas remain future candidates, not MVP commitments.

## MVP success criteria

1. A Windows user can perform the essential operations without writing commands.
2. Original files remain unchanged after success, failure, or cancellation.
3. Outputs are verified for expected streams, codecs, order, language metadata, and acceptable duration differences.
4. Incompatible stream/container combinations are rejected with actionable alternatives; video/audio are never transcoded silently.
5. Windows 10/11 x64 use is documented and tested.

## Positioning

The product should not attempt to replace mature general-purpose converters initially. Its first differentiator is **safe, transparent, per-stream control**, with batch rules and intelligent library optimization explored only after MVP validation.

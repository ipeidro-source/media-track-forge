"""Main-thread desktop presentation; application services remain behind the controller."""

from __future__ import annotations

import re
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Literal, cast

import customtkinter as ctk

from mediatrack_forge.application.extraction import ExtractionPlanningService
from mediatrack_forge.domain.planning import MetadataIntent, StreamReference
from mediatrack_forge.ui.display import (
    clock_text,
    codec_text,
    language_text,
    review_summary,
    size_text,
)
from mediatrack_forge.ui.presentation_model import DesktopController, plan_text, result_text


class DesktopWindow:
    def __init__(self, controller: DesktopController | None = None) -> None:
        ctk.set_appearance_mode("system")
        self.root = cast(tk.Tk, ctk.CTk())
        self.root.title("MediaTrack Forge")
        screen_width, screen_height = self._screen_bounds()
        self.root.geometry(f"{min(700, screen_width)}x{min(300, screen_height)}")
        self.root.minsize(min(620, screen_width), min(280, screen_height))
        self.controller = controller if controller is not None else DesktopController()
        self._loading = True
        self._destroyed = False
        self._selected: StreamReference | None = None
        self._rows: dict[str, StreamReference] = {}
        self._metadata_dirty = False
        self._metadata_fields: set[str] = set()
        self._plan_revision: str | None = ""
        self._review_ack: frozenset[str] = frozenset()
        self._appearance = ""
        self._warning_vars: dict[str, tk.BooleanVar] = {}
        self._editing_controls: list[Any] = []
        self._expanded = False
        self._progress_mode = "idle"
        self._execution_started: float | None = None
        self._execution_elapsed: float | None = None
        self._extraction_rows: dict[str, StreamReference] = {}
        self._destination_check_id: str | None = None
        self._rendered_intent: object = None
        self._last_format = "mkv"
        self._last_elapsed_tick = 0
        self._source_identity: object = None
        self._show_technical = tk.BooleanVar(value=False)
        self._show_result_details = tk.BooleanVar(value=False)
        self.extraction_selection = tk.StringVar(value="Choose a source track")
        self.extraction_description = tk.StringVar()
        self.destination_error = tk.StringVar()
        self.mode = tk.StringVar(value="Remux")
        self.container = tk.StringVar(value="mkv")
        self.destination = tk.StringVar()
        self.chapters = tk.BooleanVar(value=True)
        self.language = tk.StringVar()
        self.track_title = tk.StringVar()
        self.default = tk.StringVar(value="Keep original")
        self.forced = tk.StringVar(value="Keep original")
        self.status = tk.StringVar(value=self.controller.status)
        self.summary = tk.StringVar(
            value="No media selected. Local files or trusted Windows shares."
        )
        self.phase = tk.StringVar(value="No operation running")
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self.root)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(header, text="MediaTrack Forge", font=("Segoe UI", 24, "bold")).pack(
            side="left", padx=16, pady=8
        )
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self.media = ctk.CTkScrollableFrame(self.tabs.add("1. Media"))
        self.operation = ctk.CTkScrollableFrame(self.tabs.add("2. Operation"))
        self.execution = self.tabs.add("3. Execution")
        self.media.pack(fill="both", expand=True)
        self.operation.pack(fill="both", expand=True)
        self.operation_empty = ctk.CTkLabel(
            self.tabs.tab("2. Operation"),
            text="Open Media in 1. Media to choose an operation and new output file.",
            wraplength=500,
        )
        self._build_media()
        self._build_operation()
        self._build_execution()
        self._enable_keyboard(self.root)
        self.footer_label = ctk.CTkLabel(
            self.root, textvariable=self.status, wraplength=1000, anchor="w"
        )
        self.footer_label.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        for variable in (self.mode, self.container, self.destination, self.chapters):
            variable.trace_add("write", self._options_changed)
        for variable in (
            self.language,
            self.track_title,
            self.default,
            self.forced,
        ):
            variable.trace_add("write", self._metadata_changed)
        self.root.bind("<Control-o>", lambda _: self._guard(self.open_media))
        self.root.bind("<Control-r>", lambda _: self._guard(self.review))
        self.root.bind("<Control-Return>", lambda _: self._guard(self.execute))
        self.root.bind("<Escape>", lambda _: self._guard(self.cancel))
        self.root.bind("<Alt-Key-1>", lambda _: self.tabs.set("1. Media"))
        self.root.bind("<Alt-Key-2>", lambda _: self.tabs.set("2. Operation"))
        self.root.bind("<Alt-Key-3>", lambda _: self.tabs.set("3. Execution"))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Configure>", self._wrap_window, add="+")
        self.root.bind("<FocusIn>", self._scroll_to_focus, add="+")
        self._loading = False
        self._refresh()
        self._poll_id = self.root.after(60, self._poll)
        self.open_button.focus_set()
        self.root.update_idletasks()
        self._initial_size = (self.root.winfo_width(), self.root.winfo_height())

    def _screen_bounds(self) -> tuple[int, int]:
        scale = ctk.ScalingTracker.get_window_scaling(self.root)
        return (
            max(1, int((self.root.winfo_screenwidth() - 80) / scale)),
            max(1, int((self.root.winfo_screenheight() - 100) / scale)),
        )

    def _button(
        self,
        parent: Any,
        text: str,
        command: Callable[[], None],
        *,
        editable: bool = True,
        width: int = 130,
    ) -> Any:
        button = ctk.CTkButton(parent, text=text, command=lambda: self._guard(command), width=width)
        button.pack(side="left", padx=4, pady=5)
        # CTkButton does not participate in Tk focus traversal by default.
        button._canvas.configure(takefocus=True)
        button._canvas.bind("<FocusIn>", lambda _: button._canvas.configure(highlightthickness=2))
        button._canvas.bind("<FocusOut>", lambda _: button._canvas.configure(highlightthickness=0))

        def activate(event: object) -> None:
            if button.cget("state") != "disabled":
                self._guard(command)

        button._canvas.bind("<Return>", activate)
        button._canvas.bind("<space>", activate)
        if editable:
            self._editing_controls.append(button)
        return button

    def _enable_keyboard(self, parent: Any) -> None:
        for widget in parent.winfo_children():
            if isinstance(widget, ctk.CTkButton):
                self._bind_button_keyboard(widget)
            if isinstance(widget, (ctk.CTkOptionMenu, ctk.CTkCheckBox)):
                widget._canvas.configure(takefocus=True)
                self._bind_keyboard(widget)
            self._enable_keyboard(widget)

    @staticmethod
    def _bind_button_keyboard(widget: Any) -> None:
        widget._canvas.configure(takefocus=True)
        widget._canvas.bind("<Return>", lambda _: widget.invoke())
        widget._canvas.bind("<space>", lambda _: widget.invoke())
        widget._canvas.bind("<FocusIn>", lambda _: widget._canvas.configure(highlightthickness=2))
        widget._canvas.bind("<FocusOut>", lambda _: widget._canvas.configure(highlightthickness=0))

    def _bind_keyboard(self, widget: Any) -> None:
        def activate(event: tk.Event[tk.Misc]) -> None:
            if widget.cget("state") == "disabled":
                return
            if isinstance(widget, ctk.CTkCheckBox):
                widget.toggle()
            else:
                values = list(widget.cget("values"))
                if values:
                    current = values.index(widget.get()) if widget.get() in values else 0
                    widget.set(
                        values[(current + (-1 if event.keysym == "Left" else 1)) % len(values)]
                    )
                    command = widget.cget("command")
                    if command is not None:
                        command(widget.get())

        for key in ("<space>", "<Return>", "<Left>", "<Right>"):
            widget._canvas.bind(key, activate)
        widget._canvas.bind("<FocusIn>", lambda _: widget._canvas.configure(highlightthickness=2))
        widget._canvas.bind("<FocusOut>", lambda _: widget._canvas.configure(highlightthickness=0))

    def _build_media(self) -> None:
        self.media.columnconfigure(0, weight=1)
        actions = ctk.CTkFrame(self.media)
        actions.grid(row=0, column=0, sticky="ew")
        self.open_button = self._button(actions, "Open Media (Ctrl+O)", self.open_media)
        self.add_button = self._button(actions, "Add SRT files", self.add_subtitles)
        self.summary_label = ctk.CTkLabel(
            self.media, textvariable=self.summary, anchor="w", justify="left", wraplength=1000
        )
        self.summary_label.grid(row=1, column=0, sticky="ew", padx=4, pady=8)
        frame = ttk.Frame(self.media)
        self.track_frame = frame
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        columns = (
            "state",
            "index",
            "kind",
            "codec",
            "language",
            "title",
            "default",
            "forced",
            "order",
            "source",
        )
        self.table = ttk.Treeview(
            frame, columns=columns, show="tree headings", selectmode="browse", height=9
        )
        self.table.heading("#0", text="Track group")
        self.table.column("#0", width=100, minwidth=80)
        self.table.tag_configure("changed", font=("Segoe UI", 9, "bold"))
        headings = (
            "Included",
            "Original index",
            "Kind",
            "Codec",
            "Language",
            "Title",
            "Default",
            "Forced",
            "Order",
            "Source",
        )
        for column, heading in zip(columns, headings, strict=True):

            def sort(c: str = column) -> None:
                self.sort_table(c)

            self.table.heading(column, text=heading, command=sort)
            self.table.column(column, width=100 if column != "source" else 200, minwidth=60)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.table.bind("<<TreeviewSelect>>", self._select_row)
        self.table.bind("<space>", lambda _: self._guard(self.toggle))
        self.table.bind("<Alt-Up>", lambda _: self._guard(lambda: self.move(-1)))
        self.table.bind("<Alt-Down>", lambda _: self._guard(lambda: self.move(1)))
        controls = ctk.CTkFrame(self.media)
        self.track_controls = controls
        controls.grid(row=3, column=0, sticky="ew", pady=6)
        self._button(controls, "Include / exclude", self.toggle)
        self._button(controls, "Move up", lambda: self.move(-1))
        self._button(controls, "Move down", lambda: self.move(1))
        ctk.CTkLabel(controls, text="* Changed").pack(side="left", padx=6)
        metadata_area = ctk.CTkFrame(self.media)
        self.metadata_area = metadata_area
        metadata_area.grid(row=4, column=0, sticky="nsew")
        metadata_area.columnconfigure(0, weight=1)
        ctk.CTkLabel(metadata_area, text="Edit Metadata", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=8
        )
        self.track_details = tk.StringVar()
        self.track_details_label = ctk.CTkLabel(
            metadata_area, textvariable=self.track_details, wraplength=900, justify="left"
        )
        self.track_details_label.grid(row=1, column=0, sticky="ew")
        editor = ctk.CTkFrame(metadata_area)
        editor.grid(row=2, column=0, sticky="ew")
        editor.columnconfigure(2, weight=1)
        for row, label, value in (
            (0, "Language", self.language),
            (1, "Title", self.track_title),
        ):
            ctk.CTkLabel(editor, text=label).grid(row=row, column=0, padx=8, pady=4)
            entry = ctk.CTkEntry(editor, textvariable=value)
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
            self._editing_controls.append(entry)
        flags = ctk.CTkFrame(metadata_area)
        flags.grid(row=3, column=0, sticky="ew", pady=5)
        for label, value in (("Default", self.default), ("Forced", self.forced)):
            ctk.CTkLabel(flags, text=label).pack(side="left", padx=8)
            menu = ctk.CTkOptionMenu(flags, variable=value, values=["Yes", "No"], width=75)
            menu.pack(side="left", padx=4)
            self._editing_controls.append(menu)
        self._button(flags, "Apply", self._save_metadata, width=80)
        self.reset_button = self._button(flags, "Reset to original", self.reset_metadata, width=120)
        self.metadata_help = ctk.CTkLabel(
            metadata_area,
            text="Apply saves pending output changes. Empty text clears a tag. "
            "Sources remain unchanged; only a separately confirmed operation creates output. "
            "Language: a three-letter code, for example eng or spa.",
            wraplength=1000,
        )
        self.metadata_help.grid(row=4, column=0, sticky="ew", pady=4)
        self.remove_button = ctk.CTkButton(
            metadata_area,
            text="Remove external source from session",
            command=lambda: self._guard(self.remove_external),
        )
        self.remove_button.grid(row=5, column=0, sticky="w", padx=8, pady=4)
        self._editing_controls.append(self.remove_button)
        self.copy_path_button = ctk.CTkButton(
            metadata_area, text="Copy full source path", command=self._copy_source_path
        )
        self.copy_path_button.grid(row=6, column=0, sticky="w", padx=8, pady=4)
        self.media.bind("<Configure>", self._wrap_media, add="+")

    def _build_operation(self) -> None:
        self.operation.columnconfigure(1, weight=1)
        ctk.CTkLabel(self.operation, text="Operation").grid(row=0, column=0, padx=8, pady=5)
        mode = ctk.CTkOptionMenu(self.operation, variable=self.mode, values=["Remux", "Extract"])
        mode.grid(row=0, column=1, sticky="w", pady=5)
        self.extraction_frame = ctk.CTkFrame(self.operation)
        self.extraction_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(self.extraction_frame, text="Exact source track").pack(anchor="w", padx=8)
        self.extraction_menu = ctk.CTkOptionMenu(
            self.extraction_frame,
            variable=self.extraction_selection,
            values=["Choose a source track"],
            command=lambda _: self._guard(self._choose_extraction),
        )
        self.extraction_menu.pack(fill="x", padx=8, pady=4)
        self.extraction_description_label = ctk.CTkLabel(
            self.extraction_frame,
            textvariable=self.extraction_description,
            wraplength=900,
            justify="left",
        )
        self.extraction_description_label.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(self.operation, text="Output format").grid(row=2, column=0, padx=8, pady=5)
        self.format_menu = ctk.CTkOptionMenu(
            self.operation, variable=self.container, values=["mkv", "mp4"]
        )
        self.format_menu.grid(row=2, column=1, sticky="w", pady=5)
        ctk.CTkLabel(self.operation, text="New output file").grid(row=3, column=0, padx=8, pady=5)
        destination = ctk.CTkEntry(self.operation, textvariable=self.destination)
        destination.grid(row=3, column=1, sticky="ew", pady=5)
        browse = ctk.CTkButton(
            self.operation,
            text="Choose output...",
            command=lambda: self._guard(self.choose_destination),
        )
        browse.grid(row=3, column=2, padx=8)
        ctk.CTkLabel(
            self.operation, textvariable=self.destination_error, wraplength=800, justify="left"
        ).grid(row=4, column=0, columnspan=3, sticky="ew")
        self.suggest_button = ctk.CTkButton(
            self.operation,
            text="Suggest a new filename",
            command=lambda: self._guard(self.suggest_destination),
        )
        self.suggest_button.grid(row=5, column=1, sticky="w", pady=4)
        self.chapter_control = ctk.CTkCheckBox(
            self.operation, text="Preserve primary chapters (remux only)", variable=self.chapters
        )
        self.chapter_control.grid(row=6, column=1, sticky="w", pady=8)
        actions = ctk.CTkFrame(self.operation)
        actions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=6)
        self.review_button = self._button(actions, "Review plan (Ctrl+R)", self.review)
        self.ack_button = self._button(actions, "Acknowledge selected", self.acknowledge)
        self.execute_button = self._button(actions, "Execute...", self.execute, editable=False)
        self.review_text = ctk.CTkTextbox(self.operation, wrap="word", height=180)
        self.review_text.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=4)
        self.warnings = ctk.CTkScrollableFrame(
            self.operation,
            label_text="Risks — review each affected track before acknowledging",
            height=110,
        )
        self.warnings.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=4)
        ctk.CTkCheckBox(
            self.operation,
            text="Show technical plan details",
            variable=self._show_technical,
            command=self._toggle_details,
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=4)
        self.technical_text = ctk.CTkTextbox(self.operation, wrap="word", height=180)
        self.technical_text.grid(row=11, column=0, columnspan=3, sticky="ew")
        self.technical_text.grid_remove()
        self._editing_controls.extend(
            (
                mode,
                self.format_menu,
                destination,
                browse,
                self.chapter_control,
                self.extraction_menu,
                self.suggest_button,
            )
        )

    def _build_execution(self) -> None:
        self.execution.columnconfigure(0, weight=1)
        self.execution.rowconfigure(3, weight=1)
        self.phase_label = ctk.CTkLabel(
            self.execution,
            textvariable=self.phase,
            font=("Segoe UI", 20),
            wraplength=1000,
            justify="left",
        )
        self.phase_label.grid(row=0, column=0, sticky="w", padx=10, pady=12)
        self.progress_bar = ctk.CTkProgressBar(self.execution)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        self.progress_bar.set(0)
        actions = ctk.CTkFrame(self.execution)
        actions.grid(row=2, column=0, sticky="ew", pady=4)
        self.cancel_button = self._button(
            actions, "Cancel operation (Esc)", self.cancel, editable=False
        )
        self.result_text = ctk.CTkTextbox(self.execution, wrap="word")
        self.result_text.grid(row=3, column=0, sticky="nsew", pady=6)
        ctk.CTkCheckBox(
            self.execution,
            text="Show technical result details",
            variable=self._show_result_details,
            command=self._render_result,
        ).grid(row=4, column=0, sticky="w", pady=4)
        self._write(
            self.result_text,
            "Results and validation evidence will appear here. No source files are modified.",
        )

    @staticmethod
    def _write(widget: Any, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _guard(self, action: Callable[[], None]) -> bool:
        if self._destroyed:
            return False
        succeeded = False
        try:
            action()
            succeeded = True
        except ValueError as exc:
            # Only our fixed English controller errors reach this boundary.
            self.controller.status = str(exc)
        except StopIteration:
            self.controller.status = "Select an available track and try again."
        except Exception:
            self.controller.status = (
                "The action could not complete. Check the current selection and try again."
            )
        self._refresh()
        return succeeded

    def open_media(self) -> None:
        if self.controller.worker.busy:
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open media file (local or Windows share)",
            filetypes=[
                ("Media files", "*.mkv *.mp4 *.avi *.mov *.aac *.mp3 *.srt"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._save_metadata()
            self.controller.open_media(path)
            self.tabs.set("1. Media")
            self._refresh()

    def add_subtitles(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.root,
            title="Add validated external SRT files",
            filetypes=[("SubRip subtitles", "*.srt")],
        )
        if paths:
            self._save_metadata()
            self.controller.add_subtitles(tuple(paths))

    def remove_external(self) -> None:
        if self._selected is not None:
            self.controller.remove_external(self._selected)
            self._selected = None
            self._metadata_dirty = False
            self._metadata_fields.clear()
            self.metadata_area.grid_remove()
            self._refresh_tracks()

    def _copy_source_path(self) -> None:
        if self._selected is not None:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(self._selected.source.path))

    def _wrap_media(self, event: object = None) -> None:
        width = max(260, self.media.winfo_width() / self.summary_label._get_widget_scaling() - 40)
        self.summary_label.configure(wraplength=width)
        self.track_details_label.configure(wraplength=width)
        self.metadata_help.configure(wraplength=width)

    def _wrap_window(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self.root:
            return
        width = max(260, (event.width - 90) / self.phase_label._get_widget_scaling())
        self.footer_label.configure(wraplength=width)
        self.phase_label.configure(wraplength=width)
        self.extraction_description_label.configure(wraplength=width)
        for child in self.warnings.winfo_children():
            if isinstance(child, ctk.CTkCheckBox):
                child._text_label.configure(wraplength=max(220, event.width - 160))

    def _scroll_to_focus(self, event: tk.Event[tk.Misc]) -> None:
        widget = event.widget
        if not widget.winfo_viewable():
            return
        for area in (self.media, self.operation):
            if str(widget).startswith(str(area) + "."):
                canvas = area._parent_canvas
                top = widget.winfo_rooty() - canvas.winfo_rooty()
                if top < 0 or top + widget.winfo_height() > canvas.winfo_height():
                    offset = widget.winfo_rooty() - area.winfo_rooty()
                    canvas.yview_moveto(max(0, offset - 8) / max(1, area.winfo_height()))

    def _select_row(self, event: object = None) -> None:
        selected = self.table.selection()
        if not selected or self.controller.worker.busy:
            return
        if selected[0] not in self._rows:
            if self._guard(self._save_metadata):
                self._selected = None
                self.metadata_area.grid_remove()
            return
        reference = self._rows[selected[0]]
        if reference == self._selected:
            return
        if not self._guard(self._save_metadata):
            return
        self._selected = reference
        item = next(s for s in self.controller.intent.selections if s.reference == reference)
        metadata = item.metadata
        source = self.controller.stream(reference)
        self._loading = True
        self.language.set(
            (source.language or "") if metadata.language is None else metadata.language
        )
        self.track_title.set((source.title or "") if metadata.title is None else metadata.title)
        for key, variable in (("default", self.default), ("forced", self.forced)):
            effective = getattr(metadata, key)
            if effective is None:
                effective = bool(dict(source.disposition).get(key, 0))
            variable.set("Yes" if effective else "No")
        self.track_details.set(
            f"{reference.source.path}\nOriginal index {reference.index} · "
            f"{codec_text(source.codec)}"
        )
        self._loading = False
        self._metadata_dirty = False
        self._metadata_fields.clear()
        self.metadata_area.grid()
        if any(t.source == reference.source for t in self.controller.intent.external_tracks):
            self.remove_button.grid()
        else:
            self.remove_button.grid_remove()
        for row, row_reference in self._rows.items():
            if row_reference == reference:
                self.table.selection_set(row)

    def _metadata_changed(self, *args: str) -> None:
        if self._loading or self._selected is None or self.controller.worker.busy:
            return
        self._metadata_dirty = True
        fields = {
            str(self.language): "language",
            str(self.track_title): "title",
            str(self.default): "default",
            str(self.forced): "forced",
        }
        if args and args[0] in fields:
            self._metadata_fields.add(fields[args[0]])
        self.controller.invalidate()
        self._refresh_review()

    def _save_metadata(self) -> None:
        if not self._metadata_dirty or self._selected is None:
            return
        source = self.controller.stream(self._selected)
        previous = next(
            s.metadata for s in self.controller.intent.selections if s.reference == self._selected
        )
        language = self.language.get().strip()
        if (
            language != (source.language or "")
            and language
            and not re.fullmatch(r"[a-z]{3}", language)
        ):
            raise ValueError(
                "Use a lowercase three-letter language code such as eng or spa, or clear it."
            )

        def text_intent(value: str, original: str | None) -> str | None:
            return None if value and value == original else value

        flags = dict(source.disposition)
        self.controller.edit_track(
            self._selected,
            metadata=MetadataIntent(
                language=text_intent(language, source.language)
                if "language" in self._metadata_fields
                else previous.language,
                title=text_intent(self.track_title.get(), source.title)
                if "title" in self._metadata_fields
                else previous.title,
                default=(
                    None
                    if (self.default.get() == "Yes") == bool(flags.get("default", 0))
                    else self.default.get() == "Yes"
                )
                if "default" in self._metadata_fields
                else previous.default,
                forced=(
                    None
                    if (self.forced.get() == "Yes") == bool(flags.get("forced", 0))
                    else self.forced.get() == "Yes"
                )
                if "forced" in self._metadata_fields
                else previous.forced,
            ),
        )
        self._metadata_dirty = False
        self._metadata_fields.clear()
        self._refresh_tracks()

    def reset_metadata(self) -> None:
        if self._selected is None:
            return
        reference = self._selected
        self._metadata_dirty = False
        self._metadata_fields.clear()
        self.controller.edit_track(reference, metadata=MetadataIntent())
        self._selected = None
        self._refresh_tracks()
        self._select_reference(reference)

    def _select_reference(self, reference: StreamReference) -> None:
        row = next((r for r, ref in self._rows.items() if ref == reference), None)
        if row is not None:
            self.table.selection_set(row)
            self.table.see(row)
            self._select_row()

    def toggle(self) -> None:
        if self._selected is not None:
            self._save_metadata()
            item = next(
                s for s in self.controller.intent.selections if s.reference == self._selected
            )
            self.controller.edit_track(self._selected, include=not item.include)
            self._refresh_tracks()

    def move(self, direction: int) -> None:
        if self._selected is not None:
            self._save_metadata()
            self.controller.move(self._selected, direction)
            self._refresh_tracks()

    def extract_selected(self) -> None:
        if self._selected is not None:
            self._save_metadata()
            self.controller.change(extraction_target=self._selected)
            self.mode.set("Extract")
            self.tabs.set("2. Operation")

    def _options_changed(self, *args: str) -> None:
        if self._loading or self.controller.worker.busy:
            return
        self.controller.change(
            mode=cast(Literal["Remux", "Extract"], self.mode.get()),
            container=self.container.get(),
            destination=self.destination.get(),
            preserve_chapters=self.chapters.get(),
        )
        self._refresh_review()
        self._update_formats()
        self._schedule_destination_check()

    def _update_formats(self) -> None:
        values = ["mkv", "mp4"]
        if self.mode.get() == "Extract":
            self.extraction_frame.grid()
            reference = self.controller.intent.extraction_target
            values = []
            if reference is not None:
                source = next(
                    a for a in self.controller.intent.sources if a.source == reference.source
                )
                values = list(ExtractionPlanningService.supported_extensions(source, reference))
                stream = self.controller.stream(reference)
                external = any(
                    t.source == reference.source for t in self.controller.intent.external_tracks
                )
                self.extraction_description.set(
                    "This imported SRT is already an independent file; choose an internal track."
                    if external
                    else f"{reference.source.path}\n{stream.kind.capitalize()} · "
                    f"{language_text(stream.language)} · {stream.title or 'Untitled'} · "
                    f"{codec_text(stream.codec)} · original index {reference.index}\n"
                    + (
                        "Supported subtitle conversion; formatting may change."
                        if stream.codec == "mov_text" and values
                        else "Stream copy; no audio/video encoding."
                        if values
                        else "No tested extraction format. Choose another track or use remux."
                    )
                )
                if external:
                    values = []
            else:
                self.extraction_description.set(
                    "Choose the exact source track. No track is selected automatically."
                )
        else:
            self.extraction_frame.grid_remove()
        self.format_menu.configure(values=values or ["Unsupported selection"])
        desired = (
            self.container.get()
            if self.container.get() in values
            else values[0]
            if values
            else "Unsupported selection"
        )
        if self.container.get() != desired and not self.controller.worker.busy:
            self.container.set(desired)
        format_changed = self._last_format != self.container.get()
        self._last_format = self.container.get()
        if (
            format_changed
            and values
            and self.destination.get()
            and Path(self.destination.get()).suffix.lower() != "." + self.container.get()
            and not self.controller.worker.busy
        ):
            self.destination.set("")
        self.chapter_control.configure(
            state="normal"
            if self.mode.get() == "Remux" and not self.controller.worker.busy
            else "disabled"
        )

    def choose_destination(self) -> None:
        self._update_formats()
        values = cast(list[str], self.format_menu.cget("values"))
        if values == ["Unsupported selection"]:
            self.controller.status = (
                "Select a stream with a supported extraction operation in Media."
            )
            return
        extension = self.container.get() if self.container.get() in values else values[0]
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Choose a new output file (never overwrite)",
            defaultextension="." + extension,
            filetypes=[(f"{v.upper()} output", "*." + v) for v in values],
            confirmoverwrite=False,
            initialfile=self._suggested_filename(),
        )
        if path:
            self.destination.set(path)

    def _suggested_filename(self) -> str:
        if not self.controller.intent.sources:
            return "output." + self.container.get()
        reference = self.controller.intent.extraction_target
        source = (
            reference.source.path
            if self.mode.get() == "Extract" and reference
            else self.controller.intent.sources[0].source.path
        )
        detail = (
            f".track-{reference.index}" if self.mode.get() == "Extract" and reference else ".output"
        )
        return source.stem + detail + "." + self.container.get()

    def suggest_destination(self) -> None:
        if self.format_menu.cget("values") == ["Unsupported selection"]:
            raise ValueError("Choose a track with a supported extraction format first.")
        self.controller.suggest_destination(self._suggested_filename())

    def _schedule_destination_check(self) -> None:
        if self._destination_check_id is not None:
            self.root.after_cancel(self._destination_check_id)
        self._destination_check_id = self.root.after(400, self._check_destination)

    def _check_destination(self) -> None:
        self._destination_check_id = None
        if self.controller.worker.busy or self.controller.recovery_required or self._destroyed:
            return
        if self.destination.get():
            self.controller.check_destination(self.container.get())
            self._refresh()

    def _choose_extraction(self) -> None:
        reference = self._extraction_rows.get(self.extraction_selection.get())
        self._save_metadata()
        self.controller.change(extraction_target=reference, destination="")
        self.destination.set("")
        self._update_formats()
        self._refresh_review()

    def _toggle_details(self) -> None:
        if self._show_technical.get():
            self.technical_text.grid()
        else:
            self.technical_text.grid_remove()

    def _render_result(self) -> None:
        result = self.controller.result
        if result is None:
            self._write(
                self.result_text,
                self.controller.error or "Awaiting results from the current operation.",
            )
            return
        text = result_text(result)
        if not self._show_result_details.get():
            lines = text.splitlines()[:4]
            lines.extend(f"{d.code}: {d.message}" for d in result.diagnostics)
            if result.validation:
                lines.extend(
                    f"{c.code}: {c.detail}" for c in result.validation.checks if c.status == "error"
                )
            if not result.cleanup_complete:
                lines.append(
                    "Recovery required: inspect retained staging and verify process termination "
                    "before cleanup. Do not delete unknown files."
                )
            text = "\n".join(lines)
        self._write(self.result_text, text)

    def review(self) -> None:
        self._save_metadata()
        self.controller.generate_plan()
        self.tabs.set("2. Operation")

    def acknowledge(self) -> None:
        if self.controller.plan is not None:
            codes = frozenset(
                code for code, variable in self._warning_vars.items() if variable.get()
            )
            self.controller.acknowledge(codes, self.controller.plan.revision)

    def execute(self) -> None:
        if not self.controller.can_execute or self.controller.plan is None:
            return
        revision = self.controller.plan.revision
        if messagebox.askyesno(
            "Confirm reviewed operation",
            "Execute this exact reviewed plan?\n\nDestination: "
            f"{self.controller.plan.destination_path}"
            "\n\nOriginal sources are preserved. Existing output files are never overwritten.",
            parent=self.root,
            default="no",
        ):
            self.controller.execute(revision)
            self._execution_started = time.monotonic()
            self._execution_elapsed = None
            self._write(self.result_text, "Operation running. Awaiting validated results.")
            self.tabs.set("3. Execution")
            self._refresh()

    def cancel(self) -> None:
        self.controller.cancel()
        self._refresh()

    def sort_table(self, column: str) -> None:
        for group in self.table.get_children():
            rows = sorted(
                self.table.get_children(group),
                key=lambda row: self.table.set(row, column).casefold(),
            )
            for position, row in enumerate(rows):
                self.table.move(row, group, position)

    def _refresh_tracks(self) -> None:
        self.table.delete(*self.table.get_children())
        self._rows.clear()
        counters: dict[str, int] = {}
        originals: dict[StreamReference, int] = {}
        for asset in self.controller.intent.sources:
            for stream in asset.streams:
                originals[StreamReference(asset.source, stream.index)] = 1 + sum(
                    1 for ref in originals if self.controller.stream(ref).kind == stream.kind
                )
        self._extraction_rows.clear()
        groups = {
            "video": "Video",
            "audio": "Audio",
            "subtitle": "Subtitles",
            "attachment": "Attachments",
            "data": "Data",
            "unknown": "Other",
        }
        for kind, label in groups.items():
            if any(
                self.controller.stream(s.reference).kind == kind
                for s in self.controller.intent.selections
            ):
                self.table.insert("", "end", iid="group-" + kind, text=label, open=True)
        for i, selection in enumerate(self.controller.intent.selections):
            reference = selection.reference
            stream = self.controller.stream(reference)
            if selection.include:
                counters[stream.kind] = counters.get(stream.kind, 0) + 1
            metadata = selection.metadata
            row = f"track-{i}"
            self._rows[row] = reference
            flags = dict(stream.disposition)
            language = stream.language if metadata.language is None else metadata.language
            title = stream.title if metadata.title is None else metadata.title
            default = (
                bool(flags.get("default", 0)) if metadata.default is None else metadata.default
            )
            forced = bool(flags.get("forced", 0)) if metadata.forced is None else metadata.forced
            order = counters.get(stream.kind, 0) if selection.include else None
            changes = (
                not selection.include,
                (language or "") != (stream.language or ""),
                (title or "") != (stream.title or ""),
                default != bool(flags.get("default", 0)),
                forced != bool(flags.get("forced", 0)),
                selection.include and order != originals[reference],
            )

            def marked(value: object, changed: bool) -> str:
                return ("* " if changed else "") + str(value)

            label = (
                f"{reference.source.path.name} · {stream.kind} · {language_text(language)} · "
                f"{title or 'Untitled'} · {stream.codec or 'unknown'} · index {reference.index}"
            )
            self._extraction_rows[label] = reference
            self.table.insert(
                "group-" + stream.kind,
                "end",
                iid=row,
                values=(
                    marked("Yes" if selection.include else "No", changes[0]),
                    stream.index,
                    stream.kind,
                    codec_text(stream.codec),
                    marked(language_text(language), changes[1]),
                    marked(title or "", changes[2]),
                    marked("Yes" if default else "No", changes[3]),
                    marked("Yes" if forced else "No", changes[4]),
                    marked(order if order is not None else "—", changes[5]),
                    reference.source.path.name,
                ),
                tags=("changed",) if any(changes) else (),
            )
            if reference == self._selected:
                self.table.selection_set(row)
        self.extraction_menu.configure(values=["Choose a source track", *self._extraction_rows])
        target = self.controller.intent.extraction_target
        self.extraction_selection.set(
            next(
                (label for label, ref in self._extraction_rows.items() if ref == target),
                "Choose a source track",
            )
        )
        self._rendered_intent = self.controller.intent

    def _refresh_review(self) -> None:
        plan = self.controller.plan
        revision = plan.revision if plan is not None else None
        acknowledged = plan.effective_acknowledged_warnings if plan is not None else frozenset()
        if revision != self._plan_revision or acknowledged != self._review_ack:
            self._plan_revision = revision
            self._review_ack = acknowledged
            self._write(
                self.review_text,
                review_summary(plan)
                if plan is not None
                else "Generate a plan to review current intent. Edits invalidate previous review.",
            )
            self._write(
                self.technical_text, plan_text(plan) if plan is not None else "No current plan."
            )
            for child in self.warnings.winfo_children():
                if isinstance(child, ctk.CTkCheckBox):
                    # Drop Tk variables on the main thread before destroyed widget cycles
                    # can be collected by an execution worker.
                    child.configure(variable=None)
                child.destroy()
            self._warning_vars.clear()
            if plan is not None:
                codes = sorted({issue.code for issue in plan.issues if issue.severity == "warning"})
                for code in codes:
                    variable = tk.BooleanVar(value=code in plan.effective_acknowledged_warnings)
                    count = sum(issue.code == code for issue in plan.issues)
                    occurrences = [issue for issue in plan.issues if issue.code == code]
                    impact = (
                        "Subtitle conversion"
                        if "SUBTITLE" in code
                        else "Metadata"
                        if "METADATA" in code or "LANGUAGE" in code or "DISPOSITION" in code
                        else "Content and compatibility"
                    )
                    details = "\n".join(
                        issue.message
                        + (f" [track {issue.reference.index}]" if issue.reference else "")
                        for issue in occurrences
                    )
                    check = ctk.CTkCheckBox(
                        self.warnings,
                        text=f"{impact}: {details}\nAcknowledge all {count} occurrence(s) ({code})",
                        variable=variable,
                    )
                    check.pack(anchor="w", padx=8, pady=4)
                    check._text_label.configure(wraplength=max(220, self.root.winfo_width() - 160))
                    check._canvas.configure(takefocus=True)
                    self._bind_keyboard(check)
                    self._warning_vars[code] = variable
        self.execute_button.configure(
            state="normal"
            if self.controller.can_execute and not self._metadata_dirty
            else "disabled"
        )
        self.ack_button.configure(
            state="normal" if plan is not None and not self.controller.worker.busy else "disabled"
        )
        if self._warning_vars:
            self.warnings.grid()
        else:
            self.warnings.grid_remove()

    def _refresh(self) -> None:
        self._loading = True
        self.mode.set(self.controller.intent.mode)
        self.container.set(self.controller.intent.container)
        self.destination.set(self.controller.intent.destination)
        self.chapters.set(self.controller.intent.preserve_chapters)
        self._loading = False
        self.status.set(self.controller.status)
        self.destination_error.set(self.controller.destination_feedback)
        busy = self.controller.worker.busy
        for control in self._editing_controls:
            self._state(
                control, "disabled" if busy or self.controller.recovery_required else "normal"
            )
        self._state(
            self.cancel_button,
            "normal" if busy and self.controller.worker.control is not None else "disabled",
        )
        self._refresh_review()
        self._update_formats()
        if self.controller.intent.sources:
            self.operation_empty.pack_forget()
            self.operation.pack(fill="both", expand=True)
            asset = self.controller.intent.sources[0]
            identity = (asset.source, self.controller.inspection_revision)
            if identity != self._source_identity:
                self._source_identity = identity
                self._selected = None
                self._metadata_dirty = False
                self._metadata_fields.clear()
                self.metadata_area.grid_remove()
                self._refresh_tracks()
            self.track_frame.grid()
            self.track_controls.grid()
            self.add_button.pack(side="left", padx=4, pady=5)
            if not self._expanded:
                self._expanded = True
                if (self.root.winfo_width(), self.root.winfo_height()) == getattr(
                    self, "_initial_size", None
                ):
                    screen_width, screen_height = self._screen_bounds()
                    self.root.geometry(f"{min(1180, screen_width)}x{min(850, screen_height)}")
            counts: dict[str, int] = {}
            dimensions = []
            for stream in asset.streams:
                counts[stream.kind] = counts.get(stream.kind, 0) + 1
                if stream.properties.width is not None:
                    dimensions.append(f"{stream.properties.width}×{stream.properties.height}")
            self.summary.set(
                f"{asset.source.path.name}\n{asset.source.path}\n"
                f"Container: {asset.format.long_name or asset.format.name or 'Unknown'} · "
                f"Duration: {clock_text(asset.format.duration_seconds)} · "
                f"Size: {size_text(asset.source.size_bytes)} · "
                f"Resolution: {' / '.join(dimensions) or 'Unknown'}\n"
                + ", ".join(
                    f"{counts.get(kind, 0)} {kind}" for kind in ("video", "audio", "subtitle")
                )
                + " · Inspection does not guarantee output compatibility."
            )
        else:
            self.operation.pack_forget()
            self.operation_empty.pack(fill="both", expand=True, padx=12, pady=12)
            self.track_frame.grid_remove()
            self.track_controls.grid_remove()
            self.metadata_area.grid_remove()
            self.add_button.pack_forget()
            self.summary.set(
                "Open Media to inspect tracks. Supports local and trusted Windows share inputs."
            )
        if self.controller.result is not None:
            if self._execution_started is not None and self._execution_elapsed is None:
                self._execution_elapsed = time.monotonic() - self._execution_started
            self._render_result()
        elif self.controller.error is not None:
            self._write(self.result_text, self.controller.error)
        elif busy and self.controller.worker.control is not None:
            self._write(self.result_text, "Operation running. Awaiting validated results.")
        event = self.controller.progress
        if event is not None:
            self.phase.set(
                event.phase.replace("_", " ").capitalize()
                + (
                    f" — {event.percent:.1f}%"
                    if event.percent is not None and not event.terminal
                    else ""
                    if event.terminal
                    else " — progress unavailable"
                )
                + (
                    f" · Media position {clock_text(event.processed_seconds)}"
                    if event.processed_seconds is not None
                    else ""
                )
            )
            if self.controller.worker.control is not None or self.controller.result is not None:
                self.phase.set(
                    f"{self.mode.get()}: {Path(self.destination.get()).name}\n" + self.phase.get()
                )
            if (
                self._execution_started is not None
                and self.controller.worker.control is not None
                or event.terminal
                and self._execution_started is not None
            ):
                elapsed = (
                    self._execution_elapsed
                    if self._execution_elapsed is not None
                    else time.monotonic() - self._execution_started
                )
                self.phase.set(self.phase.get() + f" · Elapsed {clock_text(elapsed)}")
            mode = (
                "determinate"
                if event.determinate
                else "indeterminate"
                if busy and not event.terminal
                else "idle"
            )
            self._set_progress_mode(mode)
            if event.determinate:
                self.progress_bar.set((event.percent or 0) / 100)
        else:
            self.phase.set("No operation running")
            self._set_progress_mode("idle")
            self.progress_bar.set(0)

    @staticmethod
    def _state(widget: Any, state: str) -> None:
        if widget.cget("state") != state:
            widget.configure(state=state)

    def _set_progress_mode(self, mode: str) -> None:
        if mode == self._progress_mode:
            return
        self.progress_bar.stop()
        self._progress_mode = mode
        self.progress_bar.configure(
            mode="indeterminate" if mode == "indeterminate" else "determinate"
        )
        if mode == "indeterminate":
            self.progress_bar.start()
        elif mode == "idle":
            self.progress_bar.set(0)

    def _poll(self) -> None:
        if self._destroyed:
            return
        previous_sources = len(self.controller.intent.sources)
        if self.controller.poll():
            # Reset a successfully replaced session before rendering rows with reused IDs.
            self._refresh()
            if self._rendered_intent is not self.controller.intent:
                self._refresh_tracks()
            if len(self.controller.intent.sources) > previous_sources and previous_sources:
                source = self.controller.intent.sources[-1]
                self._select_reference(StreamReference(source.source, source.streams[0].index))
        if (
            self.controller.worker.control is not None
            and int(time.monotonic()) != self._last_elapsed_tick
        ):
            self._last_elapsed_tick = int(time.monotonic())
            self._refresh()
        appearance = ctk.get_appearance_mode()
        if appearance != self._appearance:
            self._appearance = appearance
            index = 1 if appearance == "Dark" else 0

            def color(widget: str, field: str) -> str:
                value = ctk.ThemeManager.theme[widget][field]
                return cast(str, value[index] if isinstance(value, (list, tuple)) else value)

            style = ttk.Style(self.root)
            style.theme_use("clam")
            style.configure(
                "Treeview",
                background=color("CTkFrame", "fg_color"),
                fieldbackground=color("CTkFrame", "fg_color"),
                foreground=color("CTkLabel", "text_color"),
                rowheight=max(26, round(self.root.winfo_fpixels("1i") / 96 * 26)),
            )
            style.map("Treeview", background=[("selected", color("CTkButton", "fg_color"))])
        if self.controller.safe_to_close:
            self.destroy()
            return
        self._poll_id = self.root.after(60, self._poll)

    def close(self) -> None:
        if self.controller.worker.busy:
            cancel = messagebox.askyesno(
                "Operation in progress",
                "Cancel and close after the backend reports safe termination?"
                "\n\nChoose No to keep working.",
                parent=self.root,
                default="no",
            )
            self.controller.request_close(cancel)
            self._refresh()
        elif self.controller.request_close(False):
            self.destroy()
        else:
            self.tabs.set("3. Execution")
            self._refresh()
            messagebox.showwarning("Recovery information", self.controller.status, parent=self.root)

    def destroy(self) -> None:
        if self.controller.worker.busy:
            raise ValueError("Cannot destroy the window while a backend worker is active.")
        self._destroyed = True
        self.controller.closed = True
        if self._destination_check_id is not None:
            self.root.after_cancel(self._destination_check_id)
            self._destination_check_id = None
        self.root.after_cancel(self._poll_id)
        self.progress_bar.stop()
        # This application owns one Tk interpreter. Cancel its toolkit timers too,
        # so an update already in progress cannot call destroyed widget commands.
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            # Leave command deletion to the widget that registered it.
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

"""Main-thread desktop presentation; application services remain behind the controller."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk
from typing import Any, Literal, cast

import customtkinter as ctk

from mediatrack_forge.application.extraction import ExtractionPlanningService
from mediatrack_forge.domain.planning import MetadataIntent, StreamReference
from mediatrack_forge.ui.presentation_model import DesktopController, plan_text, result_text


class DesktopWindow:
    def __init__(self, controller: DesktopController | None = None) -> None:
        ctk.set_appearance_mode("system")
        self.root = cast(tk.Tk, ctk.CTk())
        self.root.title("MediaTrack Forge")
        self.root.geometry("1180x850")
        self.root.minsize(800, 640)
        self.controller = controller if controller is not None else DesktopController()
        self._loading = True
        self._destroyed = False
        self._selected: StreamReference | None = None
        self._rows: dict[str, StreamReference] = {}
        self._metadata_dirty = False
        self._plan_revision: str | None = None
        self._review_ack: frozenset[str] = frozenset()
        self._appearance = ""
        self._warning_vars: dict[str, tk.BooleanVar] = {}
        self._editing_controls: list[Any] = []
        self.mode = tk.StringVar(value="Remux")
        self.container = tk.StringVar(value="mkv")
        self.destination = tk.StringVar()
        self.chapters = tk.BooleanVar(value=True)
        self.language_mode = tk.StringVar(value="Keep original")
        self.language = tk.StringVar()
        self.title_mode = tk.StringVar(value="Keep original")
        self.track_title = tk.StringVar()
        self.default = tk.StringVar(value="Keep original")
        self.forced = tk.StringVar(value="Keep original")
        self.status = tk.StringVar(value=self.controller.status)
        self.summary = tk.StringVar(value="No media selected. Local files only.")
        self.phase = tk.StringVar(value="No operation running")
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self.root)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(header, text="MediaTrack Forge", font=("Segoe UI", 24, "bold")).pack(
            side="left", padx=16, pady=8
        )
        ctk.CTkLabel(header, text="Inspect · select · review · execute").pack(side="right", padx=16)
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self.media = self.tabs.add("Media")
        self.operation = self.tabs.add("Operation")
        self.execution = self.tabs.add("Execution")
        self._build_media()
        self._build_operation()
        self._build_execution()
        self._enable_keyboard(self.root)
        ctk.CTkLabel(self.root, textvariable=self.status, wraplength=1000, anchor="w").grid(
            row=2, column=0, sticky="ew", padx=16, pady=8
        )
        for variable in (self.mode, self.container, self.destination, self.chapters):
            variable.trace_add("write", self._options_changed)
        for variable in (
            self.language_mode,
            self.language,
            self.title_mode,
            self.track_title,
            self.default,
            self.forced,
        ):
            variable.trace_add("write", self._metadata_changed)
        self.root.bind("<Control-o>", lambda _: self._guard(self.open_media))
        self.root.bind("<Control-r>", lambda _: self._guard(self.review))
        self.root.bind("<Control-Return>", lambda _: self._guard(self.execute))
        self.root.bind("<Escape>", lambda _: self._guard(self.cancel))
        self.root.bind("<Alt-Key-1>", lambda _: self.tabs.set("Media"))
        self.root.bind("<Alt-Key-2>", lambda _: self.tabs.set("Operation"))
        self.root.bind("<Alt-Key-3>", lambda _: self.tabs.set("Execution"))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._loading = False
        self._refresh()
        self._poll_id = self.root.after(60, self._poll)
        self.open_button.focus_set()

    def _button(
        self, parent: Any, text: str, command: Callable[[], None], *, editable: bool = True
    ) -> Any:
        button = ctk.CTkButton(parent, text=text, command=lambda: self._guard(command), width=130)
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

        for key in ("<space>", "<Return>", "<Left>", "<Right>"):
            widget._canvas.bind(key, activate)
        widget._canvas.bind("<FocusIn>", lambda _: widget._canvas.configure(highlightthickness=2))
        widget._canvas.bind("<FocusOut>", lambda _: widget._canvas.configure(highlightthickness=0))

    def _build_media(self) -> None:
        self.media.columnconfigure(0, weight=1)
        self.media.rowconfigure(2, weight=3, minsize=100)
        self.media.rowconfigure(4, weight=1, minsize=80)
        actions = ctk.CTkFrame(self.media)
        actions.grid(row=0, column=0, sticky="ew")
        self.open_button = self._button(actions, "Open Media (Ctrl+O)", self.open_media)
        self._button(actions, "Add SRT files", self.add_subtitles)
        self._button(actions, "Remove external", self.remove_external)
        ctk.CTkLabel(
            self.media, textvariable=self.summary, anchor="w", justify="left", wraplength=1000
        ).grid(row=1, column=0, sticky="ew", padx=4, pady=8)
        frame = ttk.Frame(self.media)
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
        self.table = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        headings = (
            "Included",
            "Original index",
            "Kind",
            "Codec",
            "Language",
            "Title",
            "Default",
            "Forced",
            "Kind order",
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
        controls.grid(row=3, column=0, sticky="ew", pady=6)
        self._button(controls, "Include / exclude", self.toggle)
        self._button(controls, "Move up", lambda: self.move(-1))
        self._button(controls, "Move down", lambda: self.move(1))
        self._button(controls, "Use for extraction", self.extract_selected)
        metadata_area = ctk.CTkScrollableFrame(self.media, height=150)
        metadata_area.grid(row=4, column=0, sticky="nsew")
        metadata_area.columnconfigure(0, weight=1)
        editor = ctk.CTkFrame(metadata_area)
        editor.grid(row=0, column=0, sticky="ew")
        editor.columnconfigure(2, weight=1)
        for row, label, mode, value in (
            (0, "Language", self.language_mode, self.language),
            (1, "Title", self.title_mode, self.track_title),
        ):
            ctk.CTkLabel(editor, text=label).grid(row=row, column=0, padx=8, pady=4)
            menu = ctk.CTkOptionMenu(editor, variable=mode, values=["Keep original", "Set value"])
            menu.grid(row=row, column=1, padx=4, pady=4)
            entry = ctk.CTkEntry(editor, textvariable=value)
            entry.grid(row=row, column=2, sticky="ew", padx=8, pady=4)
            self._editing_controls.extend((menu, entry))
        flags = ctk.CTkFrame(metadata_area)
        flags.grid(row=1, column=0, sticky="ew", pady=5)
        for label, value in (("Default", self.default), ("Forced", self.forced)):
            ctk.CTkLabel(flags, text=label).pack(side="left", padx=8)
            menu = ctk.CTkOptionMenu(
                flags, variable=value, values=["Keep original", "On", "Off"], width=140
            )
            menu.pack(side="left", padx=4)
            self._editing_controls.append(menu)
        self._button(flags, "Apply metadata", self._save_metadata)
        ctk.CTkLabel(
            metadata_area,
            text="Set value + empty text clears a tag. On/Off changes a flag. "
            "Order changes stay within each kind.",
            wraplength=1000,
        ).grid(row=2, column=0, sticky="ew", pady=4)

    def _build_operation(self) -> None:
        self.operation.columnconfigure(1, weight=1)
        self.operation.rowconfigure(5, weight=3, minsize=100)
        self.operation.rowconfigure(6, weight=1, minsize=80)
        ctk.CTkLabel(self.operation, text="Operation").grid(row=0, column=0, padx=8, pady=5)
        mode = ctk.CTkOptionMenu(self.operation, variable=self.mode, values=["Remux", "Extract"])
        mode.grid(row=0, column=1, sticky="w", pady=5)
        ctk.CTkLabel(self.operation, text="Output format").grid(row=1, column=0, padx=8, pady=5)
        self.format_menu = ctk.CTkOptionMenu(
            self.operation, variable=self.container, values=["mkv", "mp4"]
        )
        self.format_menu.grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkLabel(self.operation, text="Destination").grid(row=2, column=0, padx=8, pady=5)
        destination = ctk.CTkEntry(self.operation, textvariable=self.destination)
        destination.grid(row=2, column=1, sticky="ew", pady=5)
        browse = ctk.CTkButton(
            self.operation,
            text="Choose output...",
            command=lambda: self._guard(self.choose_destination),
        )
        browse.grid(row=2, column=2, padx=8)
        self.chapter_control = ctk.CTkCheckBox(
            self.operation, text="Preserve primary chapters (remux only)", variable=self.chapters
        )
        self.chapter_control.grid(row=3, column=1, sticky="w", pady=8)
        actions = ctk.CTkFrame(self.operation)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=6)
        self.review_button = self._button(actions, "Review plan (Ctrl+R)", self.review)
        self.ack_button = self._button(actions, "Acknowledge selected", self.acknowledge)
        self.execute_button = self._button(actions, "Execute...", self.execute, editable=False)
        self.review_text = ctk.CTkTextbox(self.operation, wrap="word")
        self.review_text.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=4)
        self.warnings = ctk.CTkScrollableFrame(
            self.operation,
            label_text="Warnings — select each code only after reviewing all its occurrences",
            height=140,
        )
        self.warnings.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=4)
        self._editing_controls.extend(
            (mode, self.format_menu, destination, browse, self.chapter_control)
        )

    def _build_execution(self) -> None:
        self.execution.columnconfigure(0, weight=1)
        self.execution.rowconfigure(3, weight=1)
        ctk.CTkLabel(self.execution, textvariable=self.phase, font=("Segoe UI", 20)).grid(
            row=0, column=0, sticky="w", padx=10, pady=12
        )
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

    def _guard(self, action: Callable[[], None]) -> None:
        if self._destroyed:
            return
        try:
            action()
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

    def open_media(self) -> None:
        if self.controller.worker.busy:
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open local media",
            filetypes=[
                ("Media files", "*.mkv *.mp4 *.avi *.mov *.aac *.mp3 *.srt"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._selected = None
            self._metadata_dirty = False
            self.controller.open_media(path)
            self.tabs.set("Media")
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
            self._refresh_tracks()

    def _select_row(self, event: object = None) -> None:
        selected = self.table.selection()
        if not selected or self.controller.worker.busy:
            return
        reference = self._rows[selected[0]]
        if reference == self._selected:
            return
        self._guard(self._save_metadata)
        self._selected = reference
        item = next(s for s in self.controller.intent.selections if s.reference == reference)
        metadata = item.metadata
        source = self.controller.stream(reference)
        self._loading = True
        self.language_mode.set("Keep original" if metadata.language is None else "Set value")
        self.language.set(
            (source.language or "") if metadata.language is None else metadata.language
        )
        self.title_mode.set("Keep original" if metadata.title is None else "Set value")
        self.track_title.set((source.title or "") if metadata.title is None else metadata.title)
        self.default.set(
            "Keep original" if metadata.default is None else "On" if metadata.default else "Off"
        )
        self.forced.set(
            "Keep original" if metadata.forced is None else "On" if metadata.forced else "Off"
        )
        self._loading = False
        self._metadata_dirty = False
        for row, row_reference in self._rows.items():
            if row_reference == reference:
                self.table.selection_set(row)

    def _metadata_changed(self, *args: str) -> None:
        if self._loading or self._selected is None or self.controller.worker.busy:
            return
        self._metadata_dirty = True
        self.controller.invalidate()
        self._refresh_review()

    def _save_metadata(self) -> None:
        if not self._metadata_dirty or self._selected is None:
            return
        flags = {"Keep original": None, "On": True, "Off": False}
        self.controller.edit_track(
            self._selected,
            metadata=MetadataIntent(
                language=None
                if self.language_mode.get() == "Keep original"
                else self.language.get(),
                title=None if self.title_mode.get() == "Keep original" else self.track_title.get(),
                default=flags[self.default.get()],
                forced=flags[self.forced.get()],
            ),
        )
        self._metadata_dirty = False
        self._refresh_tracks()

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
            self.tabs.set("Operation")

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

    def _update_formats(self) -> None:
        values = ["mkv", "mp4"]
        if self.mode.get() == "Extract":
            reference = self.controller.intent.extraction_target
            values = []
            if reference is not None:
                source = next(
                    a for a in self.controller.intent.sources if a.source == reference.source
                )
                values = list(ExtractionPlanningService.supported_extensions(source, reference))
        self.format_menu.configure(values=values or ["Unsupported selection"])
        if values and self.container.get() not in values and not self.controller.worker.busy:
            self.container.set(values[0])
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
            confirmoverwrite=True,
        )
        if path:
            self.destination.set(path)

    def review(self) -> None:
        self._save_metadata()
        self.controller.generate_plan()
        self.tabs.set("Operation")

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
            self.tabs.set("Execution")

    def cancel(self) -> None:
        self.controller.cancel()
        self._refresh()

    def sort_table(self, column: str) -> None:
        rows = sorted(
            self.table.get_children(), key=lambda row: self.table.set(row, column).casefold()
        )
        for position, row in enumerate(rows):
            self.table.move(row, "", position)

    def _refresh_tracks(self) -> None:
        self.table.delete(*self.table.get_children())
        self._rows.clear()
        counters: dict[str, int] = {}
        external = {t.source for t in self.controller.intent.external_tracks}
        for i, selection in enumerate(self.controller.intent.selections):
            reference = selection.reference
            stream = self.controller.stream(reference)
            if selection.include:
                counters[stream.kind] = counters.get(stream.kind, 0) + 1
            metadata = selection.metadata
            row = f"track-{i}"
            self._rows[row] = reference
            flags = dict(stream.disposition)
            self.table.insert(
                "",
                "end",
                iid=row,
                values=(
                    "Yes" if selection.include else "No (explicit)",
                    stream.index,
                    stream.kind,
                    stream.codec or "Unknown",
                    stream.language if metadata.language is None else metadata.language,
                    stream.title if metadata.title is None else metadata.title,
                    flags.get("default", "Unknown")
                    if metadata.default is None
                    else int(metadata.default),
                    flags.get("forced", "Unknown")
                    if metadata.forced is None
                    else int(metadata.forced),
                    counters[stream.kind] if selection.include else "—",
                    ("External: " if reference.source in external else "Primary: ")
                    + reference.source.path.name,
                ),
            )
            if reference == self._selected:
                self.table.selection_set(row)

    def _refresh_review(self) -> None:
        plan = self.controller.plan
        revision = plan.revision if plan is not None else None
        acknowledged = plan.effective_acknowledged_warnings if plan is not None else frozenset()
        if revision != self._plan_revision or acknowledged != self._review_ack:
            self._plan_revision = revision
            self._review_ack = acknowledged
            self._write(
                self.review_text,
                plan_text(plan)
                if plan is not None
                else "Generate a plan to review current intent. Edits invalidate previous review.",
            )
            for child in self.warnings.winfo_children():
                child.destroy()
            self._warning_vars.clear()
            if plan is not None:
                codes = sorted({issue.code for issue in plan.issues if issue.severity == "warning"})
                for code in codes:
                    variable = tk.BooleanVar(value=code in plan.effective_acknowledged_warnings)
                    count = sum(issue.code == code for issue in plan.issues)
                    check = ctk.CTkCheckBox(
                        self.warnings,
                        text=f"{code} — acknowledge all {count} displayed occurrence(s)",
                        variable=variable,
                    )
                    check.pack(anchor="w", padx=8, pady=4)
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

    def _refresh(self) -> None:
        self._loading = True
        self.mode.set(self.controller.intent.mode)
        self.container.set(self.controller.intent.container)
        self.destination.set(self.controller.intent.destination)
        self.chapters.set(self.controller.intent.preserve_chapters)
        self._loading = False
        self.status.set(self.controller.status)
        busy = self.controller.worker.busy
        for control in self._editing_controls:
            control.configure(
                state="disabled" if busy or self.controller.recovery_required else "normal"
            )
        self.cancel_button.configure(
            state="normal" if busy and self.controller.worker.control is not None else "disabled"
        )
        self._refresh_review()
        self._update_formats()
        if self.controller.intent.sources:
            asset = self.controller.intent.sources[0]
            counts: dict[str, int] = {}
            dimensions = []
            for stream in asset.streams:
                counts[stream.kind] = counts.get(stream.kind, 0) + 1
                if stream.properties.width is not None:
                    dimensions.append(f"{stream.properties.width}×{stream.properties.height}")
            self.summary.set(
                f"{asset.source.path}\n{asset.format.name} · duration "
                f"{asset.format.duration_seconds or 'unknown'} s "
                f"· {asset.source.size_bytes:,} bytes · {' / '.join(dimensions)}\n"
                + ", ".join(f"{n} {kind}" for kind, n in counts.items())
                + " · Inspection does not guarantee output compatibility."
            )
        else:
            self.summary.set(
                "No media selected. Opening a new primary clears external sources and review."
            )
        if self.controller.result is not None:
            self._write(self.result_text, result_text(self.controller.result))
        elif self.controller.error is not None:
            self._write(self.result_text, self.controller.error)
        event = self.controller.progress
        if event is not None:
            self.phase.set(
                event.phase.replace("_", " ").capitalize()
                + (f" — {event.percent:.1f}%" if event.percent is not None else " — indeterminate")
                + (
                    f" · {event.processed_seconds:.2f} s processed"
                    if event.processed_seconds is not None
                    else ""
                )
            )
            if event.determinate:
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                self.progress_bar.set((event.percent or 0) / 100)
            elif busy:
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start()
            else:
                self.progress_bar.stop()

    def _poll(self) -> None:
        if self._destroyed:
            return
        if self.controller.poll():
            self._refresh_tracks()
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
            self.tabs.set("Execution")
            self._refresh()
            messagebox.showwarning("Recovery information", self.controller.status, parent=self.root)

    def destroy(self) -> None:
        if self.controller.worker.busy:
            raise ValueError("Cannot destroy the window while a backend worker is active.")
        self._destroyed = True
        self.controller.closed = True
        self.root.after_cancel(self._poll_id)
        self.progress_bar.stop()
        # This application owns one Tk interpreter. Cancel its toolkit timers too,
        # so an update already in progress cannot call destroyed widget commands.
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            # Leave command deletion to the widget that registered it.
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

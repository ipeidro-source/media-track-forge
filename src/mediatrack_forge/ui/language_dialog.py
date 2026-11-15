"""Small native searchable language picker; returns codes, never arbitrary text."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from mediatrack_forge.ui.languages import language_choices


class LanguageDialog:
    def __init__(
        self, parent: tk.Tk, original: str, selected: str, choose: Callable[[str], None]
    ) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("Select language")
        self.window.transient(parent)
        self.window.geometry("420x380")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(2, weight=1)
        ttk.Label(self.window, text="Search by language name or three-letter code").grid(
            row=0, column=0, sticky="w", padx=12, pady=8
        )
        self.search = ttk.Entry(self.window)
        self.search.grid(row=1, column=0, sticky="ew", padx=12)
        self.list = tk.Listbox(self.window, exportselection=False)
        self.list.grid(row=2, column=0, sticky="nsew", padx=(12, 0), pady=8)
        scroll = ttk.Scrollbar(self.window, command=self.list.yview)
        scroll.grid(row=2, column=1, sticky="ns", pady=8)
        self.list.configure(yscrollcommand=scroll.set)
        self.original = original
        self.choose = choose
        self.choices: list[tuple[str, str]] = []
        ttk.Button(self.window, text="Select language", command=self.accept).grid(
            row=3, column=0, sticky="e", padx=12, pady=8
        )
        self.search.bind("<KeyRelease>", lambda _: self.refresh())
        self.search.bind("<Down>", self.focus_list)
        self.window.bind("<Return>", lambda _: self.accept())
        self.window.bind("<Escape>", lambda _: self.window.destroy())
        self.list.bind("<Double-Button-1>", lambda _: self.accept())
        self.refresh()
        for index, (code, _) in enumerate(self.choices):
            if code == selected:
                self.list.selection_clear(0, "end")
                self.list.selection_set(index)
                self.list.see(index)
        self.window.grab_set()
        self.search.focus_set()

    def refresh(self) -> None:
        self.choices = language_choices(self.search.get(), self.original)
        self.list.delete(0, "end")
        for _, label in self.choices:
            self.list.insert("end", label)
        if self.choices:
            self.list.selection_set(0)

    def focus_list(self, event: object = None) -> str:
        self.list.focus_set()
        return "break"

    def accept(self) -> None:
        selected = self.window.tk.splitlist(self.list.tk.call(str(self.list), "curselection"))
        if selected:
            self.choose(self.choices[int(selected[0])][0])
            self.window.destroy()

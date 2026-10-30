"""Collapsible ASCII file tree matching USRDIR.tree.html presentation and colourisation."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

TREE_BG = "#1e1e1e"
TREE_FG = "#c9d1d9"
DARK_SURFACE = "#181818"
DARK_SELECT = "#264f78"
COLOR_DUPLICATE = "#e3b341"
COLOR_UNIQUE = "#56d879"
COLOR_EMPTY = "#ff7b72"
COLOR_UNKNOWN = "#b0bac5"
COLOR_TAGS = (
    "duplicate",
    "unique",
    "empty",
    "unknown",
    "asset_supported",
    "asset_partial",
    "asset_hex_only",
    "asset_unknown",
)


def set_dark_titlebar(window):
    """Enable native Windows dark title bar when available."""
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def style_dark_text_widget(widget, **extra):
    """Apply dark mode styling to a tk.Text widget."""
    cfg = {
        "bg": DARK_SURFACE,
        "fg": TREE_FG,
        "insertbackground": TREE_FG,
        "selectbackground": DARK_SELECT,
        "selectforeground": "#f0f4f8",
        "inactiveselectbackground": DARK_SELECT,
        "relief": tk.FLAT,
        "borderwidth": 0,
        "highlightthickness": 1,
        "highlightbackground": "#2a2a2a",
        "highlightcolor": "#3a5a8c",
    }
    cfg.update(extra)
    widget.configure(**cfg)


def apply_dark_theme(root):
    """Apply application-wide dark mode matching the documentation and file tree palette."""
    root.configure(bg=TREE_BG)
    set_dark_titlebar(root)
    root.option_add("*TCombobox*Listbox.background", DARK_SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TREE_FG)
    root.option_add("*TCombobox*Listbox.selectBackground", DARK_SELECT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#f0f4f8")
    root.option_add("*Menu.background", DARK_SURFACE)
    root.option_add("*Menu.foreground", TREE_FG)
    root.option_add("*Menu.activeBackground", DARK_SELECT)
    root.option_add("*Menu.activeForeground", "#f0f4f8")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        ".",
        background=TREE_BG,
        foreground=TREE_FG,
        fieldbackground=DARK_SURFACE,
        troughcolor="#141414",
        bordercolor="#343434",
        darkcolor=DARK_SURFACE,
        lightcolor="#2a2a2a",
        insertcolor=TREE_FG,
        selectbackground=DARK_SELECT,
        selectforeground="#f0f4f8",
    )
    style.configure("TFrame", background=TREE_BG)
    style.configure("TPanedwindow", background=TREE_BG)
    style.configure(
        "Sash",
        sashthickness=5,
        gripcount=0,
        background="#2a2a2a",
        bordercolor=TREE_BG,
        lightcolor="#2a2a2a",
        darkcolor="#2a2a2a",
    )
    style.configure("TLabel", background=TREE_BG, foreground=TREE_FG)
    style.configure(
        "TButton",
        background="#262626",
        foreground="#e6edf3",
        bordercolor="#3c3c3c",
        lightcolor="#262626",
        darkcolor="#262626",
        focuscolor="#3a5a8c",
        padding=(8, 4),
    )
    style.map(
        "TButton",
        background=[("disabled", "#1b1b1b"), ("pressed", "#1f4068"), ("active", "#323842")],
        foreground=[("disabled", "#6e7681"), ("active", "#ffffff")],
        bordercolor=[("active", "#58a6ff")],
    )
    style.configure(
        "TEntry",
        fieldbackground=DARK_SURFACE,
        foreground=TREE_FG,
        insertcolor=TREE_FG,
        bordercolor="#343434",
        lightcolor=DARK_SURFACE,
        darkcolor=DARK_SURFACE,
        selectbackground=DARK_SELECT,
        selectforeground="#f0f4f8",
        padding=4,
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", "#141414"), ("readonly", DARK_SURFACE)],
        foreground=[("disabled", "#6e7681")],
        bordercolor=[("focus", "#58a6ff")],
    )
    style.configure(
        "TCombobox",
        fieldbackground=DARK_SURFACE,
        background="#262626",
        foreground=TREE_FG,
        arrowcolor=TREE_FG,
        bordercolor="#343434",
        lightcolor="#262626",
        darkcolor="#262626",
        selectbackground=DARK_SELECT,
        selectforeground="#f0f4f8",
        padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", DARK_SURFACE), ("disabled", "#141414")],
        foreground=[("readonly", TREE_FG), ("disabled", "#6e7681")],
        selectbackground=[("readonly", DARK_SURFACE)],
        selectforeground=[("readonly", TREE_FG)],
        background=[("active", "#323842")],
    )
    style.configure(
        "TCheckbutton",
        background=TREE_BG,
        foreground=TREE_FG,
        indicatorbackground=DARK_SURFACE,
        indicatorforeground="#58a6ff",
        focuscolor=TREE_BG,
    )
    style.map(
        "TCheckbutton",
        background=[("active", TREE_BG)],
        foreground=[("active", "#f0f4f8"), ("disabled", "#6e7681")],
        indicatorbackground=[("selected", DARK_SELECT), ("active", "#242424")],
    )
    style.configure(
        "Treeview",
        background=DARK_SURFACE,
        fieldbackground=DARK_SURFACE,
        foreground=TREE_FG,
        bordercolor="#2a2a2a",
        lightcolor=DARK_SURFACE,
        darkcolor=DARK_SURFACE,
        rowheight=22,
    )
    style.map(
        "Treeview",
        background=[("selected", DARK_SELECT)],
        foreground=[("selected", "#f0f4f8")],
    )
    style.configure(
        "Treeview.Heading",
        background="#242424",
        foreground="#f0f4f8",
        bordercolor="#343434",
        lightcolor="#242424",
        darkcolor="#242424",
        relief="flat",
        padding=(6, 4),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", "#323842")],
        foreground=[("active", "#ffffff")],
    )
    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background="#2d2d2d",
            troughcolor="#161616",
            bordercolor="#161616",
            darkcolor="#2d2d2d",
            lightcolor="#2d2d2d",
            arrowcolor="#9da5b4",
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", "#424242"), ("pressed", "#565656")],
        )


class AsciiTreeView(ttk.Treeview):
    """Subclasses ttk.Treeview for full model/API compatibility while rendering an HTML-style ASCII tree."""

    def __init__(self, master, app, **kw):
        super().__init__(master, **kw)
        self.app = app
        self.text_widget = tk.Text(
            master,
            bg=TREE_BG,
            fg=TREE_FG,
            font=("Consolas", 10),
            wrap=tk.NONE,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=6,
            cursor="arrow",
            state=tk.DISABLED,
            selectbackground="#264f78",
            inactiveselectbackground="#264f78",
        )
        self.text_widget.tag_configure("tree_default", foreground=TREE_FG)
        self.text_widget.tag_configure("duplicate", foreground=COLOR_DUPLICATE)
        self.text_widget.tag_configure("unique", foreground=COLOR_UNIQUE)
        self.text_widget.tag_configure("empty", foreground=COLOR_EMPTY)
        self.text_widget.tag_configure("unknown", foreground=COLOR_UNKNOWN)
        self.text_widget.tag_configure("asset_supported", foreground=COLOR_UNIQUE)
        self.text_widget.tag_configure("asset_partial", foreground=COLOR_DUPLICATE)
        self.text_widget.tag_configure("asset_hex_only", foreground=COLOR_EMPTY)
        self.text_widget.tag_configure("asset_unknown", foreground=COLOR_UNKNOWN)
        self.text_widget.tag_configure("selected", background="#264f78")

        self.line_to_node = {}
        self.node_to_line = {}
        self.node_span = {}
        self._render_after_id = None

        self.text_widget.bind("<Button-1>", self._on_click)
        self.text_widget.bind("<Double-Button-1>", self._on_double_click)
        self.text_widget.bind("<Up>", self._on_key_up)
        self.text_widget.bind("<Down>", self._on_key_down)
        self.text_widget.bind("<Left>", self._on_key_left)
        self.text_widget.bind("<Right>", self._on_key_right)
        self.text_widget.bind("<Return>", self._on_key_right)

    def pack(self, cnf=None, **kw):
        return self.text_widget.pack(cnf or {}, **kw)

    def pack_forget(self):
        return self.text_widget.pack_forget()

    def yview(self, *args):
        return self.text_widget.yview(*args)

    def xview(self, *args):
        return self.text_widget.xview(*args)

    def configure(self, cnf=None, **kw):
        text_kw = {}
        for key in ("yscrollcommand", "xscrollcommand"):
            if key in kw:
                text_kw[key] = kw.pop(key)
        if text_kw:
            self.text_widget.configure(**text_kw)
        if cnf or kw:
            return super().configure(cnf, **kw)
        return None

    config = configure

    def tag_configure(self, tagname, option=None, **kw):
        res = super().tag_configure(tagname, option=option, **kw)
        if kw:
            self.text_widget.tag_configure(tagname, **kw)
        return res

    def insert(self, parent, index, iid=None, **kw):
        node = super().insert(parent, index, iid=iid, **kw)
        self.schedule_render()
        return node

    def delete(self, *items):
        super().delete(*items)
        self.schedule_render()

    def item(self, item, option=None, **kw):
        res = super().item(item, option=option, **kw)
        if kw:
            self.schedule_render()
        return res

    def move(self, item, parent, index):
        super().move(item, parent, index)
        self.schedule_render()

    def detach(self, *items):
        super().detach(*items)
        self.schedule_render()

    def selection_set(self, *items):
        super().selection_set(*items)
        self._update_selection_tags()

    def schedule_render(self):
        if self._render_after_id is not None:
            return
        delay = 120 if getattr(self.app, "scanning_folders", None) else 12
        try:
            self._render_after_id = self.app.root.after(delay, self.render)
        except tk.TclError:
            self._render_after_id = None

    def _color_tag(self, node):
        try:
            tags = super().item(node, "tags") or ()
        except tk.TclError:
            return "tree_default"
        for tag in COLOR_TAGS:
            if tag in tags:
                return tag
        if node in self.app.file_color_tags:
            return self.app.file_color_tags[node]
        return "tree_default"

    def render(self):
        self._render_after_id = None
        try:
            if not self.text_widget.winfo_exists():
                return
        except tk.TclError:
            return

        yv = self.text_widget.yview()
        xv = self.text_widget.xview()

        self.line_to_node.clear()
        self.node_to_line.clear()
        self.node_span.clear()

        rows = []

        def add_row(prefix_str, label_str, label_tag, node_id=None):
            rows.append((prefix_str, label_str, label_tag, node_id))

        def emit_archive_children(parent_node, prefix):
            children = list(self.get_children(parent_node))
            for idx, child in enumerate(children):
                is_last = idx == len(children) - 1
                grandchildren = self.get_children(child)
                tag = self._color_tag(child)
                label = super(AsciiTreeView, self).item(child, "text")
                if grandchildren:
                    conn = f"{prefix}{'\\---' if is_last else '+---'}"
                    add_row(conn, label, tag, child)
                    if bool(super(AsciiTreeView, self).item(child, "open")) or self.app.filtered:
                        emit_archive_children(child, f"{prefix}{'    ' if is_last else '|   '}")
                else:
                    add_row(f"{prefix}    ", label, tag, child)

        def emit_directory_children(dir_node, prefix):
            children = list(self.get_children(dir_node))
            file_children = [c for c in children if c in self.app.file_nodes]
            dir_children = [c for c in children if c in self.app.folder_nodes]
            other_children = [c for c in children if c not in self.app.file_nodes and c not in self.app.folder_nodes]

            file_children.sort(key=lambda c: super(AsciiTreeView, self).item(c, "text").casefold())
            dir_children.sort(key=lambda c: super(AsciiTreeView, self).item(c, "text").casefold())

            has_dirs = bool(dir_children)
            file_conn = f"{prefix}|   " if has_dirs else f"{prefix}    "

            for fnode in file_children:
                label = super(AsciiTreeView, self).item(fnode, "text")
                add_row(file_conn, label, self._color_tag(fnode), fnode)
                if bool(super(AsciiTreeView, self).item(fnode, "open")) or (
                    self.app.filtered and fnode in self.app.files_map
                ):
                    emit_archive_children(fnode, file_conn)

            if not file_children and not dir_children and other_children:
                for onode in other_children:
                    label = super(AsciiTreeView, self).item(onode, "text")
                    add_row(f"{prefix}    ", label, "unknown", dir_node)

            if file_children and dir_children:
                add_row(f"{prefix}|", "", "tree_default", None)

            for idx, dnode in enumerate(dir_children):
                is_last = idx == len(dir_children) - 1
                conn = f"{prefix}{'\\---' if is_last else '+---'}"
                label = super(AsciiTreeView, self).item(dnode, "text")
                add_row(conn, label, "tree_default", dnode)
                is_open = bool(super(AsciiTreeView, self).item(dnode, "open")) or (
                    self.app.filtered and dnode not in self.app.deferred_folders
                )
                if is_open:
                    child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
                    emit_directory_children(dnode, child_prefix)
                    if not is_last:
                        add_row(f"{prefix}|", "", "tree_default", None)

        roots = list(self.get_children(""))
        for root_node in roots:
            if root_node in self.app.folder_nodes:
                root_label = super().item(root_node, "text")
                add_row("", root_label, "tree_default", root_node)
                if bool(super().item(root_node, "open")) or self.app.filtered:
                    emit_directory_children(root_node, "")
            else:
                label = super().item(root_node, "text")
                add_row("", label, self._color_tag(root_node), root_node)
                if bool(super().item(root_node, "open")) or (
                    self.app.filtered and root_node in self.app.files_map
                ):
                    emit_archive_children(root_node, "    ")

        insert_args = []
        for idx, (prefix_str, label_str, label_tag, node_id) in enumerate(rows, start=1):
            if prefix_str:
                insert_args.append(prefix_str)
                insert_args.append(("tree_default",))
            if label_str:
                insert_args.append(label_str)
                insert_args.append((label_tag,))
            if idx < len(rows):
                insert_args.append("\n")
                insert_args.append(())
            if node_id is not None:
                self.line_to_node[idx] = node_id
                self.node_to_line[node_id] = idx
                col_start = len(prefix_str)
                col_end = col_start + len(label_str)
                self.node_span[node_id] = (f"{idx}.{col_start}", f"{idx}.{col_end}")

        self.text_widget.configure(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        if insert_args:
            self.text_widget.insert("1.0", *insert_args)
        self.text_widget.configure(state=tk.DISABLED)

        self._update_selection_tags()
        self.text_widget.yview_moveto(yv[0])
        self.text_widget.xview_moveto(xv[0])

    def _update_selection_tags(self):
        try:
            self.text_widget.tag_remove("selected", "1.0", tk.END)
            for node in self.selection():
                span = self.node_span.get(node)
                if span:
                    self.text_widget.tag_add("selected", span[0], span[1])
        except tk.TclError:
            pass

    def _node_at_event(self, event):
        try:
            index = self.text_widget.index(f"@{event.x},{event.y}")
            line_no = int(index.split(".")[0])
            return self.line_to_node.get(line_no)
        except (tk.TclError, ValueError):
            return None

    def _on_click(self, event):
        self.text_widget.focus_set()
        node = self._node_at_event(event)
        if not node or not self.exists(node):
            return "break"
        already_selected = self.selection() == (node,)
        self.focus(node)
        if node in self.app.folder_nodes:
            if node in self.app.deferred_folders:
                self.selection_set(node)
            else:
                new_open = not bool(super().item(node, "open"))
                self.item(node, open=new_open)
                self.selection_set(node)
                if new_open:
                    self.app.on_tree_open(None)
        elif node in self.app.file_nodes:
            fname = self.app.file_nodes[node]
            if fname.lower().endswith(".str") and already_selected:
                new_open = not bool(super().item(node, "open"))
                self.item(node, open=new_open)
                if new_open:
                    self.app.on_tree_open(None)
            else:
                self.selection_set(node)
        else:
            if self.get_children(node):
                self.item(node, open=not bool(super().item(node, "open")))
            self.selection_set(node)
        return "break"

    def _on_double_click(self, event):
        node = self._node_at_event(event)
        if not node or not self.exists(node):
            return "break"
        if node in self.app.file_nodes and self.app.file_nodes[node].lower().endswith(".str"):
            if not bool(super().item(node, "open")):
                self.focus(node)
                self.item(node, open=True)
                self.app.on_tree_open(None)
        return "break"

    def _move_selection(self, delta):
        ordered = [node for _, node in sorted(self.line_to_node.items())]
        if not ordered:
            return "break"
        current = self.selection()[0] if self.selection() else None
        idx = ordered.index(current) if current in ordered else (0 if delta > 0 else len(ordered) - 1)
        target = ordered[max(0, min(len(ordered) - 1, idx + delta))]
        self.focus(target)
        self.selection_set(target)
        line = self.node_to_line.get(target)
        if line:
            self.text_widget.see(f"{line}.0")
        return "break"

    def _on_key_up(self, _event):
        return self._move_selection(-1)

    def _on_key_down(self, _event):
        return self._move_selection(1)

    def _on_key_left(self, _event):
        sel = self.selection()
        if not sel:
            return "break"
        node = sel[0]
        if bool(super().item(node, "open")):
            self.item(node, open=False)
        else:
            parent = self.parent(node)
            if parent:
                self.focus(parent)
                self.selection_set(parent)
        return "break"

    def _on_key_right(self, _event):
        sel = self.selection()
        if not sel:
            return "break"
        node = sel[0]
        if node in self.app.folder_nodes or (
            node in self.app.file_nodes and self.app.file_nodes[node].lower().endswith(".str")
        ) or self.get_children(node):
            self.focus(node)
            self.item(node, open=True)
            self.app.on_tree_open(None)
        return "break"

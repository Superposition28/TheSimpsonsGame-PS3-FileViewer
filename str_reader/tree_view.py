"""Collapsible ASCII file tree matching USRDIR.tree.html presentation and colourisation."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

TREE_BG = "#1e1e1e"
TREE_FG = "#c9d1d9"
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
                path = self.app.folder_paths.get(root_node, "")
                drive, _ = os.path.splitdrive(os.path.abspath(path)) if path else ("", "")
                root_label = f"{drive}." if drive else super().item(root_node, "text")
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

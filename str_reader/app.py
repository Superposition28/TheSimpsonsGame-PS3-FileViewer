import hashlib
import io
import json
import os
import threading
import time
import shutil
from pathlib import Path
from types import SimpleNamespace
import webbrowser

from connection_explorer.controller import ServerController
from connection_explorer.index import MODULE
from game_formats.formats import identify, parse_resource, SUPPORTED_SUFFIXES, localization_table, PARTIAL
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk

    IMAGE_SUPPORT = True
except Exception:  # noqa: BLE001
    Image = None
    ImageTk = None
    IMAGE_SUPPORT = False

from .parsers.lh2 import LH2Parser
from .parsers.Export_txd import convert_txd_bytes, is_probable_txd
from .resource_parsers import (
    parse_cec,
    #parse_ears_mesh,
    parse_ears_mesh_unified,
    parse_graph,
    parse_lighttoc,
    parse_metamodel,
    parse_preinstanced,
    parse_rw_stream,
    parse_simgroup,
    parse_shk,
    parse_tob,
)
from .str_parser import STRFile
from .discovery import discover
from .media import MediaConverter, MediaRequest, MEDIA_SUFFIXES, AUDIO, VIDEO, IMAGES, open_default
from .descriptions import describe_media


class STRViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simpsons Game File Viewer")
        self.root.geometry("1000x700")

        self.server = ServerController()
        self.server_source = str(MODULE / "Source/PS3/EU/1/PS3_GAME/USRDIR")
        self.server_database = str(MODULE / "GameFiles/file-connections/index.sqlite")
        self.server_extracted = [str(MODULE / "GameFiles" / name) for name in
                                 ("PS3-EU-Full-audio_reorg-isRenamed", "PS3-EU-FullFlattened-audio_reorg-isRenamed")]
        self.server_port = 8781
        self.server_log = []
        bar = ttk.Frame(root)
        bar.pack(fill=tk.X, padx=6, pady=5)
        self.btn_server = ttk.Button(bar, text="Start connections server", command=self.toggle_server)
        self.btn_server.pack(side=tk.LEFT)
        self.btn_server_open = ttk.Button(bar, text="Open connections", command=self.open_connections, state=tk.DISABLED)
        self.btn_server_open.pack(side=tk.LEFT, padx=5)
        ttk.Button(bar, text="Connections settings", command=self.configure_connections).pack(side=tk.LEFT)
        self.server_status = ttk.Label(bar, text="Stopped")
        self.server_status.pack(side=tk.LEFT, padx=5)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self.tree_frame = ttk.Frame(self.paned)
        self.search_frame = ttk.Frame(self.tree_frame)
        self.search_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", self.on_search_change)

        self.discovery_status = ttk.Label(self.tree_frame, text="Open a folder to list files.")
        self.discovery_status.pack(side=tk.BOTTOM, fill=tk.X, padx=6)
        self.tree_container = ttk.Frame(self.tree_frame)
        self.tree_container.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(self.tree_container)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.scrollbar = ttk.Scrollbar(self.tree_container, orient="vertical", command=self.tree.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.tree.tag_configure("asset_supported", foreground="#1b6f3a")
        self.tree.tag_configure("asset_hex_only", foreground="#7a3e00")
        self.tree.tag_configure("asset_unknown", foreground="#6b6b6b")
        self.tree.tag_configure("asset_partial", foreground="#8a6500")

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.paned.add(self.tree_frame, weight=1)

        self.detail_frame = ttk.Frame(self.paned)
        self.paned.add(self.detail_frame, weight=2)

        self.converters = [
            {
                "name": "RW Texture Dictionary",
                "check": self.is_txd_chunk,
                "parser": convert_txd_bytes,
                "type": "txd",
            },
            {
                "name": "LightTOC",
                "check": self.is_lighttoc_chunk,
                "parser": parse_lighttoc,
                "type": "table",
            },
            {
                "name": "MetaModel",
                "check": self.is_metamodel_chunk,
                "parser": parse_metamodel,
                "type": "tree",
            },
            {
                "name": "Navigation Graph",
                "check": self.is_graph_chunk,
                "parser": parse_graph,
                "type": "tree",
            },
            {
                "name": "SimGroup",
                "check": self.is_simgroup_chunk,
                "parser": parse_simgroup,
                "type": "tree",
            },
            {
                "name": "EARS_MESH (Unified)",
                "check": self.is_ears_mesh_unified_chunk,
                "parser": self.parse_ears_mesh_with_metadata,
                "type": "tree",
            },
            {
                "name": "RenderWare Stream",
                "check": self.is_rw_stream_chunk,
                "parser": parse_rw_stream,
                "type": "tree",
            },
            {
                "name": "Preinstanced Mesh",
                "check": self.is_preinstanced_chunk,
                "parser": parse_preinstanced,
                "type": "tree",
            },
            {
                "name": "Controller Event Config",
                "check": self.is_cec_chunk,
                "parser": parse_cec,
                "type": "table",
            },
            {
                "name": "Text Overlay File",
                "check": self.is_tob_chunk,
                "parser": parse_tob,
                "type": "table",
            },
            {
                "name": "Shock Resource",
                "check": self.is_shk_chunk,
                "parser": parse_shk,
                "type": "table",
            },
            {
                "name": "LH2 Translation Table",
                "check": lambda c: c.get("PayloadData", c.get("Data", b"")).startswith(b"2HCL")
                or c.get("FileName", "").lower().endswith(".lh2")
                or c.get("ResourceType", "").upper() == "LH2",
                "parser": LH2Parser.parse_to_csv,
                "type": "csv",
            },
        ]
        self.converters.insert(1, {
            "name": "Documented resource", "check": self.is_documented_chunk,
            "parser": self.parse_documented_chunk, "type": "tree", "async": True,
        })
        self.converters.insert(1, {
            "name": "LH2 Translation Table", "check": lambda chunk: identify(chunk.get("FullPath") or chunk.get("FileName", ""), chunk.get("ResourceType", ""), chunk.get("PayloadData", chunk.get("Data", b""))) == ".lh2",
            "parser": localization_table, "type": "table", "async": True,
        })
        self.active_converter = None

        self.toolbar_frame = ttk.Frame(self.detail_frame)
        self.toolbar_frame.pack(pady=5, anchor="w", fill=tk.X)

        self.lbl_info = ttk.Label(self.toolbar_frame, text="Select an item to view details.", font=("Consolas", 10))
        self.lbl_info.pack(side=tk.LEFT, padx=5)
        self.base_info_text = "Select an item to view details."

        self.btn_play = ttk.Button(self.toolbar_frame, text="Play", command=self.play_media)
        self.media_choice = ttk.Combobox(self.toolbar_frame, state="readonly", width=24)
        self.media_converter = MediaConverter()
        self.media_results = Queue()
        self.media_cache = {}
        self.media_running = False
        self.selected_media = None
        self.selected_source = None
        self.selected_size = 0
        self.view_mode = "description"
        self.interpretation_cache = None
        self.deferred_folders = {}
        self.scanning_folders = set()
        self.filtered = False
        self.discovery_cancel = threading.Event()

        self.btn_action = ttk.Button(self.toolbar_frame, text="Extract Asset", command=self.extract_asset)

        self.btn_view_toggle = ttk.Button(self.toolbar_frame, text="View as CSV", command=self.toggle_view)
        self.btn_hex_prev = ttk.Button(self.toolbar_frame, text="Prev", command=self.hex_prev)
        self.btn_hex_next = ttk.Button(self.toolbar_frame, text="Next", command=self.hex_next)
        self.btn_export_json = ttk.Button(self.toolbar_frame, text="Export JSON", command=self.export_json)

        self.view_container = ttk.Frame(self.detail_frame)
        self.view_container.pack(fill=tk.BOTH, expand=True)

        self.txt_content = tk.Text(self.view_container, font=("Consolas", 10), wrap=tk.NONE)
        self.txt_content.pack(fill=tk.BOTH, expand=True)

        self.table_frame = ttk.Frame(self.view_container)
        self.table_view = ttk.Treeview(self.table_frame, show="headings")
        self.table_scroll_y = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.table_view.yview)
        self.table_scroll_x = ttk.Scrollbar(self.table_frame, orient="horizontal", command=self.table_view.xview)
        self.table_view.configure(yscrollcommand=self.table_scroll_y.set, xscrollcommand=self.table_scroll_x.set)

        self.table_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.table_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.table_view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.gallery_frame = ttk.Frame(self.view_container)
        self.preview_label = ttk.Label(self.gallery_frame, text="Select a texture", anchor="center")
        self.preview_label.pack(fill=tk.BOTH, expand=False, padx=5, pady=(5, 2))

        self.thumb_canvas = tk.Canvas(self.gallery_frame, highlightthickness=0)
        self.thumb_scroll_y = ttk.Scrollbar(self.gallery_frame, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_scroll_x = ttk.Scrollbar(self.gallery_frame, orient="horizontal", command=self.thumb_canvas.xview)
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scroll_y.set, xscrollcommand=self.thumb_scroll_x.set)

        self.thumb_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.thumb_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.thumb_inner = ttk.Frame(self.thumb_canvas)
        self.thumb_window = self.thumb_canvas.create_window((0, 0), window=self.thumb_inner, anchor="nw")
        self.thumb_inner.bind("<Configure>", self.on_thumb_configure)
        self.thumb_canvas.bind("<Configure>", self.on_thumb_canvas_configure)

        self.meta_frame = ttk.Frame(self.view_container)
        self.meta_tree = ttk.Treeview(self.meta_frame)
        self.meta_scroll_y = ttk.Scrollbar(self.meta_frame, orient="vertical", command=self.meta_tree.yview)
        self.meta_scroll_x = ttk.Scrollbar(self.meta_frame, orient="horizontal", command=self.meta_tree.xview)
        self.meta_tree.configure(yscrollcommand=self.meta_scroll_y.set, xscrollcommand=self.meta_scroll_x.set)
        self.meta_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.meta_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.meta_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open Files...", command=self.open_files)
        filemenu.add_command(label="Open Folder...", command=self.open_folder)
        filemenu.add_separator()
        filemenu.add_command(label="Clear List", command=self.clear_all)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.close)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)

        self.files_map = {}
        self.pending_files = {}
        self.loading_files = set()
        self.file_results = Queue()
        self.resource_results = Queue()
        self.selected_data = None
        self.selected_payload = None
        self.selected_filename = "export.dat"
        self.txd_textures = []
        self.txd_source_bytes = None
        self.txd_cache = {}
        self.txd_cache_key = None
        self.thumb_images = []
        self.preview_image = None
        self.parse_task_id = 0
        self.hex_offset = 0
        self.hex_page_size = 2048
        self.current_tree_data = None
        self.current_resource_data = None
        self.tree_index = {}
        self.tree_children = {}
        self.folder_load_task_id = 0
        self.root.after(100, self.poll_background)

    def is_documented_chunk(self, chunk):
        data = chunk.get("PayloadData", chunk.get("Data", b""))
        kind = identify(chunk.get("FullPath") or chunk.get("FileName", ""), chunk.get("ResourceType", ""), data)
        return bool(kind and kind not in {".str", ".dat"})

    def parse_documented_chunk(self, data):
        chunk = self.selected_chunk or {}
        result = parse_resource(data, chunk.get("FullPath") or chunk.get("FileName", ""), chunk.get("ResourceType", ""))
        self.current_resource_data = {key: value for key, value in result.items() if key != "tree"}
        return result

    def poll_background(self):
        for _ in range(5):
            try:
                request, outputs, error = self.media_results.get_nowait()
            except Empty:
                break
            self.media_running = False
            self.btn_play.config(state=tk.NORMAL, text=self.media_button_label())
            if error:
                messagebox.showerror("Media preview", str(error))
            else:
                self.media_cache[request.key()] = outputs
                if self.selected_media and request == self.selected_media:
                    self.media_choice.config(values=[path.name for path in outputs])
                    self.media_choice.current(0)
                    if len(outputs) > 1:
                        self.media_choice.pack(side=tk.LEFT, padx=5)
                    self.set_summary(f"Preview: {outputs[0]}")
                    try:
                        open_default(outputs[0])
                    except OSError as exc:
                        messagebox.showerror("Open preview", str(exc))
        for _ in range(10):
            try:
                result = self.resource_results.get_nowait()
            except Empty:
                break
            self.finish_async_parse(*result)
        for _ in range(10):
            try:
                generation, node, file, error = self.file_results.get_nowait()
            except Empty:
                break
            if generation != self.folder_load_task_id or not self.tree.exists(node):
                continue
            self.loading_files.discard(node)
            if error:
                children = self.tree.get_children(node)
                if children:
                    self.tree.item(children[0], text=f"Error: {error} (select again to retry)")
                self.rebuild_tree_index()
            else:
                self.populate_file(node, file)
                self.tree.item(node, open=True)
                if self.tree.selection() == (node,):
                    self.on_select(None)
        lines = self.server.poll()
        self.server_log.extend(lines)
        self.server_log = self.server_log[-200:]
        if self.server.running:
            self.btn_server.config(text="Stop connections server")
            self.server_status.config(text=self.server.url or (lines[-1][:100] if lines else "Starting / indexing..."))
            self.btn_server_open.config(state=tk.NORMAL if self.server.url else tk.DISABLED)
        else:
            self.btn_server.config(text="Start connections server")
            self.btn_server_open.config(state=tk.DISABLED)
            if self.server.process is not None:
                code = self.server.process.returncode
                self.server_status.config(text="Stopped" if self.server.stopping or code == 0 else f"Server exited ({code}); see settings log")
        self.root.after(100, self.poll_background)

    def toggle_server(self):
        if self.server.running:
            self.server.stop()
            self.server_status.config(text="Stopping...")
            return
        try:
            self.server.start(self.server_source, self.server_extracted, self.server_database, self.server_port,
                              getattr(self, "server_rebuild", False))
            self.server_rebuild = False
            self.server_status.config(text="Starting / indexing...")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Connections server", str(exc))

    def open_connections(self):
        if self.server.running and self.server.url:
            webbrowser.open(self.server.url)

    def configure_connections(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Connections settings")
        dialog.transient(self.root)
        fields = {}
        for row, (label, value) in enumerate((("Original source root", self.server_source),
                                               ("Database", self.server_database),
                                               ("Loopback port (0 = automatic)", str(self.server_port)),
                                               ("Extracted roots (one per line)", "\n".join(self.server_extracted)))):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="nw", padx=5, pady=5)
            if row == 3:
                entry = tk.Text(dialog, width=80, height=3)
                entry.insert("1.0", value)
            else:
                entry = ttk.Entry(dialog, width=80)
                entry.insert(0, value)
            entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
            fields[row] = entry
        rebuild = tk.BooleanVar(value=getattr(self, "server_rebuild", False))
        ttk.Checkbutton(dialog, text="Rebuild index on next start (reads source archives)", variable=rebuild).grid(row=4, column=1, sticky="w")
        log = tk.Text(dialog, width=100, height=12, wrap=tk.WORD)
        log.grid(row=5, column=0, columnspan=2, padx=5, pady=5)
        log.insert("1.0", "\n".join(self.server_log) or "Server is stopped. An existing index is reused unless rebuilding is selected.")
        log.config(state=tk.DISABLED)

        def save():
            try:
                port = int(fields[2].get())
                if not 0 <= port <= 65535:
                    raise ValueError("port must be 0..65535")
                self.server_port = port
                self.server_source = fields[0].get().strip()
                self.server_database = fields[1].get().strip()
                self.server_extracted = [p.strip() for p in fields[3].get("1.0", "end").splitlines() if p.strip()]
                self.server_rebuild = rebuild.get()
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror("Connections settings", str(exc), parent=dialog)

        ttk.Button(dialog, text="Save for next start", command=save).grid(row=6, column=1, sticky="e", padx=5, pady=5)

    def close(self):
        self.folder_load_task_id += 1
        self.discovery_cancel.set()
        self.parse_task_id += 1
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(callback)
        self.server.close()
        self.media_converter.close()
        self.root.destroy()
        self.active_converter = None
        self.converters.clear()
        self.search_var = None
        self.preview_image = None
        self.thumb_images.clear()

    def clear_all(self):
        self.folder_load_task_id += 1
        self.discovery_cancel.set()
        self.parse_task_id += 1
        self.discovery_cancel = threading.Event()
        self.pending_files.clear()
        self.deferred_folders.clear()
        self.scanning_folders.clear()
        self.btn_play.pack_forget()
        self.media_choice.pack_forget()
        self.selected_media = None
        self.loading_files.clear()
        self.selected_data = self.selected_payload = self.selected_chunk = None
        self.active_converter = None
        self.restore_tree()
        self.tree.delete(*self.tree.get_children())
        self.files_map.clear()
        self.txt_content.delete(1.0, tk.END)
        self.lbl_info.config(text="Select an item to view details.")
        self.base_info_text = "Select an item to view details."
        self.meta_tree.delete(*self.meta_tree.get_children())
        self.current_tree_data = None
        self.current_resource_data = None
        self.tree_index = {}
        self.tree_children = {}
        self.btn_action.pack_forget()
        self.btn_view_toggle.pack_forget()
        self.btn_view_toggle.config(state=tk.NORMAL)
        self.btn_hex_prev.pack_forget()
        self.btn_hex_next.pack_forget()
        self.btn_export_json.pack_forget()
        self.clear_gallery()
        self.txd_cache.clear()
        self.txd_cache_key = None

    def open_files(self):
        fnames = filedialog.askopenfilenames(
            filetypes=[("Game files", " ".join("*" + suffix for suffix in SUPPORTED_SUFFIXES)), ("All Files", "*.*")]
        )
        if not fnames:
            return

        for fname in fnames:
            self.load_single_file(fname, reindex=False)
        self.rebuild_tree_index()

    def insert_indexed(self, parent, text, **options):
        node = self.tree.insert(parent, "end", text=text, **options)
        siblings = self.tree_children.setdefault(parent, [])
        self.tree_index[node] = {"parent": parent, "index": len(siblings), "text": text}
        siblings.append(node)
        self.tree_children[node] = []
        return node

    def open_folder(self):
        directory = filedialog.askdirectory()
        if not directory:
            return
        self.restore_tree()
        node = self.insert_indexed("", os.path.basename(directory.rstrip(os.sep)) or directory, open=True)
        self.scan_directory(directory, node)

    def scan_directory(self, directory, folder_node):
        if folder_node in self.scanning_folders:
            return
        self.scanning_folders.add(folder_node)
        self.deferred_folders.pop(folder_node, None)
        generation = self.folder_load_task_id
        events = Queue()
        cancelled = self.discovery_cancel
        nodes = {os.path.normcase(os.path.normpath(directory)): folder_node}
        counts = {"files": 0, "str": 0}

        def scan():
            try:
                for entry in discover(directory, cancelled.is_set):
                    events.put(entry)
            except OSError as exc:
                events.put(str(exc))
            finally:
                events.put(None)

        def pump():
            if generation != self.folder_load_task_id or not self.tree.exists(folder_node):
                return
            start = time.monotonic()
            processed = 0
            while processed < 400 and time.monotonic() - start < 0.02:
                try:
                    entry = events.get_nowait()
                except Empty:
                    break
                if entry is None:
                    self.scanning_folders.discard(folder_node)
                    self.discovery_status.config(text=f"Listed {counts['files']:,} files ({counts['str']:,} STR archives). Audio folders load when selected.")
                    if self.search_var.get().strip():
                        self.filter_tree(self.search_var.get())
                    return
                if isinstance(entry, str):
                    self.insert_indexed(folder_node, "Scan error: " + entry)
                    continue
                parent = nodes[os.path.normcase(os.path.normpath(entry.parent))]
                if entry.kind == "file":
                    self.load_single_file(entry.path, parent, reindex=False)
                    counts["files"] += 1
                    counts["str"] += int(entry.path.lower().endswith(".str"))
                else:
                    node = self.insert_indexed(parent, os.path.basename(entry.path), open=False)
                    nodes[os.path.normcase(os.path.normpath(entry.path))] = node
                    if entry.kind == "deferred":
                        self.deferred_folders[node] = entry.path
                        self.insert_indexed(node, "Select or expand to list audio files")
                processed += 1
            self.discovery_status.config(text=f"Listing {os.path.basename(directory)}: {counts['files']:,} files ({counts['str']:,} STR)…")
            self.root.after(10, pump)

        threading.Thread(target=scan, daemon=True).start()
        self.root.after(10, pump)

    def ensure_folder_listed(self, node):
        if node not in self.deferred_folders:
            return
        directory = self.deferred_folders[node]
        self.restore_tree()
        for child in self.tree.get_children(node):
            self.tree.delete(child)
            self.tree_index.pop(child, None)
            self.tree_children.pop(child, None)
        self.tree_children[node] = []
        self.tree.item(node, open=True)
        self.scan_directory(directory, node)

    def load_single_file(self, fname, parent_id=None, reindex=True):
        """Register paths only; STR parsing waits specifically for expansion."""
        if reindex:
            self.restore_tree()
        node = self.insert_indexed(parent_id or "", os.path.basename(fname), open=False)
        self.pending_files[node] = fname
        self.insert_indexed(node, "Expand to load archive" if fname.lower().endswith(".str") else "Select to view")
        if reindex and self.search_var.get().strip():
            self.filter_tree(self.search_var.get())
        return node

    @staticmethod
    def read_file(fname):
        if fname.lower().endswith(".str"):
            return STRFile(fname)
        media = Path(fname).suffix.lower() in MEDIA_SUFFIXES
        data = None if media else Path(fname).read_bytes()
        chunk = {"Type": "Resource", "FileName": os.path.basename(fname), "FullPath": fname,
                 "Data": data, "PayloadData": data, "SourcePath": fname, "FileSize": Path(fname).stat().st_size}
        return SimpleNamespace(filepath=fname, standalone=True, header={}, stream_info={},
                               sections=[SimpleNamespace(info={"Compression": "None"}, chunks=[chunk])])

    def on_tree_open(self, _event):
        self.ensure_folder_listed(self.tree.focus())
        self.ensure_loaded(self.tree.focus(), expand=True)

    def ensure_loaded(self, node, expand=False):
        if node not in self.pending_files or node in self.loading_files:
            return
        fname = self.pending_files[node]
        if fname.lower().endswith(".str") and not expand:
            return
        self.restore_tree()
        self.loading_files.add(node)
        task_id = self.folder_load_task_id
        self.tree.item(self.tree.get_children(node)[0], text="Loading...")

        results, reader = self.file_results, self.read_file

        def read():
            try:
                results.put((task_id, node, reader(fname), None))
            except Exception as exc:
                results.put((task_id, node, None, str(exc)))

        threading.Thread(target=read, daemon=True).start()

    def populate_file(self, root_id, f):
        self.restore_tree()
        self.tree.delete(*self.tree.get_children(root_id))
        self.files_map[root_id] = f
        self.pending_files.pop(root_id, None)
        if getattr(f, "standalone", False):
            self.tree.item(root_id, tags=("sec_0_chunk_0", "asset_supported"))
            self.rebuild_tree_index()
            return
        h_id = self.tree.insert(root_id, "end", text="Header", open=False)
        self.tree.insert(h_id, "end", text=f"Version: {f.header.get('Version', '?')}")
        self.tree.insert(h_id, "end", text=f"Sections: {f.header.get('nSections', '?')}")

        if f.stream_info:
            s_id = self.tree.insert(root_id, "end", text="Stream Info", open=False)
            self.tree.insert(s_id, "end", text=f"FileName: {f.stream_info.get('FileName', 'Unknown')}")
            self.tree.insert(s_id, "end", text=f"GUID: {hex(f.stream_info.get('GUID', 0))}")

        for i, section in enumerate(f.sections):
            comp_status = section.info.get("Compression", "Unknown")
            sec_name = f"Section {i} ({comp_status})"

            sec_id = self.tree.insert(root_id, "end", text=sec_name, open=False)

            if "Error" in section.info:
                self.tree.insert(sec_id, "end", text=f"Error: {section.info['Error']}")

            if "ActualOffset" in section.info:
                self.tree.insert(sec_id, "end", text=f"Offset: {section.info['ActualOffset']}")

            for j, chunk in enumerate(section.chunks):
                c_name = f"[{chunk['Type']}]"

                if chunk.get("FileName"):
                    c_name += f" {chunk['FileName']}"
                elif chunk.get("ResourceType"):
                    c_name += f" {chunk['ResourceType']}"
                else:
                    c_name += " [No Name]"

                full_path = chunk.get("FullPath")
                if full_path:
                    path_base = os.path.basename(full_path.replace("\\", os.sep))
                    if path_base:
                        c_name += f" [{path_base}]"

                converter_supported = False
                for converter in self.converters:
                    try:
                        if converter["check"](chunk):
                            converter_supported = True
                            break
                    except Exception:
                        converter_supported = False

                if chunk.get("Data"):
                    kind = identify(chunk.get("FullPath") or chunk.get("FileName", ""), chunk.get("ResourceType", ""), chunk.get("PayloadData", chunk.get("Data", b"")))
                    color_tag = "asset_partial" if kind in PARTIAL else ("asset_supported" if converter_supported else "asset_hex_only")
                else:
                    color_tag = "asset_unknown"

                cid = self.tree.insert(sec_id, "end", text=c_name)
                self.tree.item(cid, tags=(f"sec_{i}_chunk_{j}", color_tag))



        self.rebuild_tree_index()

    def is_txd_chunk(self, chunk):
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type == "RWID_TEXDICTIONARY":
            return True
        if chunk.get("FileName", "").lower().endswith(".txd"):
            return True
        data = chunk.get("PayloadData", chunk.get("Data", b""))
        return is_probable_txd(data)

    def is_cec_chunk(self, chunk):
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"CEC", "CONTROLLEREVENTCONFIG", "CONTROLLER_EVENT_CONFIG"}:
            return True
        return chunk.get("FileName", "").lower().endswith(".cec")

    def is_tob_chunk(self, chunk):
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"TOB", "TEXTOOVERLAYFILE", "TEXTOVERLAYFILE"}:
            return True
        return chunk.get("FileName", "").lower().endswith(".tob")

    def is_shk_chunk(self, chunk):
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"SHK", "SHOCKRESOURCE", "SHOCK"}:
            return True
        return chunk.get("FileName", "").lower().endswith(".shk")

    def is_lighttoc_chunk(self, chunk):
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"LIGHTTOC", "LIGHT_TOC", "LIGHTTOCRESOURCE"}:
            return True
        return chunk.get("FileName", "").lower().endswith((".lighttoc", ".ltoc", ".ltc"))

    def is_metamodel_chunk(self, chunk):
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"METAMODEL", "MMDL", "MMDL"}:
            return True
        return chunk.get("FileName", "").lower().endswith((".mmdl", ".mmd"))

    def is_simgroup_chunk(self, chunk):
        return chunk.get("Type") == "SimGroup"

    def is_rw_stream_chunk(self, chunk):
        fname = chunk.get("FileName", "").lower()
        if fname.endswith((".dff", ".rws", ".bsp", ".txd")):
            return True
        return chunk.get("ResourceType", "").upper() == "RWID_TEXDICTIONARY"

    def is_graph_chunk(self, chunk):
        """Detect navigation graph resources (both standalone and embedded in STR)."""
        # Standalone .graph files loaded directly
        if chunk.get("Type") == "Navigation Graph":
            return True

        # Check ResourceType for embedded assets in STR files
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"GRAPH", "NAVIGATIONGRAPH", "NAVIGATION_GRAPH", "NAV_GRAPH"}:
            return True

        # Check filename extension
        fname = chunk.get("FileName", "").lower()
        if fname.endswith(".graph"):
            return True

        return False

    def is_ears_mesh_unified_chunk(self, chunk):
        """Detect EARS_MESH resources that are embedded in RWS/DFF files.

        These should be parsed with parse_ears_mesh_unified to show both
        the RWS metadata AND the embedded preinstanced texture/mesh data.
        """
        # Must be EARS_MESH resource type
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type not in {"EARS_MESH", "EARSMESH"}:
            return False

        # Must have full Data available (embedded in RWS/DFF)
        # The presence of both Data and PayloadData indicates it's from an RWS file
        if "Data" in chunk and "PayloadData" in chunk:
            # This is an embedded EARS_MESH in an RWS file - use unified parser
            return True

        return False

    def is_preinstanced_chunk(self, chunk):
        """Detect preinstanced mesh files (.dff.preinstanced, .rws.preinstanced).

        IMPORTANT: ALL ResourceType EARS_MESH files are preinstanced.
        Note: If EARS_MESH has both Data and PayloadData, it's handled by
        is_ears_mesh_unified_chunk() which takes precedence.
        """
        # Check ResourceType - all EARS_MESH are preinstanced
        # but if it has full Data, is_ears_mesh_unified_chunk handles it
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"EARS_MESH", "EARSMESH"}:
            # Only return True if it doesn't have both Data and PayloadData
            # (which would mean is_ears_mesh_unified_chunk should handle it)
            if not ("Data" in chunk and "PayloadData" in chunk):
                return True

        # Check FullPath - always ends with .preinstanced for these files
        full_path = chunk.get("FullPath", "").lower()
        if full_path.endswith(".preinstanced"):
            return True

        # Check filename extension
        fname = chunk.get("FileName", "").lower()
        if fname.endswith(".preinstanced") or ".preinstanced" in fname:
            return True

        # Check for mesh chunk signature with proper verification
        data = chunk.get("PayloadData", chunk.get("Data", b""))
        if not data or len(data) < 100:
            return False

        # Look for mesh signature in first 512 bytes
        search_region = data[:512]
        sig_pos = search_region.find(b"\x33\xEA\x00\x00")
        if sig_pos != -1 and sig_pos + 12 <= len(data):
            # Verify the mesh signature pattern at +8
            if data[sig_pos + 8:sig_pos + 12] == b"\x2D\x00\x02\x1C":
                # Also check for texture headers or TLFD (strong indicators of preinstanced)
                # Scan more of the file to find these markers
                scan_len = min(len(data), 8192)  # Check first 8KB instead of just 1KB
                if (b"\x02\x11\x01\x00\x02\x00\x00\x00" in data[:scan_len] or
                    b"TLFD" in data[:scan_len]):
                    return True

        return False

    def is_ears_mesh_chunk(self, chunk):
        """Detect EARS mesh files (legacy, non-preinstanced).

        NOTE: All actual EARS_MESH resources are preinstanced and handled
        by is_preinstanced_chunk. This is kept for backwards compatibility.
        """
        # All EARS_MESH resources are now handled by preinstanced parser
        # This function only catches non-EARS_MESH files with the mesh signature

        # Skip if it has EARS_MESH resource type (handled by preinstanced)
        resource_type = chunk.get("ResourceType", "").upper()
        if resource_type in {"EARS_MESH", "EARSMESH"}:
            return False

        data = chunk.get("PayloadData", chunk.get("Data", b""))
        if not data:
            return False

        # Only match files with mesh signature but NOT preinstanced
        return data[:64].find(b"\x33\xEA\x00\x00") != -1

    def parse_ears_mesh_with_metadata(self, conversion_data):
        """Wrapper that calls parse_ears_mesh_unified with chunk metadata.

        This is used as a parser for EARS_MESH resources that are embedded
        in RWS/DFF files. It combines RWS metadata with preinstanced texture/mesh data.
        """
        metadata = {}
        if self.selected_chunk:
            metadata = {
                "FileName": self.selected_chunk.get("FileName", ""),
                "ResourceType": self.selected_chunk.get("ResourceType", ""),
                "FullPath": self.selected_chunk.get("FullPath", ""),
            }

        # Call the unified parser with metadata
        return parse_ears_mesh_unified(conversion_data, metadata)

    def on_select(self, event):
        self.parse_task_id += 1
        self.selected_data = self.selected_payload = self.selected_chunk = None
        self.selected_source = None
        self.selected_size = 0
        self.hex_offset = 0
        self.selected_media = None
        self.active_converter = None
        self.current_tree_data = self.current_resource_data = None
        self.interpretation_cache = None
        self.description_text = "Select an item to view details."
        self.view_mode = "description"
        for widget in (self.btn_action, self.btn_view_toggle, self.btn_export_json, self.btn_play, self.media_choice):
            widget.pack_forget()
        self.btn_view_toggle.config(state=tk.NORMAL)
        self.clear_gallery()
        self.hide_views()
        self.txt_content.pack(fill=tk.BOTH, expand=True)
        self.txt_content.delete("1.0", tk.END)
        self.set_hex_controls_visible(False)
        selection = self.tree.selection()
        if not selection:
            return
        node = selection[0]
        self.ensure_folder_listed(node)
        self.ensure_loaded(node)
        tags = self.tree.item(node, "tags")
        file = None
        cursor = node
        while cursor:
            if cursor in self.files_map:
                file = self.files_map[cursor]
                break
            cursor = self.tree.parent(cursor)
        if tags and tags[0].startswith("sec_") and file:
            parts = tags[0].split("_")
            self.select_chunk(file.sections[int(parts[1])].chunks[int(parts[3])])
            return
        if node in self.pending_files:
            path = self.pending_files[node]
            self.selected_filename = os.path.basename(path)
            self.selected_source = path
            self.selected_size = os.path.getsize(path)
            if path.lower().endswith(".str"):
                self.description_text = f"STR archive: {self.selected_filename}\nSize: {self.selected_size:,} bytes\n\nExpand this archive to parse its sections and list embedded resources."
                self.active_converter = {"name": "Archive description", "type": "text"}
                self.btn_view_toggle.config(text="View raw HEX")
                self.btn_view_toggle.pack(side=tk.LEFT, padx=5)
            else:
                self.description_text = "Loading file description…"
        elif file and node in self.files_map:
            self.selected_source = file.filepath
            self.selected_size = os.path.getsize(file.filepath)
            self.description_text = "STR archive: " + file.filepath + "\n\n" + json.dumps({"header": file.header, "stream": file.stream_info, "sections": [section.info for section in file.sections]}, indent=2)
            self.active_converter = {"name": "Archive description", "type": "text"}
            self.btn_view_toggle.config(text="View raw HEX")
            self.btn_view_toggle.pack(side=tk.LEFT, padx=5)
        else:
            self.description_text = self.tree.item(node, "text")
            if file:
                self.description_text += "\n" + file.filepath
        self.base_info_text = self.tree.item(node, "text")
        self.lbl_info.config(text=self.base_info_text)
        self.txt_content.insert(tk.END, self.description_text)

    def select_chunk(self, chunk):
        self.selected_chunk = chunk
        self.selected_source = chunk.get("SourcePath")
        self.selected_payload = chunk.get("PayloadData", chunk.get("Data"))
        self.selected_data = self.selected_payload
        self.selected_size = chunk.get("FileSize", len(self.selected_data or b""))
        name = chunk.get("FullPath") or chunk.get("FileName", "resource.dat")
        self.selected_filename = os.path.basename(name.replace("\\", "/")) or "resource.dat"
        self.base_info_text = self.selected_filename
        self.lbl_info.config(text=self.base_info_text)
        suffix = Path(name).suffix.lower()
        kind = identify(name, chunk.get("ResourceType", ""), self.selected_data or b"")
        if suffix in MEDIA_SUFFIXES:
            request = MediaRequest(name, self.selected_source, self.selected_payload)
            self.selected_media = request
            self.active_converter = {"name": "Media description", "type": "text", "async": True,
                                     "parser": lambda _data, request=request: {"text": describe_media(request)}}
            self.btn_play.config(text=self.media_button_label(), state=tk.DISABLED if self.media_running else tk.NORMAL)
            self.btn_play.pack(side=tk.LEFT, padx=5)
            cached = self.media_cache.get(request.key(), [])
            if len(cached) > 1:
                self.media_choice.config(values=[path.name for path in cached])
                self.media_choice.current(0)
                self.media_choice.pack(side=tk.LEFT, padx=5)
        elif kind in {".txt", ".lua"} or suffix in {".json", ".csv", ".yaml", ".yml", ".toml", ".fnt", ".srt", ".vtt", ".xml"} and kind != ".meta.xml":
            self.active_converter = {"name": "Source text", "type": "text", "async": True,
                                     "parser": self.parse_text}
        else:
            for converter in self.converters:
                if converter["check"](chunk):
                    self.active_converter = converter
                    break
        self.btn_action.config(text="Extract payload")
        self.btn_action.pack(side=tk.LEFT, padx=5)
        self.btn_view_toggle.pack(side=tk.LEFT, padx=5)
        self.show_interpretation()

    @staticmethod
    def parse_text(data):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", "backslashreplace")
        return {"text": text}

    def media_button_label(self):
        if self.selected_media and Path(self.selected_media.name).suffix.lower() in VIDEO:
            return "Watch"
        if self.selected_media and Path(self.selected_media.name).suffix.lower() in IMAGES:
            return "Open image"
        return "Play"

    def play_media(self):
        request = self.selected_media
        if request is None or self.media_running:
            return
        cached = self.media_cache.get(request.key())
        if cached and all(path.is_file() for path in cached):
            index = max(0, self.media_choice.current())
            try:
                open_default(cached[min(index, len(cached) - 1)])
            except OSError as exc:
                messagebox.showerror("Open preview", str(exc))
            return
        self.media_running = True
        self.btn_play.config(state=tk.DISABLED, text="Converting…")
        self.set_summary("Preparing temporary preview…")

        results, converter = self.media_results, self.media_converter

        def convert():
            try:
                results.put((request, converter.convert(request), None))
            except Exception as exc:
                results.put((request, None, exc))

        threading.Thread(target=convert, daemon=True).start()

    def hide_views(self):
        for frame in (self.txt_content, self.meta_frame, self.table_frame, self.gallery_frame):
            frame.pack_forget()

    def switch_to_hex_view(self):
        self.hide_views()
        self.txt_content.pack(fill=tk.BOTH, expand=True)
        self.view_mode = "hex"
        self.btn_view_toggle.config(text="View interpretation", state=tk.NORMAL)
        self.set_hex_controls_visible(self.selected_data is not None or self.selected_source is not None)
        self.show_hex_page()

    def toggle_view(self):
        if self.view_mode == "hex":
            self.show_interpretation()
        else:
            self.parse_task_id += 1
            self.switch_to_hex_view()

    def show_interpretation(self):
        self.hide_views()
        self.set_hex_controls_visible(False)
        self.view_mode = "interpretation"
        self.btn_view_toggle.config(text="View raw HEX", state=tk.NORMAL)
        converter = self.active_converter
        if converter is None or converter["name"] == "Archive description":
            self.txt_content.pack(fill=tk.BOTH, expand=True)
            self.txt_content.delete("1.0", tk.END)
            self.txt_content.insert(tk.END, self.description_text if converter else "Unidentified resource. Raw bytes are available using View raw HEX.")
        elif converter["type"] == "txd":
            self.show_txd_gallery(self.selected_data)
        elif self.interpretation_cache is not None:
            self.render_interpretation(self.interpretation_cache)
        else:
            self.start_async_parse(self.selected_data)

    def render_interpretation(self, parsed):
        self.hide_views()
        self.view_mode = "interpretation"
        self.btn_view_toggle.config(text="View raw HEX", state=tk.NORMAL)
        kind = self.active_converter["type"]
        if kind == "tree":
            self.current_tree_data = parsed.get("tree", [])
            self.current_resource_data = {key: value for key, value in parsed.items() if key != "tree"}
            self.render_tree_view(self.current_tree_data)
            self.meta_frame.pack(fill=tk.BOTH, expand=True)
            self.btn_export_json.pack(side=tk.LEFT, padx=5)
        elif kind == "table":
            self.render_table_view(parsed.get("headers", []), parsed.get("rows", []))
            self.table_frame.pack(fill=tk.BOTH, expand=True)
        elif kind == "csv":
            self.render_csv_view(parsed)
            self.table_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.txt_content.pack(fill=tk.BOTH, expand=True)
            self.txt_content.delete("1.0", tk.END)
            self.txt_content.insert(tk.END, parsed.get("text", ""))
        if isinstance(parsed, dict) and parsed.get("summary"):
            self.set_summary(parsed["summary"])

    def render_csv_view(self, rows):
        self.table_view.delete(*self.table_view.get_children())

        if not rows:
            return

        headers = rows[0]
        self.table_view["columns"] = headers

        for col in headers:
            self.table_view.heading(col, text=col)
            self.table_view.column(col, width=150, minwidth=50)

        for row in rows[1:]:
            self.table_view.insert("", "end", values=row)

    def render_table_view(self, headers, rows):
        self.table_view.delete(*self.table_view.get_children())

        if not headers:
            return

        self.table_view["columns"] = headers

        for col in headers:
            self.table_view.heading(col, text=col)
            self.table_view.column(col, width=150, minwidth=50)

        for row in rows:
            self.table_view.insert("", "end", values=row)

    def render_tree_view(self, nodes):
        self.meta_tree.delete(*self.meta_tree.get_children())

        def add_nodes(parent, items):
            for item in items:
                label = item.get("label", "") if isinstance(item, dict) else str(item)
                node_id = self.meta_tree.insert(parent, "end", text=label)
                children = item.get("children", []) if isinstance(item, dict) else []
                if children:
                    add_nodes(node_id, children)

        add_nodes("", nodes or [])

    def set_hex_controls_visible(self, visible):
        if visible:
            self.btn_hex_prev.pack(side=tk.LEFT, padx=5)
            self.btn_hex_next.pack(side=tk.LEFT, padx=5)
        else:
            self.btn_hex_prev.pack_forget()
            self.btn_hex_next.pack_forget()

    def show_hex_page(self):
        if self.selected_data is not None:
            self.display_hex(self.selected_data, offset=self.hex_offset, limit=self.hex_page_size)
        elif self.selected_source:
            with open(self.selected_source, "rb") as handle:
                handle.seek(self.hex_offset)
                page = handle.read(self.hex_page_size)
            self.display_hex(page, limit=self.hex_page_size, base_offset=self.hex_offset, total_size=self.selected_size)

    def hex_prev(self):
        self.hex_offset = max(0, self.hex_offset - self.hex_page_size)
        self.show_hex_page()

    def hex_next(self):
        maximum = max(0, self.selected_size - 1)
        self.hex_offset = min(maximum, self.hex_offset + self.hex_page_size)
        self.show_hex_page()

    def export_json(self):
        if not self.current_tree_data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.current_resource_data or self.current_tree_data, f, indent=2)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export Error", str(exc))

    def on_search_change(self, _event):
        self.filter_tree(self.search_var.get())

    def restore_tree(self):
        if not self.filtered:
            return
        self.filtered = False
        for node, info in self.tree_index.items():
            if self.tree.exists(node) and (not info["parent"] or self.tree.exists(info["parent"])):
                self.tree.move(node, info["parent"], info["index"])

    def rebuild_tree_index(self):
        self.restore_tree()
        self.tree_index = {}
        self.tree_children = {}

        def walk(parent):
            children = self.tree.get_children(parent)
            self.tree_children[parent] = list(children)
            for idx, child in enumerate(children):
                self.tree_index[child] = {
                    "parent": parent,
                    "index": idx,
                    "text": self.tree.item(child, "text"),
                }
                walk(child)

        walk("")
        query = (self.search_var.get() or "").strip()
        if query:
            self.filter_tree(query)

    def filter_tree(self, query):
        if not self.tree_index:
            self.rebuild_tree_index()

        query = (query or "").strip().lower()

        self.restore_tree()

        if not query:
            return

        self.filtered = True
        keep = set()

        def visit(item):
            text = self.tree_index[item]["text"].lower()
            match = query in text
            for child in self.tree_children.get(item, []):
                if visit(child):
                    match = True
            if match:
                keep.add(item)
            return match

        for root in self.tree_children.get("", []):
            visit(root)

        for item in list(self.tree_index.keys()):
            if item not in keep:
                self.tree.detach(item)

    def start_async_parse(self, conversion_data):
        self.parse_task_id += 1
        task_id = self.parse_task_id

        previous_label = self.btn_view_toggle.cget("text")
        self.view_mode = "loading"
        self.btn_view_toggle.config(state=tk.NORMAL, text="View raw HEX")
        self.meta_frame.pack_forget()
        self.table_frame.pack_forget()
        self.gallery_frame.pack_forget()
        self.set_hex_controls_visible(False)
        self.txt_content.pack(fill=tk.BOTH, expand=True)
        self.txt_content.delete(1.0, tk.END)
        self.txt_content.insert(tk.END, "Loading...\n")
        self.set_summary("Loading...")

        converter = self.active_converter
        chunk = dict(self.selected_chunk or {})
        if converter["name"] == "Documented resource":
            parser = lambda data: parse_resource(data, chunk.get("FullPath") or chunk.get("FileName", ""), chunk.get("ResourceType", ""))
        elif converter["name"] == "EARS_MESH (Unified)":
            parser = lambda data: parse_ears_mesh_unified(data, chunk)
        else:
            parser = converter["parser"]
        results = self.resource_results

        def run_parse():
            try:
                parsed = parser(conversion_data)
                error = None
            except Exception as exc:
                parsed = None
                error = exc
            results.put((task_id, parsed, error, previous_label))

        thread = threading.Thread(target=run_parse, daemon=True)
        thread.start()

    def finish_async_parse(self, task_id, parsed_data, error, previous_label):
        if task_id != self.parse_task_id:
            return
        if error:
            self.hide_views()
            self.txt_content.pack(fill=tk.BOTH, expand=True)
            self.txt_content.delete("1.0", tk.END)
            self.txt_content.insert(tk.END, f"Interpretation unavailable: {error}\n\nUse View raw HEX to inspect this resource.")
            self.view_mode = "interpretation"
            self.btn_view_toggle.config(text="View raw HEX", state=tk.NORMAL)
            return
        self.interpretation_cache = parsed_data
        self.render_interpretation(parsed_data)

    def set_summary(self, summary):
        if not summary:
            return
        base = self.base_info_text.rstrip()
        text = f"{base}\n{summary.strip()}" if base else summary.strip()
        self.lbl_info.config(text=text)

    def on_thumb_configure(self, event):
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))

    def on_thumb_canvas_configure(self, event):
        self.thumb_canvas.itemconfig(self.thumb_window, width=event.width)

    def clear_gallery(self):
        for child in self.thumb_inner.winfo_children():
            child.destroy()
        self.thumb_images = []
        self.preview_image = None
        self.txd_textures = []
        self.txd_source_bytes = None
        self.txd_cache_key = None
        self.preview_label.config(image="", text="Select a texture")

    def switch_to_gallery_view(self):
        self.table_frame.pack_forget()
        self.txt_content.pack_forget()
        self.gallery_frame.pack(fill=tk.BOTH, expand=True)
        self.set_hex_controls_visible(False)

    def get_txd_cache_key(self, data):
        digest = hashlib.sha1(data).hexdigest()
        return digest

    def get_cached_txd_images(self, cache_key):
        cache_entry = self.txd_cache.get(cache_key)
        if not cache_entry:
            cache_entry = {"textures": [], "images": {}}
            self.txd_cache[cache_key] = cache_entry
        return cache_entry

    def show_txd_gallery(self, data):
        if not IMAGE_SUPPORT:
            messagebox.showerror(
                "Missing Dependencies",
                "Pillow is required to preview TXD textures.",
            )
            self.btn_view_toggle.config(text="View as TXD")
            return

        self.set_hex_controls_visible(False)
        self.txd_source_bytes = data
        cache_key = self.get_txd_cache_key(data)
        self.txd_cache_key = cache_key
        cache_entry = self.get_cached_txd_images(cache_key)

        if cache_entry["textures"]:
            textures = cache_entry["textures"]
        else:
            try:
                textures = self.active_converter["parser"](data)
            except Exception as e:
                messagebox.showerror("TXD Conversion Error", str(e))
                self.switch_to_hex_view()
                self.btn_view_toggle.config(text="View as TXD")
                return
            cache_entry["textures"] = textures

        self.txd_textures = textures
        self.switch_to_gallery_view()
        self.render_txd_gallery(textures)

    def render_txd_gallery(self, textures):
        self.clear_gallery()

        if not textures:
            self.preview_label.config(text="No textures found")
            return

        columns = 4
        thumb_size = 128

        cache_key = self.txd_cache_key
        cache_entry = self.get_cached_txd_images(cache_key) if cache_key else None

        for idx, texture in enumerate(textures):
            thumb_image = None
            try:
                cached_image = None
                if cache_entry:
                    cached_image = cache_entry["images"].get(texture.name)
                if cached_image is None:
                    cached_image = self.decode_dds_to_image(texture.dds_bytes)
                    if cache_entry is not None:
                        cache_entry["images"][texture.name] = cached_image
                image = cached_image
                thumb = image.copy()
                thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
                thumb_image = ImageTk.PhotoImage(thumb)
            except Exception:
                thumb_image = None

            label_text = f"{texture.name}\n{texture.width}x{texture.height}"
            thumb_label = ttk.Label(self.thumb_inner, text=label_text, compound="top")
            if thumb_image:
                thumb_label.configure(image=thumb_image)
                self.thumb_images.append(thumb_image)

            thumb_label.grid(row=idx // columns, column=idx % columns, padx=6, pady=6, sticky="n")
            thumb_label.bind("<Button-1>", lambda _e, tex=texture: self.show_txd_preview(tex))

        self.show_txd_preview(textures[0])

    def decode_dds_to_image(self, dds_bytes):
        if not IMAGE_SUPPORT:
            raise RuntimeError("Image support is not available.")
        image = Image.open(io.BytesIO(dds_bytes))
        image.load()
        return image.convert("RGBA")

    def show_txd_preview(self, texture):
        try:
            cache_entry = None
            if self.txd_cache_key:
                cache_entry = self.get_cached_txd_images(self.txd_cache_key)
            if cache_entry:
                image = cache_entry["images"].get(texture.name)
            else:
                image = None
            if image is None:
                image = self.decode_dds_to_image(texture.dds_bytes)
                if cache_entry is not None:
                    cache_entry["images"][texture.name] = image
        except Exception as e:
            self.preview_label.config(text=f"Failed to decode {texture.name}: {e}", image="")
            self.preview_image = None
            return

        preview = image.copy()
        preview.thumbnail((640, 640), Image.LANCZOS)
        self.preview_image = ImageTk.PhotoImage(preview)
        self.preview_label.config(
            image=self.preview_image,
            text=f"{texture.name} ({texture.width}x{texture.height}, {texture.format_name})",
            compound="top",
        )

    def show_chunk_details(self, chunk):
        info_str = f"Type: {chunk['Type']}\n"

        if chunk.get("FileName"):
            info_str += f"File: {chunk['FileName']}\n"
            self.selected_filename = os.path.basename((chunk.get("FullPath") or chunk["FileName"]).replace("\\", "/"))
        else:
            self.selected_filename = "exported_chunk.dat.uie" if chunk.get("ResourceType") == "UIE" else "exported_chunk.dat"

        if chunk.get("ResourceType"):
            info_str += f"Resource: {chunk['ResourceType']}\n"

        if chunk.get("FullPath"):
            info_str += f"Path: {chunk['FullPath']}\n"

        self.lbl_info.config(text=info_str)
        self.base_info_text = info_str

        if chunk.get("Data") is not None:
            self.selected_data = chunk["Data"]
            self.selected_payload = chunk.get("PayloadData")
            self.btn_action.config(text=f"Extract payload ({len(self.selected_payload if self.selected_payload is not None else self.selected_data)} bytes)")
            self.btn_action.pack(pady=5, anchor="w")
            self.hex_offset = 0
            self.set_hex_controls_visible(True)
            self.show_hex_page()
        else:
            self.txt_content.insert(tk.END, "[No Data Available or Parsed]")
            self.set_hex_controls_visible(False)

    def display_hex(self, data, offset=0, limit=1024, base_offset=0, total_size=None):
        self.txt_content.delete(1.0, tk.END)

        header = (
            f"{'Offset':<8}  {'00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F':<48}  ASCII\n"
        )
        self.txt_content.insert(tk.END, header)
        self.txt_content.insert(tk.END, "-" * 75 + "\n")

        if offset < 0:
            offset = 0
        preview_len = min(len(data) - offset, limit)

        for i in range(0, preview_len, 16):
            chunk = data[offset + i : offset + i + 16]
            hex_str = " ".join(f"{b:02X}" for b in chunk)
            ascii_str = "".join((chr(b) if 32 <= b < 127 else ".") for b in chunk)

            line = f"{base_offset + offset + i:08X}  {hex_str:<47}  {ascii_str}\n"
            self.txt_content.insert(tk.END, line)

        total_size = len(data) if total_size is None else total_size
        if total_size > base_offset + offset + preview_len:
            self.txt_content.insert(
                tk.END,
                f"\n... (Total size {total_size} bytes, showing {base_offset + offset}-{base_offset + offset + preview_len}) ...",
            )

    def extract_asset(self):
        data = self.selected_payload if self.selected_payload is not None else self.selected_data
        if data is None and self.selected_source is None:
            return

        path = filedialog.asksaveasfilename(initialfile=self.selected_filename)
        if path:
            try:
                if data is None:
                    shutil.copyfile(self.selected_source, path)
                else:
                    with open(path, "wb") as f:
                        f.write(data)
                messagebox.showinfo("Success", f"Saved to {path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

import hashlib
import io
import json
import os
import threading
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk
    import imagecodecs  # noqa: F401

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


class STRViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simpsons Game .STR Viewer (v5 Multi-File)")
        self.root.geometry("1000x700")

        self.paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self.tree_frame = ttk.Frame(self.paned)
        self.search_frame = ttk.Frame(self.tree_frame)
        self.search_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", self.on_search_change)

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

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
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
        self.active_converter = None

        self.toolbar_frame = ttk.Frame(self.detail_frame)
        self.toolbar_frame.pack(pady=5, anchor="w", fill=tk.X)

        self.lbl_info = ttk.Label(self.toolbar_frame, text="Select an item to view details.", font=("Consolas", 10))
        self.lbl_info.pack(side=tk.LEFT, padx=5)
        self.base_info_text = "Select an item to view details."

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
        filemenu.add_command(label="Exit", command=root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)

        self.files_map = {}
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
        self.tree_index = {}
        self.tree_children = {}
        self.folder_load_task_id = 0

    def clear_all(self):
        self.tree.delete(*self.tree.get_children())
        self.files_map.clear()
        self.txt_content.delete(1.0, tk.END)
        self.lbl_info.config(text="Select an item to view details.")
        self.base_info_text = "Select an item to view details."
        self.meta_tree.delete(*self.meta_tree.get_children())
        self.current_tree_data = None
        self.tree_index = {}
        self.tree_children = {}
        self.btn_action.pack_forget()
        self.btn_view_toggle.pack_forget()
        self.btn_hex_prev.pack_forget()
        self.btn_hex_next.pack_forget()
        self.btn_export_json.pack_forget()
        self.clear_gallery()
        self.txd_cache.clear()
        self.txd_cache_key = None

    def open_files(self):
        fnames = filedialog.askopenfilenames(
            filetypes=[("STR/Graph Files", "*.str *.graph"), ("All Files", "*.*")]
        )
        if not fnames:
            return

        for fname in fnames:
            self.load_single_file(fname)

    def open_folder(self):
        dname = filedialog.askdirectory()
        if not dname:
            return

        folder_label = os.path.basename(dname.rstrip(os.sep)) or dname
        folder_root = self.tree.insert("", "end", text=folder_label, open=True)
        path_nodes = {"": folder_root}

        self.folder_load_task_id += 1
        task_id = self.folder_load_task_id
        queue = Queue()

        def scan_folder():
            found = 0
            try:
                for root, _, files in os.walk(dname):
                    rel_root = os.path.relpath(root, dname)
                    for name in files:
                        if name.lower().endswith((".str", ".graph")):
                            full_path = os.path.join(root, name)
                            queue.put((rel_root, full_path))
                            found += 1
                            print(f"Queued file: {full_path}")
            finally:
                queue.put((None, found))

        def ensure_path_node(rel_root):
            if rel_root in ("", "."):
                return folder_root
            accum = ""
            parent_id = folder_root
            for part in rel_root.split(os.sep):
                accum = os.path.join(accum, part) if accum else part
                node_id = path_nodes.get(accum)
                if not node_id:
                    node_id = self.tree.insert(parent_id, "end", text=part, open=False)
                    path_nodes[accum] = node_id
                parent_id = node_id
            return parent_id

        def pump_queue():
            if task_id != self.folder_load_task_id:
                return
            processed = 0
            max_per_tick = 25
            while processed < max_per_tick:
                try:
                    rel_root, payload = queue.get_nowait()
                except Empty:
                    break

                if rel_root is None:
                    if payload == 0:
                        messagebox.showinfo("Info", "No .str files found in the selected directory.")
                    return

                parent_id = ensure_path_node(rel_root)
                self.load_single_file(payload, parent_id=parent_id)
                processed += 1
                print(f"Loaded file: {payload}")

            self.root.after(10, pump_queue)

        threading.Thread(target=scan_folder, daemon=True).start()
        self.root.after(10, pump_queue)

    def load_single_file(self, fname, parent_id=None):
        if fname.lower().endswith(".graph"):
            self.load_graph_file_direct(fname, parent_id)
            return

        try:
            f = STRFile(fname)
            display_name = os.path.basename(f.filepath)

            target_parent = parent_id if parent_id is not None else ""
            root_id = self.tree.insert(target_parent, "end", text=display_name, open=False)
            self.files_map[root_id] = f

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
                        color_tag = "asset_supported" if converter_supported else "asset_hex_only"
                    else:
                        color_tag = "asset_unknown"

                    cid = self.tree.insert(sec_id, "end", text=c_name)
                    self.tree.item(cid, tags=(f"sec_{i}_chunk_{j}", color_tag))

                    self.rebuild_tree_index()

        except Exception as e:
            print(f"Failed to load file {fname}: {e}")
            self.tree.insert("", "end", text=f"[ERROR] {os.path.basename(fname)}")

    def load_graph_file_direct(self, fname, parent_id=None):
        display_name = os.path.basename(fname)
        target_parent = parent_id if parent_id is not None else ""
        root_id = self.tree.insert(target_parent, "end", text=display_name, open=True)

        try:
            with open(fname, "rb") as f:
                data = f.read()

            chunk = {
                "Type": "Navigation Graph",
                "FileName": display_name,
                "Data": data,
                "PayloadData": data,
            }

            class DummySection:
                def __init__(self, chk):
                    self.chunks = [chk]

            class DummyFile:
                def __init__(self, path, chk):
                    self.filepath = path
                    self.sections = [DummySection(chk)]

            self.files_map[root_id] = DummyFile(fname, chunk)

            cid = self.tree.insert(root_id, "end", text="Navigation Graph Data")
            self.tree.item(cid, tags=("sec_0_chunk_0", "asset_supported"))
            self.rebuild_tree_index()

        except Exception as e:  # noqa: BLE001
            self.tree.insert(root_id, "end", text=f"Error: {e}")

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
        self.btn_action.pack_forget()
        self.btn_view_toggle.pack_forget()
        self.btn_export_json.pack_forget()
        self.switch_to_hex_view()
        self.clear_gallery()
        self.parse_task_id += 1
        self.selected_data = None
        self.selected_payload = None
        self.selected_chunk = None  # Store the current chunk for parser access
        self.active_converter = None
        self.current_tree_data = None

        selected_items = self.tree.selection()
        if not selected_items:
            return

        selected_item = selected_items[0]
        item_text = self.tree.item(selected_item, "text")
        tags = self.tree.item(selected_item, "tags")

        current_file = None
        cursor = selected_item
        while cursor:
            if cursor in self.files_map:
                current_file = self.files_map[cursor]
                break
            cursor = self.tree.parent(cursor)

        if tags and tags[0].startswith("sec_") and current_file:
            parts = tags[0].split("_")
            sec_idx = int(parts[1])
            chunk_idx = int(parts[3])

            chunk = current_file.sections[sec_idx].chunks[chunk_idx]
            self.selected_chunk = chunk  # Store for parser access

            for converter in self.converters:
                if converter["check"](chunk):
                    self.active_converter = converter
                    if converter["type"] == "txd":
                        self.btn_view_toggle.config(text="View as HEX")
                    else:
                        self.btn_view_toggle.config(text=f"View as {converter['type'].upper()}")
                    self.btn_view_toggle.pack(side=tk.LEFT, padx=5)
                    break

            self.show_chunk_details(chunk)
            if self.active_converter and self.active_converter["type"] == "txd":
                conversion_data = self.selected_payload or self.selected_data
                if conversion_data:
                    self.show_txd_gallery(conversion_data)
            self.btn_action.pack(side=tk.LEFT, padx=5)
            if self.active_converter and self.active_converter["type"] == "tree":
                self.btn_export_json.pack(side=tk.LEFT, padx=5)
        else:
            self.txt_content.delete(1.0, tk.END)
            self.txt_content.insert(tk.END, f"Info: {item_text}")
            if current_file:
                self.txt_content.insert(tk.END, f"\nFile: {current_file.filepath}")
            self.set_hex_controls_visible(False)

    def switch_to_hex_view(self):
        self.table_frame.pack_forget()
        self.gallery_frame.pack_forget()
        self.meta_frame.pack_forget()
        self.txt_content.pack(fill=tk.BOTH, expand=True)
        self.txt_content.delete(1.0, tk.END)
        self.lbl_info.config(text=self.base_info_text)
        self.set_hex_controls_visible(self.selected_data is not None)

    def toggle_view(self):
        conversion_data = self.selected_payload or self.selected_data
        if not self.active_converter or not conversion_data:
            return

        if self.active_converter["type"] == "txd":
            if self.gallery_frame.winfo_ismapped():
                self.switch_to_hex_view()
                self.hex_offset = 0
                self.show_hex_page()
                self.btn_view_toggle.config(text="View as TXD")
            else:
                self.show_txd_gallery(conversion_data)
                self.btn_view_toggle.config(text="View as HEX")
            return

        if self.active_converter["type"] == "tree" and self.meta_frame.winfo_ismapped():
            self.switch_to_hex_view()
            self.hex_offset = 0
            self.show_hex_page()
            self.btn_view_toggle.config(text=f"View as {self.active_converter['type'].upper()}")
            return

        if self.active_converter.get("async") and not self.table_frame.winfo_ismapped():
            self.start_async_parse(conversion_data)
            return

        if self.table_frame.winfo_ismapped():
            self.switch_to_hex_view()
            self.hex_offset = 0
            self.show_hex_page()
            self.btn_view_toggle.config(text=f"View as {self.active_converter['type'].upper()}")
        else:
            try:
                self.txt_content.pack_forget()
                self.gallery_frame.pack_forget()
                self.meta_frame.pack_forget()
                self.table_frame.pack_forget()
                self.set_hex_controls_visible(False)

                parsed_data = self.active_converter["parser"](conversion_data)

                if self.active_converter["type"] == "csv":
                    self.render_csv_view(parsed_data)
                elif self.active_converter["type"] == "table":
                    summary = ""
                    headers = []
                    rows = []
                    if isinstance(parsed_data, dict):
                        headers = parsed_data.get("headers", [])
                        rows = parsed_data.get("rows", [])
                        summary = parsed_data.get("summary", "")
                    if headers:
                        self.txt_content.pack_forget()
                        self.render_table_view(headers, rows)
                    else:
                        self.render_csv_view(parsed_data)
                    if summary:
                        self.set_summary(summary)
                elif self.active_converter["type"] == "tree":
                    summary = ""
                    nodes = []
                    if isinstance(parsed_data, dict):
                        nodes = parsed_data.get("tree", [])
                        summary = parsed_data.get("summary", "")
                        self.current_tree_data = nodes
                    self.render_tree_view(nodes)
                    if summary:
                        self.set_summary(summary)

                if self.active_converter["type"] == "tree":
                    self.meta_frame.pack(fill=tk.BOTH, expand=True)
                else:
                    self.table_frame.pack(fill=tk.BOTH, expand=True)
                self.btn_view_toggle.config(text="View as HEX")

            except Exception as e:
                messagebox.showerror("Conversion Error", str(e))
                self.switch_to_hex_view()

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
        if not self.selected_data:
            return
        self.display_hex(self.selected_data, offset=self.hex_offset, limit=self.hex_page_size)

    def hex_prev(self):
        if not self.selected_data:
            return
        self.hex_offset = max(0, self.hex_offset - self.hex_page_size)
        self.show_hex_page()

    def hex_next(self):
        if not self.selected_data:
            return
        max_offset = max(0, len(self.selected_data) - 1)
        self.hex_offset = min(max_offset, self.hex_offset + self.hex_page_size)
        self.show_hex_page()

    def export_json(self):
        if not self.current_tree_data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.current_tree_data, f, indent=2)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export Error", str(exc))

    def on_search_change(self, _event):
        self.filter_tree(self.search_var.get())

    def rebuild_tree_index(self):
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

        for item, info in self.tree_index.items():
            self.tree.move(item, info["parent"], info["index"])

        if not query:
            return

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
        self.btn_view_toggle.config(state=tk.DISABLED, text="Loading...")
        self.meta_frame.pack_forget()
        self.table_frame.pack_forget()
        self.gallery_frame.pack_forget()
        self.set_hex_controls_visible(False)
        self.txt_content.pack(fill=tk.BOTH, expand=True)
        self.txt_content.delete(1.0, tk.END)
        self.txt_content.insert(tk.END, "Loading...\n")
        self.set_summary("Loading...")

        def run_parse():
            try:
                parsed = self.active_converter["parser"](conversion_data)
                error = None
            except Exception as exc:  # noqa: BLE001
                parsed = None
                error = exc

            self.root.after(0, lambda: self.finish_async_parse(task_id, parsed, error, previous_label))

        thread = threading.Thread(target=run_parse, daemon=True)
        thread.start()

    def finish_async_parse(self, task_id, parsed_data, error, previous_label):
        if task_id != self.parse_task_id:
            return

        self.btn_view_toggle.config(state=tk.NORMAL, text=previous_label)

        if error:
            messagebox.showerror("Conversion Error", str(error))
            self.switch_to_hex_view()
            return

        if not parsed_data:
            self.switch_to_hex_view()
            return

        if self.active_converter["type"] == "table":
            summary = ""
            headers = []
            rows = []
            if isinstance(parsed_data, dict):
                headers = parsed_data.get("headers", [])
                rows = parsed_data.get("rows", [])
                summary = parsed_data.get("summary", "")
            if headers:
                self.txt_content.pack_forget()
                self.render_table_view(headers, rows)
                self.table_frame.pack(fill=tk.BOTH, expand=True)
                if summary:
                    self.set_summary(summary)
            else:
                self.switch_to_hex_view()
        elif self.active_converter["type"] == "tree":
            nodes = []
            summary = ""
            if isinstance(parsed_data, dict):
                nodes = parsed_data.get("tree", [])
                summary = parsed_data.get("summary", "")
                self.current_tree_data = nodes
            self.txt_content.pack_forget()
            self.render_tree_view(nodes)
            self.meta_frame.pack(fill=tk.BOTH, expand=True)
            if summary:
                self.set_summary(summary)
        else:
            self.switch_to_hex_view()

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
                "Pillow and imagecodecs are required to preview TXD textures.",
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
            self.selected_filename = chunk["FileName"]
        else:
            self.selected_filename = "exported_chunk.dat"

        if chunk.get("ResourceType"):
            info_str += f"Resource: {chunk['ResourceType']}\n"

        if chunk.get("FullPath"):
            info_str += f"Path: {chunk['FullPath']}\n"

        self.lbl_info.config(text=info_str)
        self.base_info_text = info_str

        if chunk.get("Data"):
            self.selected_data = chunk["Data"]
            self.selected_payload = chunk.get("PayloadData")
            self.btn_action.config(text=f"Extract {len(chunk['Data'])} bytes")
            self.btn_action.pack(pady=5, anchor="w")
            self.hex_offset = 0
            self.set_hex_controls_visible(True)
            self.show_hex_page()
        else:
            self.txt_content.insert(tk.END, "[No Data Available or Parsed]")
            self.set_hex_controls_visible(False)

    def display_hex(self, data, offset=0, limit=1024):
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

            line = f"{offset + i:08X}  {hex_str:<47}  {ascii_str}\n"
            self.txt_content.insert(tk.END, line)

        if len(data) > offset + preview_len:
            self.txt_content.insert(
                tk.END,
                f"\n... (Total size {len(data)} bytes, showing {offset}-{offset + preview_len}) ...",
            )

    def extract_asset(self):
        if not self.selected_data:
            return

        path = filedialog.asksaveasfilename(initialfile=self.selected_filename)
        if path:
            try:
                with open(path, "wb") as f:
                    f.write(self.selected_data)
                messagebox.showinfo("Success", f"Saved to {path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

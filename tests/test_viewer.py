"""Regression checks: python -B -m unittest discover -s tests -v (viewer root)."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_formats.archive import STRFile
from game_formats.formats import identify, parse_resource
from game_formats.refpack import refpack
from game_formats.resources import parse_font, parse_impact


def asset_record(payload: bytes, path: str = "folder/test.tox.PS3", resource: str = "TOB") -> bytes:
    fields = bytearray()
    for index, text in enumerate(("Object", resource, path, "")):
        if index == 1:
            fields.extend(bytes(range(16)))
        raw = text.encode() + b"\0"
        fields.extend(struct.pack(">I", len(raw)) + raw)
    fields.extend(struct.pack(">2I", 0, len(payload)))
    body = struct.pack(">I", len(fields)) + fields + payload + b"\0" * (-len(payload) % 4)
    return b"\x16\x07\0\0" + struct.pack("<I", len(body)) + b"\xff\xff\x02\x18" + body


def archive_bytes(records: bytes, compressed: bool = False) -> bytes:
    packed = records
    if compressed:
        remaining = records
        packed = b"\x10\xfb" + len(records).to_bytes(3, "big")
        while len(remaining) >= 4:
            size = min(len(remaining) // 4 * 4, 112)
            packed += bytes([0xE0 + size // 4 - 1]) + remaining[:size]
            remaining = remaining[size:]
        packed += bytes([0xFC + len(remaining)]) + remaining
    header = b"SToc" + struct.pack(">I", 1) + b"\x01\x03\0\0" + struct.pack(">2I", 0, 20)
    descriptor = struct.pack(">6I", 0, 0xB9F0B9EC if compressed else 0, len(records), len(records), len(packed), 0)
    return (header + descriptor).ljust(2048, b"\0") + packed


class ArchiveTests(unittest.TestCase):
    def test_raw_and_compressed_exact_payload_and_group_boundaries(self):
        payload = b"1BOT" + struct.pack(">3I", 32, 1, 1) + struct.pack(">4I", 0x12345678, 100, 250, 0)
        group = bytearray(52)
        group[8:12] = b"SimG"
        struct.pack_into(">I", group, 40, 48)
        struct.pack_into(">I", group, 48, 52)
        group_record = b"\x22\x07\0\0" + struct.pack("<I", len(group)) + b"\0" * 4 + group
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "test.str"
                path.write_bytes(archive_bytes(group_record + asset_record(payload), compressed))
                file = STRFile(path)
                chunks = file.sections[0].chunks
                self.assertEqual(len(chunks), 2)
                self.assertEqual(chunks[0]["Data"], group)
                self.assertEqual(chunks[1]["PayloadData"], payload)
                self.assertEqual(chunks[1]["AssetGUID"], bytes(range(16)).hex().upper())
                self.assertEqual(parse_resource(payload, "test.tox.PS3")["structure"]["cues"][0]["start_ms"], 100)

    def test_malformed_record_and_refpack_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.str"
            path.write_bytes(archive_bytes(b"\x16\x07\0\0\xff\xff\xff\x7f" + b"\0" * 4))
            with self.assertRaises(ValueError):
                STRFile(path)
        for packed in (b"\x10\xfb\0\0\x04\xfc", b"\x10\xfb\0\0\x04\x00\x00", b"\x10\xfb\0\0\x04\xe0x"):
            with self.subTest(data=packed), self.assertRaises(ValueError):
                refpack(packed)

    def test_uie_empty_path_is_not_simgroup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uie.str"
            payload = struct.pack("<5I", 1, 2, 3, 4, 5)
            path.write_bytes(archive_bytes(asset_record(payload, "", "UIE")))
            chunk = STRFile(path).sections[0].chunks[0]
            self.assertEqual(identify("", "UIE", chunk["PayloadData"]), ".dat.uie")
            self.assertEqual(len(parse_resource(payload, "", "UIE")["identifiers"]), 2)


class ResourceTests(unittest.TestCase):
    def test_vfb_observed_byte_count_and_bsp_eu_directory_variant(self):
        from game_formats.resources import parse_effect, parse_bsp
        effect = bytearray(80)
        struct.pack_into(">I", effect, 16, 6)
        effect[28] = 1
        struct.pack_into(">I", effect, 48, 76)
        effect[76:80] = b".prt"
        result = parse_effect(effect)
        self.assertEqual(len(result["entries"]), 1)
        self.assertIn("Observed byte count", result["count_interpretation"])
        bsp = bytearray(256)
        struct.pack_into(">I", bsp, 0, 11)
        struct.pack_into(">2I", bsp, 0x28, 128, 192)
        struct.pack_into(">2I", bsp, 0x30, 193, 195)
        result = parse_bsp(bsp)
        self.assertEqual(len(result["nodes"]), 1)
        self.assertIn("observed EU", result["directory_interpretation"])

    def test_font_signed_bearings_fixed_uvs_and_truncated_kerning(self):
        lookup = 0x434 + 24
        kern = lookup + 0x404
        data = bytearray(kern + 11)
        data[:4] = b"FONT"
        struct.pack_into(">IHHI", data, 4, len(data), 6, 1, 0x434)
        struct.pack_into(">I", data, 32, lookup)
        struct.pack_into(">H", data, 0x428, 2)
        struct.pack_into(">I", data, 0x42C, kern)
        struct.pack_into(">BBHHHhh6H", data, 0x434, 65, 0, 3, 4, 5, -2, 1, 16, 32, 64, 96, 2, 0)
        struct.pack_into(">BBBb", data, kern + 6, 65, 66, 0, -3)
        result = parse_font(bytes(data))
        self.assertEqual(result["glyphs"][0]["x_offset"], -2)
        self.assertEqual(result["glyphs"][0]["atlas_pixels"], [1, 2, 4, 6])
        self.assertEqual(len(result["surviving_kerning_pairs"]), 1)
        self.assertEqual(result["kerning_tail_bytes"], 1)

    def test_audio_alias_record_stride_and_cp1252_localization(self):
        alb = struct.pack(">HHI12I", 6, 2, 8, 1, 2, 3, 3, 3, 4, 5, 2, 6, 6, 6, 7)
        result = parse_resource(alb, "test.alb")
        self.assertEqual(len(result["structure"]["records"]), 2)
        self.assertEqual(result["structure"]["records"][1]["offset"], 32)
        lh2 = b"2HCL" + struct.pack(">7I", 44, 0, 0, 1, 1, 0, 0) + struct.pack(">2I", 123, 40) + b"\x93x\x94\0"
        self.assertEqual(parse_resource(lh2, "test.en.LH2")["structure"]["rows"][0]["columns"], ["“x”"])

    def test_standard_mib_candidate_records_and_unknown_variable_layout(self):
        data = bytearray(48)
        struct.pack_into(">I", data, 32, 1)
        data.extend(struct.pack(">I8f2I", 0x1234, *([1.0] * 8), 0x17700, 44))
        result = parse_resource(data, "mix.mib")["structure"]
        self.assertEqual(result["standard_mix_records"][0]["dsp_float_candidates"], [1.0] * 8)
        result = parse_resource(data + b"\0" * 4, "mix.mib")["structure"]
        self.assertIn("Variable body", result["record_layout"])

    def test_impact_block_bounds(self):
        data = struct.pack(">I4H4I", 0x5BA08CAA, 2, 1, 0x33, 1, 28, 30, 62, 70)
        data += struct.pack(">H8I2I2I", 0, *range(8), 123, 0, 1, 0)
        result = parse_impact(data)
        self.assertEqual(result["material_map"][0]["hash"], "0000007B")
        with self.assertRaises(ValueError):
            parse_impact(data[:-1])


class LazyViewerTests(unittest.TestCase):
    def test_registration_selection_expand_and_clear(self):
        """Actual Tk when available; no files may be read during registration."""
        import tkinter as tk
        from str_reader.app import STRViewerApp
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc).splitlines()[0])
        root.withdraw()
        app = STRViewerApp(root)
        try:
            with patch("str_reader.app.STRFile", side_effect=AssertionError("eager read")):
                node = app.load_single_file("not-present.str")
            self.assertIn(node, app.pending_files)
            self.assertFalse(app.files_map)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "test.str"
                payload = b"1BOT" + struct.pack(">3I", 32, 1, 1) + struct.pack(">4I", 1, 2, 3, 0)
                path.write_bytes(archive_bytes(asset_record(payload)))
                node = app.load_single_file(str(path))
                app.tree.focus(node)
                with patch.object(app, "read_file", wraps=app.read_file) as reader:
                    app.on_tree_open(None)
                    app.ensure_loaded(node)
                    deadline = time.monotonic() + 4
                    while node not in app.files_map and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertIn(node, app.files_map)
                    self.assertEqual(reader.call_count, 1)
                    app.ensure_loaded(node)
                    self.assertEqual(reader.call_count, 1)
                asset = next(child for section in app.tree.get_children(node)
                             for child in app.tree.get_children(section)
                             if any(tag.startswith("sec_") for tag in app.tree.item(child, "tags")))
                app.tree.selection_set(asset)
                root.update()
                deadline = time.monotonic() + 3
                while app.current_resource_data is None and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertEqual(app.current_resource_data["structure"]["cues"][0]["duration_ms"], 3)
                self.assertEqual(app.view_mode, "interpretation")
                app.toggle_view()
                self.assertEqual(app.view_mode, "hex")
                app.toggle_view()
                self.assertEqual(app.view_mode, "interpretation")
                exported = Path(directory) / "export.tox.PS3"
                with patch("str_reader.app.filedialog.asksaveasfilename", return_value=str(exported)), patch("str_reader.app.messagebox.showinfo"):
                    app.extract_asset()
                self.assertEqual(exported.read_bytes(), payload)
                app.filter_tree("missing")
                app.clear_all()
                self.assertFalse(app.tree.get_children())
                self.assertFalse(app.pending_files)
                self.assertFalse(app.files_map)
        finally:
            app.close()

    def test_folder_scan_does_not_read_files_and_search_clear_keeps_no_hidden_nodes(self):
        import tkinter as tk
        from str_reader.app import STRViewerApp
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc).splitlines()[0])
        root.withdraw()
        app = STRViewerApp(root)
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                (folder / "one.str").write_bytes(b"not an archive")
                (folder / "two.STR").write_bytes(b"not an archive")
                (folder / ".history").mkdir()
                (folder / ".history/skip.str").write_bytes(b"ignored")
                with patch("str_reader.app.filedialog.askdirectory", return_value=directory), patch.object(app, "read_file", side_effect=AssertionError("eager read")) as reader:
                    app.open_folder()
                    deadline = time.monotonic() + 2
                    while len(app.pending_files) < 2 and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertEqual(len(app.pending_files), 2)
                    self.assertFalse(app.files_map)
                    reader.assert_not_called()
                app.search_var.set("one")
                app.filter_tree("one")
                app.load_single_file(str(folder / "three.str"))
                app.clear_all()
                self.assertEqual(app.tree.get_children(), ())
                self.assertFalse(app.tree_index)
        finally:
            app.close()


    def test_ascii_tree_colours_collapsed_default_and_expand_all_skips_audio(self):
        import tkinter as tk
        from str_reader.app import STRViewerApp
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc).splitlines()[0])
        root.withdraw()
        app = STRViewerApp(root)
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                (folder / "unique.lua").write_bytes(b"-- unique script")
                (folder / "USRDIR.tree").write_bytes(b"tree listing")
                (folder / "audiostreams").mkdir()
                (folder / "audiostreams/track.snu").write_bytes(b"audio bytes")
                (folder / "movies/en").mkdir(parents=True)
                (folder / "movies/en/dup_a.vp6").write_bytes(b"same video payload")
                (folder / "movies/en/dup_b.vp6").write_bytes(b"same video payload")
                (folder / "chars").mkdir()
                (folder / "chars/empty_container.str").write_bytes(b"SToc" + b"\x00" * 16)
                app.open_directory(directory)
                deadline = time.monotonic() + 3
                while (app.scanning_folders or len(app.file_color_tags) < 5 or any(
                    Path(app.file_nodes[n]).name == "unique.lua" and tag == "unknown"
                    for n, tag in app.file_color_tags.items()
                )) and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                app.tree.render()
                collapsed_text = app.tree.text_widget.get("1.0", "end-1c")
                self.assertIn("+---A1_Audio", collapsed_text)
                self.assertIn("+---A1_Video", collapsed_text)
                self.assertNotIn("dup_a.vp6", collapsed_text)
                by_name = {Path(path).name: app.file_color_tags[node] for node, path in app.file_nodes.items()}
                self.assertEqual(by_name["unique.lua"], "unique")
                self.assertEqual(by_name["USRDIR.tree"], "unknown")
                self.assertEqual(by_name["dup_a.vp6"], "duplicate")
                self.assertEqual(by_name["dup_b.vp6"], "duplicate")
                self.assertEqual(by_name["empty_container.str"], "empty")
                app.expand_all()
                expanded_text = app.tree.text_widget.get("1.0", "end-1c")
                self.assertIn("dup_a.vp6", expanded_text)
                self.assertIn("empty_container.str", expanded_text)
                self.assertNotIn("track.snu", expanded_text)
                for node in app.folder_nodes:
                    if app.is_audio_folder(node):
                        self.assertFalse(bool(app.tree.item(node, "open")))
                app.collapse_all()
                recollapsed_text = app.tree.text_widget.get("1.0", "end-1c")
                self.assertNotIn("dup_a.vp6", recollapsed_text)
        finally:
            app.close()


class ConnectionsTests(unittest.TestCase):
    def test_moved_builder_payload_coordinates_and_server_restart(self):
        from connection_explorer.index import Builder, Explorer, MODULE
        from connection_explorer.controller import ServerController
        output = MODULE / "GameFiles"
        output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="viewer-test-", dir=output) as directory:
            base = Path(directory)
            source = base / "source"
            source.mkdir()
            payload = b"1BOT" + struct.pack(">3I", 32, 1, 1) + struct.pack(">4I", 0x12345678, 100, 250, 0)
            (source / "test.str").write_bytes(archive_bytes(asset_record(payload), compressed=True))
            database = base / "index.sqlite"
            builder = Builder(database, source, [])
            summary = builder.build()
            self.assertEqual(summary["files"], 2)
            explorer = Explorer(database)
            try:
                member = dict(explorer.db.execute("SELECT * FROM files WHERE view='member'").fetchone())
                self.assertEqual(explorer.read(member), payload)
                self.assertEqual(member["format"], ".tox.ps3")
            finally:
                explorer.db.close()
            controller = ServerController()
            try:
                for attempt in range(3):
                    controller.start(str(source), [], str(database), 0, rebuild=attempt == 2)
                    deadline = time.monotonic() + 6
                    while not controller.url and controller.running and time.monotonic() < deadline:
                        controller.poll()
                        time.sleep(0.02)
                    self.assertTrue(controller.url, "\n".join(controller.poll()))
                    with urlopen(controller.url + "api/summary", timeout=3) as response:
                        self.assertEqual(json.load(response)["files"], 2)
                    with urlopen(controller.url + "api/structure?id=" + str(member["id"]), timeout=3) as response:
                        self.assertEqual(json.load(response)["structure"]["cues"][0]["duration_ms"], 250)
                    with urlopen(controller.url, timeout=3) as response:
                        self.assertIn(b"<html", response.read().lower())
                    controller.close()
                    self.assertFalse(controller.running)
                    self.assertFalse(list(base.glob("*.building-*")))
            finally:
                controller.close()


if __name__ == "__main__":
    unittest.main()

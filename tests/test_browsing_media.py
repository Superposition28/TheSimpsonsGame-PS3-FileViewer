from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from str_reader.discovery import DiscoveryEntry, discover
from str_reader.media import MediaConverter, MediaRequest
from str_reader.descriptions import audio_metadata


class DiscoveryTests(unittest.TestCase):
    def test_recursive_archives_and_deferred_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("level/deep/test.STR", "level/other.str", "audiostreams/bank/one.snu", "A1_Audio/EN/two.snu", ".backup/skip.str"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with patch.object(Path, "read_bytes", side_effect=AssertionError("payload opened")):
                entries = list(discover(directory))
            self.assertEqual(sum(entry.path.lower().endswith(".str") for entry in entries), 2)
            self.assertEqual({Path(entry.path).name for entry in entries if entry.kind == "deferred"}, {"audiostreams", "A1_Audio"})
            self.assertFalse(any(entry.path.endswith(".snu") for entry in entries))
            self.assertEqual(sum(entry.path.endswith(".snu") for entry in discover(str(root / "audiostreams"))), 1)


class MediaTests(unittest.TestCase):
    def test_snu_conversion_quad_split_cached_and_source_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stream.exa.snu"
            source.write_bytes(b"original SNU")
            converter = MediaConverter(temporary=root / "tmp")

            def wav(path, channels):
                with wave.open(str(path), "wb") as handle:
                    handle.setnchannels(channels)
                    handle.setsampwidth(2)
                    handle.setframerate(48000)
                    handle.writeframes(b"\0" * channels * 2 * 100)

            def run(command, cwd):
                if command[0] == "vgmstream-cli":
                    wav(Path(command[command.index("-o") + 1]), 4)
                else:
                    for index, argument in enumerate(command):
                        if argument == "-c:a":
                            wav(Path(command[index + 2]), 2)

            with patch.object(converter, "tool", side_effect=lambda name: Path(name)), patch.object(converter, "run", side_effect=run) as runner:
                request = MediaRequest(source.name, str(source))
                outputs = converter.convert(request)
                self.assertEqual([path.name for path in outputs], ["preview_front.wav", "preview_rear.wav"])
                for path in outputs:
                    with wave.open(str(path), "rb") as handle:
                        self.assertEqual(handle.getnchannels(), 2)
                self.assertEqual(converter.convert(request), outputs)
                self.assertEqual(runner.call_count, 2)
            self.assertEqual(source.read_bytes(), b"original SNU")

    def test_vp6_uses_configured_ogv_codecs(self):
        with tempfile.TemporaryDirectory() as directory:
            converter = MediaConverter(temporary=Path(directory))
            commands = []

            def run(command, cwd):
                commands.append(command)
                Path(command[-1]).write_bytes(b"OggS preview")

            with patch.object(converter, "tool", return_value=Path("ffmpeg")), patch.object(converter, "run", side_effect=run):
                outputs = converter.convert(MediaRequest("movie.vp6", data=b"movie"))
            self.assertEqual(outputs[0].suffix, ".ogv")
            self.assertIn("libtheora", commands[0])
            self.assertIn("libvorbis", commands[0])

    def test_audio_map_seven_hex_pattern_and_bank_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AudioMap.yaml"
            registry = {"schema_version": 2, "speakers": {"homer": {"display_name": "Homer Simpson", "review_status": "inherited"}},
                        "locations": {"hubs": {}, "levels": {"loc": {"display_name": "Land of Chocolate"}}},
                        "assets": [{"id": "homer_dialogue", "audio_type": "dialogue", "speaker_id": "homer",
                                    "source": {"scope": "localized", "original_directory": "homer_bank", "file_patterns": ["d_homr_#######.exa.snu"]},
                                    "usage": {"levels": ["loc"]}}]}
            path.write_text(json.dumps(registry), encoding="utf-8")
            result = audio_metadata("audiostreams/FR/homer_bank/d_homr_01a23bc.exa.snu", path)
            self.assertEqual(result["speaker"], "Homer Simpson")
            self.assertEqual(result["language"], "FR")
            self.assertEqual(result["locations"], ["Land of Chocolate"])
            self.assertIn("No AudioMap", audio_metadata("d_homr_123456g.exa.snu", path)["status"])

    def test_music_extracts_paired_segments_without_touching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test.mus"
            data = bytearray(260)
            data[4] = 1
            struct.pack_into(">IHH5I", data, 40, 0x1234, 0, 0, 8, 2, 4, 4, 0)
            data[128:132] = b"SNR!"
            data[256:260] = b"SNS!"
            source.write_bytes(data)
            converter = MediaConverter(temporary=root / "tmp")

            def audio(snr, directory, stem, subsongs):
                self.assertEqual(snr.read_bytes(), b"SNR!")
                self.assertEqual(snr.with_suffix(".sns").read_bytes(), b"SNS!")
                output = directory / (stem + ".wav")
                output.write_bytes(b"RIFF preview")
                return [output]

            with patch.object(converter, "audio", side_effect=audio):
                outputs = converter.convert(MediaRequest(source.name, str(source)))
            self.assertEqual(outputs[0].name, "segment_000.wav")
            self.assertEqual(source.read_bytes(), data)

    def test_sbk_decodes_all_subsongs_then_normalises_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            converter = MediaConverter(temporary=Path(directory))

            def run(command, directory):
                self.assertIn("-S", command)
                self.assertEqual(command[command.index("-S") + 1], "0")
                target = command[command.index("-o") + 1]
                for track in (1, 2):
                    Path(target.replace("?s", str(track))).write_bytes(b"decoded")

            def normalise(raw, directory, stem):
                output = directory / (stem + ".wav")
                output.write_bytes(b"RIFF normalised")
                return [output]

            with patch.object(converter, "tool", return_value=Path("vgmstream-cli")), patch.object(converter, "run", side_effect=run), patch.object(converter, "normalise", side_effect=normalise):
                outputs = converter.convert(MediaRequest("bank.sbk", data=b"knbs"))
            self.assertEqual([path.name for path in outputs], ["track_1.wav", "track_2.wav"])


class ViewerInteractionTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from str_reader.app import STRViewerApp
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc).splitlines()[0])
        self.root.withdraw()
        self.app = STRViewerApp(self.root)

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.close()
            self.app = self.root = None
            import gc
            gc.collect()

    def until(self, condition, timeout=12):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.005)
        self.assertTrue(condition(), "UI task did not complete")

    def test_str_selection_does_not_parse_until_expanded(self):
        from test_viewer import archive_bytes, asset_record
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.str"
            path.write_bytes(archive_bytes(asset_record(b"data")))
            node = self.app.load_single_file(str(path))
            with patch.object(self.app, "read_file", wraps=self.app.read_file) as reader:
                self.app.tree.selection_set(node)
                self.root.update()
                reader.assert_not_called()
                self.assertIn("Expand this archive", self.app.txt_content.get("1.0", "end"))
                self.app.tree.focus(node)
                self.app.on_tree_open(None)
                self.until(lambda: node in self.app.files_map)
                self.assertEqual(reader.call_count, 1)

    def test_no_discovery_limit_after_20000_audio_entries(self):
        directory = str(Path(tempfile.gettempdir()) / "viewer-synthetic")
        audio = str(Path(directory) / "audiostreams")

        def listing(path, cancelled):
            if path == directory:
                yield DiscoveryEntry("deferred", audio, directory)
                yield DiscoveryEntry("directory", str(Path(directory) / "level"), directory)
                yield DiscoveryEntry("file", str(Path(directory) / "level/test.str"), str(Path(directory) / "level"))
            else:
                for index in range(20050):
                    yield DiscoveryEntry("file", str(Path(audio) / f"audio_{index}.snu"), audio)

        with patch("str_reader.app.discover", side_effect=listing), patch("str_reader.app.filedialog.askdirectory", return_value=directory), patch.object(self.app, "read_file", side_effect=AssertionError("read during discovery")) as reader:
            self.app.open_folder()
            self.until(lambda: not self.app.scanning_folders)
            self.assertEqual(len(self.app.pending_files), 1)
            node = next(iter(self.app.deferred_folders))
            self.app.tree.selection_set(node)
            self.root.update()
            self.until(lambda: not self.app.scanning_folders)
            self.assertEqual(len(self.app.pending_files), 20051)
            reader.assert_not_called()

    def test_text_defaults_to_text_and_media_description_play(self):
        with tempfile.TemporaryDirectory() as directory:
            text = Path(directory) / "script.lua"
            text.write_text('print("hello")', encoding="utf-8")
            node = self.app.load_single_file(str(text))
            self.app.tree.selection_set(node)
            self.until(lambda: self.app.interpretation_cache is not None)
            self.assertEqual(self.app.view_mode, "interpretation")
            self.assertIn('print("hello")', self.app.txt_content.get("1.0", "end"))
            self.app.toggle_view()
            self.assertEqual(self.app.view_mode, "hex")
            self.app.toggle_view()
            self.assertIn('print("hello")', self.app.txt_content.get("1.0", "end"))
            source = Path(directory) / "brt_igc01.exa.snu"
            source.write_bytes(b"original audio")
            output = Path(directory) / "preview.wav"
            output.write_bytes(b"RIFF preview")
            node = self.app.load_single_file(str(source))
            self.app.tree.selection_set(node)
            self.until(lambda: self.app.selected_media is not None and self.app.view_mode == "interpretation")
            self.assertIsNone(self.app.selected_data)
            self.assertIn("EA streamed audio", self.app.txt_content.get("1.0", "end"))
            with patch.object(self.app.media_converter, "convert", return_value=[output]) as convert, patch("str_reader.app.open_default") as launch:
                self.app.play_media()
                self.until(lambda: not self.app.media_running)
                launch.assert_called_once_with(output)
                self.app.play_media()
                self.assertEqual(convert.call_count, 1)
            self.app.toggle_view()
            self.assertIn("6F 72 69 67", self.app.txt_content.get("1.0", "end"))

"""On-demand previews matching operations 11–14, writing only temporary outputs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import uuid
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import threading
import tomllib

from connection_explorer.index import MODULE
from game_formats.resources import parse_music

AUDIO = {".snu", ".sbk", ".mus", ".wav", ".ogg", ".mp3", ".flac", ".snr"}
VIDEO = {".vp6", ".ogv", ".mp4", ".avi", ".webm"}
IMAGES = {".png", ".dds", ".jpg", ".jpeg", ".bmp", ".tga"}
MEDIA_SUFFIXES = AUDIO | VIDEO | IMAGES


def wav_channels(path: Path) -> int:
    """Read RIFF fmt channels, including extensible PCM on Python 3.11."""
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[:4] not in {b"RIFF", b"RF64"} or header[8:] != b"WAVE":
            raise ValueError("Decoder did not produce a RIFF WAVE file")
        while chunk := handle.read(8):
            if len(chunk) != 8:
                break
            size = struct.unpack_from("<I", chunk, 4)[0]
            if chunk[:4] == b"fmt " and size >= 4:
                fields = handle.read(4)
                if len(fields) == 4:
                    channels = struct.unpack_from("<H", fields, 2)[0]
                    if 0 < channels <= 64:
                        return channels
                break
            handle.seek(size + (size & 1), 1)
    raise ValueError("WAV channel metadata is missing or invalid")


@dataclass(frozen=True)
class MediaRequest:
    name: str
    source: str | None = None
    data: bytes | None = None

    def key(self) -> str:
        if self.source:
            path = Path(self.source)
            stat = path.stat()
            identity = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        else:
            identity = self.name + ":" + hashlib.sha256(self.data or b"").hexdigest()
        return hashlib.sha256(identity.encode()).hexdigest()


class MediaConverter:
    def __init__(self, module: Path = MODULE, temporary: Path | None = None) -> None:
        self.module = module
        self.temporary = temporary or Path(tempfile.gettempdir()) / "TheSimpsonsGame-FileViewer"
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None

    def tool(self, name: str) -> Path:
        manifest = tomllib.loads((self.module / "Tools.toml").read_text(encoding="utf-8"))
        entry = next(item for item in manifest["tool"] if item["name"].lower() == name.lower())
        root = self.module.parents[1] / "Tools" / f"{entry['name']}-{entry['version']}-win-x64"
        relative = "bin/ffmpeg.exe" if name == "ffmpeg" else "vgmstream-cli.exe"
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing configured tool: {path}. Run Download Required Tools (operation -1).")
        return path

    def run(self, command: list[str], directory: Path) -> None:
        if self.cancelled.is_set():
            raise RuntimeError("Preview conversion cancelled")
        with self.lock:
            if self.cancelled.is_set():
                raise RuntimeError("Preview conversion cancelled")
            self.process = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            process = self.process
        output, _ = process.communicate()
        with (directory / "conversion.log").open("ab") as log:
            log.write(output or b"")
        with self.lock:
            self.process = None
        if process.returncode:
            raise RuntimeError(f"Preview conversion failed: {(output or b'').decode('utf-8', 'replace')[-1500:]}\nLog: {directory / 'conversion.log'}")

    def close(self) -> None:
        self.cancelled.set()
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()

    def convert(self, request: MediaRequest) -> list[Path]:
        suffix = Path(request.name).suffix.lower()
        directory = self.temporary / request.key()
        directory.mkdir(parents=True, exist_ok=True)
        manifest = directory / "outputs.json"
        if manifest.is_file():
            outputs = [Path(value) for value in json.loads(manifest.read_text(encoding="utf-8"))]
            if outputs and all(path.is_file() for path in outputs):
                return outputs
        # A failed or cancelled attempt is never reused as a completed preview.
        attempt = directory / uuid.uuid4().hex
        attempt.mkdir()
        source = Path(request.source).resolve() if request.source else attempt / ("input" + suffix)
        if request.source is None:
            source.write_bytes(request.data or b"")
        if suffix in IMAGES or suffix in {".wav", ".ogg", ".mp3", ".flac", ".ogv", ".mp4", ".avi", ".webm"}:
            outputs = [source]
        elif suffix == ".vp6":
            output = attempt / "preview.ogv"
            self.run([str(self.tool("ffmpeg")), "-y", "-loglevel", "error", "-i", str(source),
                      "-c:v", "libtheora", "-q:v", "10", "-c:a", "libvorbis", "-q:a", "10", str(output)], attempt)
            outputs = [output]
        elif suffix == ".mus":
            outputs = self.music(source, attempt)
        elif suffix in {".snu", ".sbk", ".snr"}:
            outputs = self.audio(source, attempt)
        else:
            raise ValueError(f"No media conversion for {suffix}")
        if not outputs or not all(path.is_file() and path.stat().st_size for path in outputs):
            raise ValueError("Converter produced no usable preview")
        manifest.write_text(json.dumps([str(path) for path in outputs]), encoding="utf-8")
        return outputs

    def audio(self, source: Path, directory: Path, stem: str = "preview", subsongs: bool = True) -> list[Path]:
        vgm = str(self.tool("vgmstream-cli"))
        # SBK may contain many subsongs; list every decoded track, without guessing
        # original event ordering. -S 0 is vgmstream's all-subsongs selection.
        if source.suffix.lower() == ".sbk" and subsongs:
            bank = directory / "decoded-bank"
            bank.mkdir(exist_ok=True)
            pattern = bank / "track_?s.wav"
            if not list(bank.glob("track_*.wav")):
                self.run([vgm, "-i", "-S", "0", "-o", str(pattern), str(source)], directory)
            tracks = sorted(bank.glob("track_*.wav"))
            if not tracks:
                raise ValueError("Decoder produced no bank tracks")
            outputs = []
            for track in tracks:
                outputs.extend(self.normalise(track, directory, track.stem))
            return outputs
        output = directory / (stem + ".wav")
        front, rear = directory / (stem + "_front.wav"), directory / (stem + "_rear.wav")
        if front.is_file() and rear.is_file():
            return [front, rear]
        if output.is_file():
            return [output]
        raw = directory / (stem + ".decoding.wav")
        self.run([vgm, "-i", "-o", str(raw), str(source)], directory)
        return self.normalise(raw, directory, stem)

    def normalise(self, raw: Path, directory: Path, stem: str) -> list[Path]:
        output = directory / (stem + ".wav")
        front, rear = directory / (stem + "_front.wav"), directory / (stem + "_rear.wav")
        channels = wav_channels(raw)
        ffmpeg = str(self.tool("ffmpeg"))
        if channels == 4:
            self.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-filter_complex",
                      "[0:a]channelsplit=channel_layout=quad[FL][FR][BL][BR];[FL][FR]join=inputs=2:channel_layout=stereo[FRONT];[BL][BR]join=inputs=2:channel_layout=stereo[REAR]",
                      "-map", "[FRONT]", "-c:a", "pcm_s16le", str(front),
                      "-map", "[REAR]", "-c:a", "pcm_s16le", str(rear)], directory)
            raw.unlink(missing_ok=True)
            return [front, rear]
        self.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-c:a", "pcm_s16le", str(output)], directory)
        raw.unlink(missing_ok=True)
        return [output]

    def music(self, source: Path, directory: Path) -> list[Path]:
        # Same descriptor extraction as operations/mus.bms and SetupMusicFiles.lua.
        data = source.read_bytes()
        descriptors = parse_music(data)["entries"]
        result = []
        for index, entry in enumerate(descriptors):
            stem = f"segment_{index:03d}"
            snr, sns = directory / (stem + ".snr"), directory / (stem + ".sns")
            for output, key in ((snr, "snr"), (sns, "sns")):
                start, size = entry[key + "_offset"], entry[key + "_size"]
                output.write_bytes(data[start:start + size])
            result.extend(self.audio(snr, directory, stem, subsongs=False))
        return result


def open_default(path: Path) -> None:
    """Called only after the user presses Play/Watch/Open image."""
    os.startfile(str(path))

"""Nonblocking lifecycle for a private connections CLI process (no Tk dependency)."""
from __future__ import annotations

from pathlib import Path
from queue import Queue, Empty
import subprocess
import sys
import threading
import uuid

from .index import MODULE


class ServerController:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.messages: Queue[str] = Queue()
        self.url = ""
        self.stopping = False
        self.temporary: Path | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, source: str, extracted: list[str], database: str, port: int, rebuild: bool = False) -> None:
        if self.running:
            raise ValueError("connections process is already running")
        self.cleanup()
        token = uuid.uuid4().hex
        command = [sys.executable, "-u", "-B", str(Path(__file__).resolve().parents[1] / "file_connections.py"),
                   "--source", source, "--database", database, "--port", str(port), "--build-token", token]
        for path in extracted:
            command.extend(["--extracted", path])
        if not extracted:
            command.append("--no-extracted")
        if rebuild:
            command.append("--rebuild")
        self.url, self.stopping = "", False
        self.messages = Queue()
        self.process = subprocess.Popen(command, cwd=MODULE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace",
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process, messages = self.process, self.messages
        target = Path(database).resolve()
        self.temporary = target.with_name(target.name + f".building-{process.pid}-{token}") if target.is_relative_to((MODULE / "GameFiles").resolve()) else None

        def collect() -> None:
            assert process.stdout is not None
            with process.stdout:
                for line in process.stdout:
                    messages.put(line.rstrip())

        threading.Thread(target=collect, daemon=True).start()

    def poll(self) -> list[str]:
        self.cleanup()
        lines = []
        for _ in range(100):
            try:
                line = self.messages.get_nowait()
            except Empty:
                break
            lines.append(line)
            if line.startswith("File connections: http://127.0.0.1:"):
                self.url = line.removeprefix("File connections: ")
        return lines

    def cleanup(self) -> None:
        if self.temporary is not None and not self.running:
            try:
                self.temporary.unlink(missing_ok=True)
            except OSError as exc:
                self.messages.put(f"Could not remove unfinished index {self.temporary}: {exc}")
            self.temporary = None

    def stop(self) -> None:
        if self.running:
            self.stopping = True
            self.process.terminate()

    def close(self) -> None:
        self.stop()
        if self.process is not None:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.cleanup()

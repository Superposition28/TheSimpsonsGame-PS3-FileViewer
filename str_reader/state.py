"""Persistent per-instance state and multi-instance slot/port coordination."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import time
import tomllib

from connection_explorer.index import MODULE

try:
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None

DEFAULT_STATE_PATH = MODULE / "reversing/fileviewer/str_reader_state.toml"
DEFAULT_BASE_PORT = 8781
MAX_SLOTS = 64

_IN_PROCESS_SLOTS: set[tuple[str, int]] = set()


def _format_toml_str(value: str) -> str:
    if "'" not in value and "\n" not in value and "\r" not in value:
        return f"'{value}'"
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _format_toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _format_toml_str(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        items = ",\n".join(f"    {_format_toml_value(item)}" for item in value)
        return f"[\n{items},\n]"
    return _format_toml_str(str(value))


def dump_state_toml(data: dict) -> str:
    lines = ["# Persistent per-instance state for Simpsons Game File Viewer", ""]
    instances = data.get("instances", {})
    for slot_key in sorted(instances.keys(), key=lambda k: int(k) if str(k).isdigit() else str(k)):
        entry = instances[slot_key]
        if not isinstance(entry, dict):
            continue
        lines.append(f"[instances.{slot_key}]")
        for key in (
            "active",
            "pid",
            "updated_at",
            "server_port",
            "server_source",
            "server_database",
            "server_extracted",
            "folders",
            "files",
        ):
            if key in entry and entry[key] is not None:
                lines.append(f"{key} = {_format_toml_value(entry[key])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _is_port_in_use(port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.05)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _try_lock_byte(fh, offset: int) -> bool:
    if msvcrt is None:
        return True
    try:
        fh.seek(offset)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _unlock_byte(fh, offset: int) -> None:
    if msvcrt is None:
        return
    try:
        fh.seek(offset)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


class InstanceStateManager:
    """Manages per-instance slot locking, TOML persistence, and non-overlapping server ports."""

    def __init__(self, state_path: Path | str | None = None, base_port: int = DEFAULT_BASE_PORT):
        self.state_path = Path(state_path) if state_path is not None else None
        self.base_port = base_port
        self.instance_id = 1
        self.other_instances: list[int] = []
        self._slot_fh = None
        self._norm_key = ""

        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self._norm_key = os.path.normcase(os.path.abspath(str(self.state_path)))
            lock_path = Path(f"{self.state_path}.lock")
            self._slot_fh = open(lock_path, "r+b" if lock_path.exists() else "w+b")
            self._slot_fh.seek(0, os.SEEK_END)
            if self._slot_fh.tell() < MAX_SLOTS + 8:
                self._slot_fh.write(b"\x00" * (MAX_SLOTS + 8))
                self._slot_fh.flush()
            self._acquire_slot()

    def _acquire_slot(self) -> None:
        claimed = None
        active_others = []
        for slot in range(1, MAX_SLOTS + 1):
            in_proc = (self._norm_key, slot) in _IN_PROCESS_SLOTS
            if in_proc:
                active_others.append(slot)
                continue
            if _try_lock_byte(self._slot_fh, slot):
                if claimed is None:
                    claimed = slot
                    _IN_PROCESS_SLOTS.add((self._norm_key, slot))
                else:
                    _unlock_byte(self._slot_fh, slot)
            else:
                active_others.append(slot)
        self.instance_id = claimed or 1
        self.other_instances = [s for s in active_others if s != self.instance_id]

    @property
    def other_instance_open(self) -> bool:
        return bool(self.other_instances)

    def _with_file_lock(self, callback):
        if self.state_path is None or self._slot_fh is None:
            return callback()
        deadline = time.monotonic() + 2.0
        locked = False
        while time.monotonic() < deadline:
            if _try_lock_byte(self._slot_fh, 0):
                locked = True
                break
            time.sleep(0.005)
        try:
            return callback()
        finally:
            if locked:
                _unlock_byte(self._slot_fh, 0)

    def _read_all_unlocked(self) -> dict:
        if self.state_path is None or not self.state_path.is_file():
            return {"instances": {}}
        try:
            raw = self.state_path.read_text(encoding="utf-8")
            parsed = tomllib.loads(raw)
            if not isinstance(parsed.get("instances"), dict):
                parsed["instances"] = {}
            return parsed
        except Exception:
            return {"instances": {}}

    def _write_all_unlocked(self, data: dict) -> None:
        if self.state_path is None:
            return
        content = dump_state_toml(data)
        tmp_path = Path(f"{self.state_path}.tmp.{os.getpid()}.{self.instance_id}")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, self.state_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def allocate_port_and_load(self, default_source: str, default_db: str, default_extracted: list[str]) -> dict:
        """Load this instance's saved state and assign a non-overlapping server port."""
        if self.state_path is None:
            return {
                "server_port": self.base_port,
                "server_source": default_source,
                "server_database": default_db,
                "server_extracted": list(default_extracted),
                "folders": [],
                "files": [],
            }

        def op():
            data = self._read_all_unlocked()
            instances = data.setdefault("instances", {})
            active_set = set(self.other_instances)
            used_ports = set()
            for slot_str, info in list(instances.items()):
                if not isinstance(info, dict):
                    continue
                try:
                    slot_num = int(slot_str)
                except ValueError:
                    continue
                if slot_num in active_set:
                    port = info.get("server_port")
                    if isinstance(port, int) and port > 0:
                        used_ports.add(port)
                elif slot_num != self.instance_id and info.get("active"):
                    info["active"] = False

            my_key = str(self.instance_id)
            my_info = dict(instances.get(my_key) or {})

            min_slot_port = self.base_port + (self.instance_id - 1)
            saved_port = my_info.get("server_port")
            if isinstance(saved_port, int) and saved_port > 0:
                candidate = max(saved_port, min_slot_port) if self.other_instances else saved_port
            else:
                candidate = min_slot_port

            while candidate in used_ports or _is_port_in_use(candidate):
                candidate += 1

            my_info["active"] = True
            my_info["pid"] = os.getpid()
            my_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            my_info["server_port"] = candidate
            my_info.setdefault("server_source", default_source)
            my_info.setdefault("server_database", default_db)
            my_info.setdefault("server_extracted", list(default_extracted))
            my_info.setdefault("folders", [])
            my_info.setdefault("files", [])
            instances[my_key] = my_info
            self._write_all_unlocked(data)
            return dict(my_info)

        return self._with_file_lock(op)

    def save_instance_state(
        self,
        *,
        folders: list[str] | None = None,
        files: list[str] | None = None,
        server_port: int | None = None,
        server_source: str | None = None,
        server_database: str | None = None,
        server_extracted: list[str] | None = None,
        active: bool = True,
    ) -> None:
        if self.state_path is None:
            return

        def op():
            data = self._read_all_unlocked()
            instances = data.setdefault("instances", {})
            my_key = str(self.instance_id)
            my_info = dict(instances.get(my_key) or {})
            my_info["active"] = active
            my_info["pid"] = os.getpid()
            my_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if server_port is not None:
                my_info["server_port"] = int(server_port)
            if server_source is not None:
                my_info["server_source"] = server_source
            if server_database is not None:
                my_info["server_database"] = server_database
            if server_extracted is not None:
                my_info["server_extracted"] = list(server_extracted)
            if folders is not None:
                my_info["folders"] = list(folders)
            if files is not None:
                my_info["files"] = list(files)
            instances[my_key] = my_info
            self._write_all_unlocked(data)

        self._with_file_lock(op)

    def close(self) -> None:
        if self.state_path is None:
            return
        try:
            self.save_instance_state(active=False)
        except Exception:
            pass
        _IN_PROCESS_SLOTS.discard((self._norm_key, self.instance_id))
        if self._slot_fh is not None:
            _unlock_byte(self._slot_fh, self.instance_id)
            try:
                self._slot_fh.close()
            except OSError:
                pass
            self._slot_fh = None


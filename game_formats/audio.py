"""Validated LH2/ALB/SMB readers, shared from reversing/audio_subtitles.py."""
from __future__ import annotations
import struct
import hashlib

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def word(data: bytes, offset: int, order: str = ">") -> int:
    require(0 <= offset <= len(data) - 4, f"word outside payload: {offset:#x}")
    return struct.unpack_from(order + "I", data, offset)[0]


def string(data: bytes, offset: int, end: int | None = None) -> str:
    end = len(data) if end is None else end
    require(0 <= offset < end <= len(data), "string outside payload")
    stop = data.find(b"\0", offset, end)
    require(stop >= 0, f"unterminated string: {offset:#x}")
    # Preserve every source byte, including undefined CP1252 control positions.
    return data[offset:stop].decode("cp1252", errors="surrogateescape")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sdbm(label: str) -> int:
    result = 0
    for byte in label.lower().encode("cp1252", errors="surrogateescape"):
        result = (result * 65599 + byte) & 0xFFFFFFFF
    return result


def parse_lh2(data: bytes) -> list[tuple[int, tuple[str, ...], dict]]:
    require(len(data) >= 32 and data[:4] == b"2HCL", "invalid LH2 header")
    require(word(data, 4) == len(data), "LH2 declared size mismatch")
    count, columns = word(data, 16), word(data, 20)
    require(columns > 0 and 32 + 4 * count * (1 + columns) <= len(data), "truncated LH2 matrix")
    result = []
    for index in range(count):
        pointers = [word(data, 32 + 4 * count + 4 * (column * count + index)) for column in range(columns)]
        result.append((word(data, 32 + 4 * index), tuple(string(data, p) for p in pointers),
                       {"row": index, "id_offset": 32 + 4 * index, "text_offsets": pointers}))
    return result


def parse_alb(data: bytes) -> list[tuple[int, int, int, int, int]]:
    require(len(data) >= 8, "short ALB")
    version, count, start = struct.unpack_from(">HHI", data)
    require(version == 6 and start == 8 and len(data) == start + 24 * count,
            "unrecognized ALB layout (expected version 6, 24-byte records)")
    result = []
    for index in range(count):
        offset = start + index * 24
        alias, bank, stream, second, third, subtitle = struct.unpack_from(">6I", data, offset)
        require(stream == second == third, "ALB stream slots differ; language/slot selection unresolved")
        result.append((offset, alias, bank, stream, subtitle))
    return result


def parse_smb(data: bytes) -> list[tuple[int, int, int, str]]:
    require(len(data) >= 24, "short SMB")
    count, table = word(data, 16), word(data, 20)
    require(table == 24 and table + count * 4 <= len(data), "invalid SMB pointer table")
    offsets = [word(data, table + index * 4) for index in range(count)]
    require(not offsets or offsets[0] == table + count * 4, "unexpected SMB records start")
    result = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        require(offset >= table + count * 4 and end - offset == 96 and end <= len(data),
                "unrecognized SMB record bounds (expected 96-byte records)")
        bank, stream, second, third = struct.unpack_from(">4I", data, offset + 4)
        require(stream == second == third, "SMB stream slots differ; selection unresolved")
        name = string(data, offset + 52, end)
        require(name.lower().endswith(".exa") and "/" not in name and "\\" not in name, "invalid SMB stream name")
        result.append((offset, bank, stream, name))
    return result



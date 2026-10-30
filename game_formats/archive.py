"""Mixed-endian STR framing shared by both viewers.

See docs/PS3_GAME/FormatAnalysis/STR/index.html. ReadOffset is retained as an
unresolved descriptor word; stored sections advance sequentially from 0x800.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import struct

from .refpack import refpack


def word(data: bytes, offset: int, order: str = ">") -> int:
    if not 0 <= offset <= len(data) - 4:
        raise ValueError(f"STR word outside data at {offset:#x}")
    return struct.unpack_from(order + "I", data, offset)[0]


@dataclass
class STRSection:
    chunks: list[dict] = field(default_factory=list)
    info: dict = field(default_factory=dict)


class STRFile:
    def __init__(self, filepath: str | Path) -> None:
        self.filepath = str(filepath)
        self.header: dict = {}
        self.stream_info: dict = {}
        self.sections: list[STRSection] = []
        self.raw_data = Path(filepath).read_bytes()
        self.parse()

    def parse(self) -> None:
        raw = self.raw_data
        if len(raw) < 20 or raw[:4] != b"SToc":
            raise ValueError("invalid STR signature or truncated header")
        count, stream, table = raw[8], word(raw, 12), word(raw, 16)
        if table < 20 or table + count * 24 > len(raw):
            raise ValueError("STR section table outside file")
        self.header = dict(Magic="SToc", Version=word(raw, 4), nSections=count,
                           PlatformID=raw[9], pStreamFile=stream, pSectionArr=table)
        self.sections = []
        if stream:
            if stream + 24 > len(raw):
                raise ValueError("STR StreamFile outside file")
            name = stream + struct.unpack_from(">i", raw, stream + 4)[0]
            end = raw.find(b"\0", name) if 0 <= name < len(raw) else -1
            if end < 0:
                raise ValueError("invalid STR StreamFile name")
            self.stream_info = dict(GUID=word(raw, stream), FileName=raw[name:end].decode("ascii", "replace"),
                                    nParents=raw[stream + 8], nForceLoad=raw[stream + 9],
                                    nSections=raw[stream + 10], Flags=raw[stream + 11],
                                    pRelatives=word(raw, stream + 16), pSectionInfo=word(raw, stream + 20))
        base = (table + count * 24 + 2047) & ~2047
        for index in range(count):
            values = struct.unpack_from(">6I", raw, table + index * 24)
            info = dict(zip(("MemPolicyID", "CompressorID", "DataSize", "AllocSize", "ReadSize", "ReadOffset"), values))
            size, stored = values[2], values[4]
            if base + stored > len(raw) or size > 256 * 1024 * 1024:
                raise ValueError(f"STR section {index} outside file or decoded size limit")
            packed = raw[base:base + stored]
            compressed = packed[:2] == b"\x10\xfb"
            data = refpack(packed, size)[0] if compressed else packed[:size]
            if len(data) != size:
                raise ValueError(f"STR section {index} decoded size mismatch")
            info.update(ActualOffset=hex(base), FileOffset=base, Compression="Refpack" if compressed else "None")
            section = STRSection(info=info)
            offset = 0
            while offset < len(data):
                if offset + 12 > len(data):
                    raise ValueError(f"short STR record at section {index}, {offset:#x}")
                kind = int.from_bytes(data[offset:offset + 2], "big")
                size = word(data, offset + 4, "<")
                start, end = offset + 12, offset + 12 + size
                if not size or end > len(data):
                    raise ValueError(f"STR record outside section {index}, {offset:#x}")
                body = data[start:end]
                chunk = dict(ID=kind, Start=offset, Data=body, PayloadData=body,
                             PayloadStart=start, PayloadSize=size,
                             Type="SimGroup" if kind == 0x2207 else f"Unknown (0x{kind:04X})")
                if kind == 0x1607:
                    chunk["Type"] = "Embedded Asset"
                    header = word(body, 0)
                    if header:
                        limit, cursor, fields = 4 + header, 4, []
                        if limit > len(body):
                            raise ValueError("STR asset header outside record")
                        for part in range(4):
                            if part == 1:
                                if cursor + 16 > limit:
                                    raise ValueError("STR asset GUID outside header")
                                chunk["AssetGUID"] = body[cursor:cursor + 16].hex().upper()
                                chunk["GUIDOffset"] = start + cursor
                                cursor += 16
                            length = word(body, cursor)
                            cursor += 4
                            if cursor + length > limit:
                                raise ValueError("STR asset string outside header")
                            fields.append(body[cursor:cursor + length].split(b"\0")[0].decode("ascii", "replace"))
                            cursor += length
                        if cursor + 8 > limit:
                            raise ValueError("STR asset size fields outside header")
                        payload_size = word(body, cursor + 4)
                        if limit + ((payload_size + 3) & ~3) != len(body):
                            raise ValueError("STR asset payload/record size disagreement")
                        chunk.update(FileName=fields[0], ResourceType=fields[1], FullPath=fields[2],
                                     ExtraString=fields[3], HeaderSize=header,
                                     PayloadStart=start + limit, PayloadSize=payload_size,
                                     PayloadData=body[limit:limit + payload_size])
                section.chunks.append(chunk)
                offset = end
            self.sections.append(section)
            base += stored
        if base != len(raw):
            raise ValueError("STR trailing bytes outside declared sections")

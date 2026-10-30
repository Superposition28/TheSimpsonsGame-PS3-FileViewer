"""Bounded EA RefPack decoder, following the STR audit's dk2 stream."""
from __future__ import annotations


def refpack(data: bytes, expected: int | None = None, maximum: int = 256 * 1024 * 1024) -> tuple[bytes, int]:
    if len(data) < 5 or data[:2] != b"\x10\xfb":
        raise ValueError("invalid or truncated RefPack header")
    declared = int.from_bytes(data[2:5], "big")
    if declared > maximum or (expected is not None and declared != expected):
        raise ValueError("RefPack decoded size disagrees with section or exceeds limit")
    out = bytearray()
    pos = 5

    def take(count: int) -> bytes:
        nonlocal pos
        if pos + count > len(data):
            raise ValueError("truncated RefPack command or literals")
        result = data[pos:pos + count]
        pos += count
        return result

    while True:
        control = take(1)[0]
        stop = False
        if control < 0x80:
            a = take(1)[0]
            literal, count, distance = control & 3, ((control >> 2) & 7) + 3, ((control & 0x60) << 3) + a + 1
        elif control < 0xC0:
            a, b = take(2)
            literal, count, distance = a >> 6, (control & 0x3F) + 4, ((a & 0x3F) << 8) + b + 1
        elif control < 0xE0:
            a, b, c = take(3)
            literal, count, distance = control & 3, ((control & 0x0C) << 6) + c + 5, ((control & 0x10) << 12) + (a << 8) + b + 1
        elif control < 0xFC:
            literal, count, distance = ((control & 0x1F) + 1) * 4, 0, 0
        else:
            literal, count, distance, stop = control & 3, 0, 0, True
        if len(out) + literal + count > declared:
            raise ValueError("RefPack output exceeds declared size")
        out.extend(take(literal))
        if count and not 0 < distance <= len(out):
            raise ValueError("RefPack back-reference outside decoded data")
        for _ in range(count):
            out.append(out[-distance])
        if stop:
            if len(out) != declared:
                raise ValueError("RefPack decoded length mismatch")
            return bytes(out), pos

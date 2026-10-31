"""Structural readers for the layouts documented in PS3_GAME/FormatAnalysis.

Unknown fields retain their offsets and raw values. These readers do not infer
animation, audio playback, physics behavior, or cross-file hash namespaces.
"""
from __future__ import annotations

import re
from itertools import islice
import struct

from .audio import require, word, string, parse_lh2, parse_alb, parse_smb
from .collision import parse_acs
from .havok import inspect_havok
from .identifiers import parse_bbn, parse_uie


def array_bounds(data: bytes, start: int, count: int, stride: int) -> None:
    require(0 <= start <= len(data) and count >= 0 and start + count * stride <= len(data),
            f"array outside payload: {start:#x}, count {count}, stride {stride}")


def parse_font(data: bytes) -> dict:
    require(len(data) >= 0x434 and data[:4] == b"FONT", "invalid FONT header")
    version, count = struct.unpack_from(">HH", data, 8)
    require(version == 6 and word(data, 4) == len(data), "unsupported FONT version/size")
    start, lookup = word(data, 12), word(data, 32)
    array_bounds(data, start, count, 24)
    require(lookup == start + count * 24 and lookup + 0x404 <= len(data), "invalid FONT lookup buffer")
    glyphs = []
    for index in range(count):
        pos = start + index * 24
        code, pad, width, height, advance, xoff, yoff, x0, y0, x1, y1, kc, ki = struct.unpack_from(">BBHHHhh6H", data, pos)
        glyphs.append(dict(offset=pos, code=code, padding=pad, width=width, height=height,
                           advance=advance, x_offset=xoff, y_offset=yoff,
                           atlas_fixed=[x0, y0, x1, y1], atlas_pixels=[v >> 4 for v in (x0, y0, x1, y1)],
                           kerning_count=kc, kerning_start_index=ki))
    declared = struct.unpack_from(">H", data, 0x428)[0]
    kern = word(data, 0x42C)
    pairs = []
    if declared:
        array_bounds(data, kern, 1, 6)
        require(kern >= lookup + 0x404, "FONT kerning overlaps lookup buffer")
        for pos in range(kern + 6, min(len(data), kern + 6 + declared * 4) - 3, 4):
            first, second, pad, amount = struct.unpack_from(">BBBb", data, pos)
            pairs.append(dict(offset=pos, first=first, second=second, padding=pad, amount=amount))
    return dict(version=version, glyph_count=count, line_height=word(data, 24), baseline=word(data, 28),
                max_width=word(data, 20), glyphs=glyphs, declared_kerning_count=declared,
                surviving_kerning_pairs=pairs, kerning_tail_bytes=(len(data) - kern - 6) % 4 if declared else 0,
                note="Only complete surviving kerning records are read; documented exporter tails can be truncated. Glyph codes retain source values; font-specific Unicode remaps are separate.")


def parse_impact(data: bytes) -> dict:
    require(len(data) >= 28 and word(data, 0) == 0x5BA08CAA, "invalid IMB magic")
    version, materials, unknown, effects = struct.unpack_from(">4H", data, 4)
    require(version == 2, "unsupported IMB version")
    a, b, c, d = struct.unpack_from(">4I", data, 12)
    require(28 <= a <= b <= c <= d <= len(data), "IMB block boundaries outside payload")
    require((b - a) % 2 == 0 and c - b == effects * 32 and d - c == materials * 8 and (len(data) - d) % 8 == 0,
            "IMB block counts/strides disagree")
    return dict(version=version, unknown_08=unknown, block_offsets=[a, b, c, d],
                interaction_indices=[row[0] for row in struct.iter_unpack(">H", data[a:b])],
                effect_clusters=[list(row) for row in struct.iter_unpack(">8I", data[b:c])],
                material_map=[dict(hash=f"{h:08X}", grid_index=i) for h, i in struct.iter_unpack(">2I", data[c:d])],
                alias_pairs=[list(row) for row in struct.iter_unpack(">2I", data[d:])],
                note="Material/effect roles are inferred. Hash algorithms and external target namespaces remain unresolved.")


def parse_effect(data: bytes) -> dict:
    require(len(data) >= 32 and word(data, 16) == 6, "unsupported VFB header")
    count_be, flags = struct.unpack_from(">2H", data, 28)
    count = count_be
    count_note = "BE u16 count from the reference"
    if 32 + count * 28 > len(data) and 32 + data[28] * 28 <= len(data):
        count = data[28]
        count_note = "Observed byte count at +0x1c; the documented BE u16 interpretation exceeds this payload. Remaining header bytes are retained."
    array_bounds(data, 32, count, 28)
    entries = []
    for index in range(count):
        pos = 32 + index * 28
        start, end, scale, key, target, fade, kind = struct.unpack_from(">3fIIfI", data, pos)
        array_bounds(data, target, 1, 4)
        require(target >= 32 + count * 28, "VFB block overlaps table")
        entries.append(dict(offset=pos, start_candidate=start, end_candidate=end, scale_candidate=scale,
                            hash_or_flags=f"{key:08X}", block_offset=target,
                            block_tag=data[target:target + 4].decode("ascii", "replace"),
                            fade_candidate=fade, block_flags=kind))
    return dict(name=data[:16].split(b"\0")[0].decode("ascii", "replace"), version=6,
                flags=word(data, 20), duration_or_scale=struct.unpack_from(">f", data, 24)[0],
                flags_1e=flags, count_header_hex=data[28:32].hex(), count_interpretation=count_note, entries=entries, note="Block opcode semantics and runtime timing remain tentative.")


def parse_bsp(data: bytes) -> dict:
    require(len(data) >= 0x70 and word(data, 0) == 11, "unsupported BSP header")
    start, size = word(data, 0x30), word(data, 0x34)
    layout = "documented +0x30 offset/length"
    if size % 64 or start + size > len(data):
        # The reference's directory description is tentative. In the inspected
        # EU files +0x28/+0x2c bound the 64-byte node array. Retain this distinction.
        start, stop = word(data, 0x28), word(data, 0x2C)
        size = stop - start
        require(start >= 0x70 and size >= 0 and size % 64 == 0, "BSP node bounds do not match either known layout")
        layout = "observed EU +0x28/+0x2c start/end; differs from tentative reference directory"
    array_bounds(data, start, size // 64, 64)
    nodes = []
    for pos in range(start, start + size, 64):
        values = struct.unpack_from(">8f8i", data, pos)
        nodes.append(dict(offset=pos, plane=list(values[:4]), unknown_floats=list(values[4:8]),
                          flags_candidate=values[8], front=values[9], back=values[10],
                          unknown_integers=list(values[11:])))
    return dict(version=11, unknown_04=word(data, 4), metadata_count=word(data, 8),
                metadata_offset=word(data, 12), directory_hex=data[16:112].hex(),
                node_lump_offset=start, directory_interpretation=layout, nodes=nodes,
                note="Only the bounded 64-byte node array is decoded. Other lump schemas and child semantics remain partly unresolved.")


def parse_music(data: bytes) -> dict:
    require(len(data) >= 40, "short MUS header")
    count = data[4]
    array_bounds(data, 40, count, 28)
    entries = []
    for index in range(count):
        pos = 40 + index * 28
        key, number, padding, snr, sns, snr_size, sns_size, last = struct.unpack_from(">IHH5I", data, pos)
        snr, sns = snr * 16, sns * 128
        array_bounds(data, snr, snr_size, 1)
        array_bounds(data, sns, sns_size, 1)
        entries.append(dict(offset=pos, hash=f"{key:08X}", number=number, padding=padding,
                            snr_offset=snr, snr_size=snr_size, sns_offset=sns, sns_size=sns_size, final_word=last))
    return dict(header_hex=data[:40].hex(), entries=entries,
                note="SNR/SNS descriptors only; adaptive music ordering and codec decoding require separate tools.")


def parse_tox(data: bytes) -> dict:
    require(len(data) >= 16 and data[:4] == b"1BOT", "invalid TOX header")
    require(word(data, 4) == len(data) and 16 + word(data, 12) * 16 == len(data), "TOX size/count mismatch")
    return dict(magic="1BOT", word_08=word(data, 8), cues=[dict(offset=pos, string_id=f"{sid:08X}",
                start_ms=start, duration_ms=duration, flags=f"{flags:08X}")
                for pos in range(16, len(data), 16)
                for sid, start, duration, flags in [struct.unpack_from(">4I", data, pos)]])


def parse_bindings(data: bytes) -> dict:
    parse_bbn(data)  # Shared strict table and index validation.
    aliases, rigs, rig_start, alias_start = struct.unpack_from(">4I", data, 24)
    rig_rows = [dict(name=string(data, word(data, pos)), hash=f"{word(data, pos + 4):08X}", offset=pos)
                for pos in range(rig_start, rig_start + rigs * 8, 8)]
    alias_rows = [dict(name=string(data, word(data, pos)), hash=f"{word(data, pos + 4):08X}",
                      rig_index=word(data, pos + 8), flags=word(data, pos + 12), offset=pos)
                  for pos in range(alias_start, alias_start + aliases * 16, 16)]
    return dict(rigs=rig_rows, aliases=alias_rows, note="Bounded documented BBN layout; animation poses are unresolved.")


def parse_streamset(data: bytes) -> dict:
    require(len(data) >= 8 and word(data, 0) == 3, "unsupported StreamSetConfig header")
    count = word(data, 4)
    array_bounds(data, 8, count, 16)
    rows = [dict(offset=pos, words=list(struct.unpack_from(">4I", data, pos)))
            for pos in range(8, 8 + count * 16, 16)]
    pool = data[8 + count * 16:]
    names = [s.decode("cp1252", "replace") for s in pool.split(b"\0") if s]
    return dict(version=3, entries=rows, string_pool=names,
                note="16-byte entries and terminal strings are documented observations; individual pointer/flag meanings remain tentative.")


def parse_partial(data: bytes, kind: str) -> dict:
    """Expose only documented header fields in incompletely understood families."""
    result: dict = {"format": kind, "size": len(data), "note": "Partial documented observations; opaque bodies and runtime semantics remain unresolved."}
    if kind == ".amb":
        require(len(data) >= 128 and data[64:68] == b"ABKC", "missing AMB ABKC marker")
        result.update(version_candidate=word(data, 0), configuration_hex=data[68:76].hex(),
                      float_candidates=list(struct.unpack_from(">3f", data, 24)),
                      header_words={f"{p:#04x}": f"{word(data, p):08X}" for p in range(0, 128, 4)})
    elif kind == ".mib":
        require(len(data) >= 48, "short MIB header")
        result.update(record_count_candidate=word(data, 32), word_24=word(data, 36),
                      state_flags_candidate=word(data, 40), master_id_candidate=f"{word(data, 44):08X}")
        count = word(data, 32)
        if len(data) == 48 + count * 44:
            result["standard_mix_records"] = [
                dict(offset=pos, target_hash_candidate=f"{word(data, pos):08X}",
                     dsp_float_candidates=list(struct.unpack_from(">8f", data, pos + 4)),
                     delimiter_or_type=word(data, pos + 36), next_size_candidate=word(data, pos + 40))
                for pos in range(48, len(data), 44)]
        else:
            result["record_layout"] = "Variable body does not match the documented standard 44-byte record array; retained as raw bytes."
    elif kind == ".msb":
        require(len(data) >= 84 and data[80:84] == b"PFDx", "missing MSB PFDx marker")
        pfd_map_size = word(data, 0x24)
        sig = word(data, 0x2C)
        paired_mus = data[0x30:0x50].split(b"\0")[0].decode("ascii", "replace").strip()
        version = word(data, 0x54)
        s7_off = 0x50 + word(data, 0x74)
        mus_id = f"{word(data, s7_off + 16):08X}" if s7_off + 20 <= len(data) else "unresolved"
        trailer_off = 0x50 + pfd_map_size
        events, parts, defines = [], [], []
        if trailer_off < len(data):
            trailer_text = data[trailer_off:].decode("latin-1", "replace")
            cur = None
            for line in [l.strip() for l in trailer_text.replace("\r\n", "\r").replace("\n", "\r").split("\r") if l.strip()]:
                if line.startswith("numevents"):
                    cur = "events"
                elif line.startswith("numparts"):
                    cur = "parts"
                elif line.startswith("numdefines"):
                    cur = "defines"
                elif cur == "events" and ":" in line:
                    k, v = line.split(":", 1)
                    events.append(dict(name=k.strip(), id=v.strip()))
                elif cur == "parts":
                    parts.append(line)
                elif cur == "defines":
                    defines.append(line)
        result.update(marker_offset=80, pfd_map_size=pfd_map_size, format_signature=f"{sig:08X}",
                      paired_mus=paired_mus, pfd_version=version, mus_file_id=mus_id,
                      event_count=len(events), part_count=len(parts), define_count=len(defines),
                      events=events[:20], parts=parts[:20], defines=defines[:20])
    elif kind == ".xml.ps3":
        require(len(data) >= 20 and data[:4] == b"seqm", "missing compiled sequence seqm marker")
        result["seqm_words"] = [word(data, p) for p in range(4, 20, 4)]
        result["seqb_observations"] = [m.start() for m in re.finditer(b"seqb", data)]
    elif kind == ".sbk":
        require(data[:4] == b"knbs", "missing SBK knbs marker")
        result["signature"] = "knbs"
        result["note"] += " Audio decoding is delegated to vgmstream; this is not a BNK animation bank."
    elif kind == ".uix":
        require(data[:4] == b"uixf", "missing UIX uixf marker")
        result["marker_observations"] = [dict(offset=m.start(), tag=m.group().decode()) for m in re.finditer(rb"uixf|titl|alig|apti|Apt Data:74", data)]
    elif kind == ".itxd":
        require(len(data) >= 0x4B0 and data[:4] == b"uz\0\3", "unsupported Xbox ITXD header")
        size = word(data, 0xE0)
        array_bounds(data, 0x4B0, size, 1)
        result.update(texture_name=data[0x38:0x78].split(b"\0")[0].decode("ascii", "replace"),
                      width=word(data, 0xAC), height=word(data, 0xB0), bits_per_pixel=word(data, 0xB4),
                      mip_count=word(data, 0xDC), payload_size=size, payload_offset=0x4B0,
                      plugin_guid_hex=data[0x7E:0x86].hex(), xenos_fetch_hex=data[0xF8:0x110].hex(),
                      note="Xbox 360 structural metadata only. Xenos untile/pixel conversion is not implemented by the PS3 TXD converter.")
    elif kind == ".bin":
        require(len(data) >= 32 and data[:4] == b"SCE\0", "not the documented SCE executable wrapper")
        result.update(signature="SCE", version=word(data, 4), opening_32_bytes=data[:32].hex())
    elif kind == ".elf":
        require(len(data) >= 32 and data[:4] == b"\x7fELF", "not an ELF executable")
        is_64 = data[4] == 2
        endian = ">" if data[5] == 2 else "<"
        entry = struct.unpack_from(f"{endian}{'Q' if is_64 else 'I'}", data, 24)[0]
        result.update(signature="ELF", elf_class="ELF64" if is_64 else "ELF32",
                      endian="BE" if endian == ">" else "LE", entry_point=f"{entry:#x}",
                      opening_32_bytes=data[:32].hex())
    elif kind == ".snu":
        require(len(data) >= 16, "short SNU wrapper")
        result["header_hex"] = data[:16].hex()
        result["endian_candidates"] = {order: {f"{p:#x}": word(data, p, prefix) for p in (4, 8, 12)}
                                       for order, prefix in (("BE", ">"), ("LE", "<"))
                                       if 16 <= word(data, 8, prefix) < len(data)}
        result["note"] += " SNU variants require codec validation; endian candidates are not a confirmed decode."
    elif kind == ".vp6":
        result["marker_observations"] = [dict(offset=m.start(), tag=m.group().decode()) for m in re.finditer(rb"SCHl|MVhd|vp60", data)]
    else:
        result["header_hex"] = data[:64].hex()
    # Strings are explicitly observations, never invented pointers or dependencies.
    result["string_observations"] = [dict(offset=m.start(), text=m.group().decode("ascii"))
                                     for m in islice(re.finditer(rb"[\x20-\x7e]{5,180}", data), 1000)]
    return result


READERS = {".inf": parse_font, ".imb": parse_impact, ".vfb": parse_effect, ".bsp": parse_bsp,
           ".mus": parse_music, ".tox.ps3": parse_tox, ".bbn.ps3": parse_bindings,
           ".acs.ps3": parse_acs, ".hkt.ps3": inspect_havok, ".hko.ps3": inspect_havok,
           "streamsetconfig": parse_streamset}

"""One resource dispatcher for standalone files and exact STR payloads."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import PurePosixPath
import math
import struct

from .audio import parse_lh2, parse_alb, parse_smb, require, word
from .identifiers import parse_identifiers
from .resources import READERS, parse_partial, array_bounds


PARTIAL = {".amb", ".aub", ".bnk.ps3", ".ctb", ".mib", ".msb", ".rcb.ps3", ".rcm_b",
           ".sbk", ".toc", ".uix", ".xml.ps3", ".ps3", ".itxd", ".bin", ".snu", ".vp6"}
LEGACY = {".graph", ".meta.xml", ".cec.ps3", ".shk.ps3", ".preinstanced", ".txd", ".rws", ".dff", ".tob"}
SUPPORTED_SUFFIXES = tuple(sorted({".str", ".lh2", ".alb", ".smb", ".dat", ".dat.uie", ".dat.simgroup",
                                  ".simgroup.dat", ".txt", ".lua", ".lighttoc", ".shk", ".wav", ".ogg", ".mp3", ".flac", ".snr", ".ogv", ".mp4", ".avi", ".webm", ".png", ".dds", ".jpg", ".jpeg", ".bmp", ".tga", ".json", ".csv", ".yaml", ".yml", ".toml", ".fnt", ".srt", ".vtt", ".xml",
                                  *READERS.keys(), *PARTIAL, *LEGACY} - {"streamsetconfig"}, key=len, reverse=True))
RESOURCE_KINDS = {"UIE": ".dat.uie", "CEC": ".cec.ps3", "SHK": ".shk.ps3", "TOB": ".tox.ps3",
                  "TOX": ".tox.ps3", "METAMODEL": ".meta.xml", "GRAPH": ".graph",
                  "EARS_MESH": ".preinstanced", "LIGHTTOC": "lighttoc", "STREAMSETCONFIG": "streamsetconfig"}


def identify(name: str, resource: str = "", data: bytes = b"") -> str:
    name = name.replace("\\", "/").lower()
    base = PurePosixPath(name).name
    if resource.upper() == "UIE":
        return ".dat.uie"
    if data[8:12] == b"SimG" or data[4:8] == b"SimG":
        return ".dat.simgroup"
    if base in {"lighttoc", "streamsetconfig"}:
        return base
    kind = next((s for s in SUPPORTED_SUFFIXES if name.endswith(s)), "")
    if kind == ".simgroup.dat":
        return ".dat.simgroup"
    if kind in {"", ".dat", ".ps3"} and resource.upper() in RESOURCE_KINDS:
        return RESOURCE_KINDS[resource.upper()]
    if kind:
        return ".shk.ps3" if kind == ".shk" else kind
    for magic, suffix in ((b"2HCL", ".lh2"), (b"FONT", ".inf"), (b"1BOT", ".tox.ps3"),
                          (b"Hkx", ".hkt.ps3"), (b"seqm", ".xml.ps3"), (b"uixf", ".uix")):
        if data.startswith(magic):
            return suffix
    return ""


def tree_nodes(value: object, label: str = "Structure", budget: int = 6000) -> list[dict]:
    remaining = [budget]

    def visit(item: object, title: str) -> dict:
        remaining[0] -= 1
        if isinstance(item, (dict, list, tuple)):
            children = []
            pairs = item.items() if isinstance(item, dict) else enumerate(item)
            for key, child in pairs:
                if remaining[0] <= 0:
                    children.append({"label": "Display limit reached; Export JSON retains the complete structure."})
                    break
                children.append(visit(child, str(key)))
            return {"label": f"{title} ({len(item)})", "children": children}
        return {"label": f"{title}: {item}"}

    return [visit(value, label)]


def json_values(value: object) -> object:
    """Preserve non-finite unknown float candidates as strings for valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: json_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_values(item) for item in value]
    return value


def localization_table(data: bytes) -> dict:
    values = parse_lh2(data)
    count = word(data, 20)
    columns = ["EN", "FR", "IT", "ES", "Label"] if count == 5 else [f"Column {i}" for i in range(count)]
    return dict(headers=["StringID", *columns], rows=[[f"{sid:08X}", *texts] for sid, texts, _ in values],
                summary=f"LH2: {len(values)} rows, {count} columns; Windows-1252 source bytes")


def parse_resource(data: bytes, name: str = "", resource: str = "") -> dict:
    kind = identify(name, resource, data)
    # Correct full-body coordinates for legacy BMS SimGroup dumps. The dump may
    # include later records; only the reachable group structures are interpreted.
    note = ""
    if kind == ".dat.simgroup" and data[4:8] == b"SimG":
        data = b"\0" * 4 + data
        note = "Legacy SimGroup body base restored by +4; a legacy dump may contain a trailing section tail. "
    if kind in READERS:
        structure = READERS[kind](data)
    elif kind == ".lh2":
        structure = {"rows": [dict(string_id=f"{sid:08X}", columns=list(columns), **location)
                              for sid, columns, location in parse_lh2(data)]}
    elif kind == ".alb":
        structure = {"version": 6, "records": [dict(offset=pos, alias=f"{alias:08X}", bank=f"{bank:08X}",
                     stream=f"{stream:08X}", string_id=f"{sid:08X}") for pos, alias, bank, stream, sid in parse_alb(data)]}
    elif kind == ".smb":
        structure = {"records": [dict(offset=pos, bank=f"{bank:08X}", stream=f"{stream:08X}", filename=filename)
                                  for pos, bank, stream, filename in parse_smb(data)]}
    elif kind == ".dat.uie":
        ids, _ = parse_identifiers(data, kind)
        structure = {"entries": [asdict(value) for value in ids]}
    elif kind in {".txt", ".lua"}:
        try:
            text, encoding = data.decode("utf-8-sig"), "UTF-8"
        except UnicodeDecodeError:
            text, encoding = data.decode("cp1252", "backslashreplace"), "Windows-1252"
        structure = dict(encoding=encoding, text=text, note="Source text is displayed without execution.")
    elif kind == "lighttoc" or kind == ".lighttoc":
        require(len(data) == 128 and data[:4] == b"\x40\xf2\0\1", "unsupported suffixless LightTOC layout")
        structure = dict(signature=data[:4].hex(), reserved_hex=data[4:16].hex(),
                         float_candidates=list(struct.unpack_from(">28f", data, 16)),
                         note="128-byte documented LightTOC sample layout; spatial/lighting semantics remain tentative.")
    elif kind in LEGACY or kind == ".dat.simgroup":
        # Keep existing detailed model/scene readers, guarded by current bounds.
        from str_reader import resource_parsers as legacy
        if kind == ".graph":
            require(len(data) >= 40, "short graph header")
            nodes, edges = struct.unpack_from(">2H", data, 12)
            array_bounds(data, word(data, 32), nodes, 32)
            array_bounds(data, word(data, 36), edges, 16)
            parsed = legacy.parse_graph(data)
        elif kind == ".meta.xml":
            parse_identifiers(data, kind)
            parsed = legacy.parse_metamodel(data)
        elif kind == ".cec.ps3":
            parse_identifiers(data, kind)
            parsed = legacy.parse_cec(data)
        elif kind == ".shk.ps3":
            require(len(data) >= 12, "short SHK header")
            count = struct.unpack_from(">h", data, 6)[0]
            array_bounds(data, 12, count, 4)
            parsed = legacy.parse_shk(data)
        elif kind == ".dat.simgroup":
            parse_identifiers(data, kind)
            parsed = legacy.parse_simgroup(data)
        elif kind == ".tob":
            parsed = legacy.parse_tob(data)
        elif kind == ".preinstanced":
            parsed = legacy.parse_ears_mesh_unified(data, {"FullPath": name, "ResourceType": resource})
        else:
            parsed = legacy.parse_rw_stream(data)
        structure = parsed
    else:
        structure = parse_partial(data, kind or "unidentified")
    ids, status = parse_identifiers(data, kind)
    summary = note + (f"{kind or 'Unidentified resource'}: documented structure" if kind not in PARTIAL and kind and kind != ".dat" else
                      f"{kind or 'Unidentified resource'}: partial observations; consult format limitations")
    structure = json_values(structure)
    result = dict(format=kind, structure=structure, identifiers=[asdict(value) for value in ids],
                  identifier_status=status, summary=summary)
    result["tree"] = tree_nodes({"structure": structure, "identifiers": result["identifiers"], "identifier_status": status})
    return result

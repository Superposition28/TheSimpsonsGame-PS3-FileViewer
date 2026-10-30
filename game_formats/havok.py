#!/usr/bin/env python3
"""Bounded PS3 Havok inspection, shared from docs/tools/inspect_havok_collision.py.

The documented 32-bit Havok 4.1 layout is validated without target execution.
Mesh totals cover every inspected object; example records are deliberately bounded.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def inspect_havok(data: bytes) -> dict:
    require(data[:16] == bytes.fromhex("486b7810090000000000000000000000"), "unknown Hkx wrapper")
    require(data[16:24] == bytes.fromhex("57e0e05710c0c010"), "unknown Havok magic")
    require(data[32:36] == bytes.fromhex("04000101"), "unsupported Havok layout rules")
    require(struct.unpack_from(">I", data, 28)[0] == 4, "unsupported packfile version")
    require(struct.unpack_from(">I", data, 36)[0] == 3, "expected three sections")
    sections = []
    for i in range(3):
        pos = 80 + 48 * i
        values = struct.unpack_from(">7I", data, pos + 20)
        start, *bounds = values
        require(bounds == sorted(bounds), "non-monotonic section boundaries")
        require(16 + start + bounds[-1] <= len(data), "section outside file")
        sections.append({"name": data[pos:pos + 19].split(b"\0")[0].decode("ascii"),
                         "packfile_relative_start": start, "file_start": start + 16,
                         "local_fixups": bounds[0], "global_fixups": bounds[1],
                         "virtual_fixups": bounds[2], "exports": bounds[3],
                         "imports": bounds[4], "end": bounds[5]})
    require([s["name"] for s in sections] == ["__classnames__", "__data__", "__types__"], "unknown sections")
    require(sections[2]["end"] == 0, "nonempty type section")
    require(sections[2]["file_start"] == len(data), "unexpected trailing bytes")
    cs = sections[0]
    pos, end = cs["file_start"], cs["file_start"] + cs["local_fixups"]
    classes = {}
    while pos + 5 <= end and data[pos:pos + 5] != b"\xff" * 5:
        require(data[pos + 4] == 9, "unknown class-name record marker")
        stop = data.index(b"\0", pos + 5, end)
        classes[pos + 5 - cs["file_start"]] = data[pos + 5:stop].decode("ascii")
        pos = stop + 1
    require(all(x == 255 for x in data[pos:end]), "unexpected class-name padding")
    ds = sections[1]
    base, data_end = ds["file_start"], ds["local_fixups"]

    def u32(offset: int) -> int:
        require(0 <= offset <= data_end - 4, "word outside data")
        return struct.unpack_from(">I", data, base + offset)[0]

    def floats(offset: int, count: int) -> tuple[float, ...]:
        require(0 <= offset <= data_end - 4 * count, "floats outside data")
        result = struct.unpack_from(">" + "f" * count, data, base + offset)
        require(all(math.isfinite(x) for x in result), "non-finite geometry value")
        return result

    def records(start: int, stop: int, width: int) -> list[tuple[int, ...]]:
        result = []
        pos = start
        while pos + width <= stop:
            row = struct.unpack_from(">" + "I" * (width // 4), data, base + pos)
            if row[0] == 0xFFFFFFFF:
                break
            result.append(row)
            pos += width
        require(all(x == 255 for x in data[base + pos:base + stop]), "unexpected fixup padding")
        return result

    local_rows = records(ds["local_fixups"], ds["global_fixups"], 8)
    global_rows = records(ds["global_fixups"], ds["virtual_fixups"], 12)
    virtual_rows = records(ds["virtual_fixups"], ds["exports"], 12)
    local = dict(local_rows)
    global_ = {source: (section, target) for source, section, target in global_rows}
    objects = {offset: classes[cls] for offset, section, cls in virtual_rows if section == 0}
    require(len(objects) == len(virtual_rows), "unknown virtual-fixup class section")
    for source, target in local_rows:
        require(0 <= source <= data_end - 4 and 0 <= target < data_end, "invalid local fixup")
        require(u32(source) == 0, "nonzero unresolved local pointer")
    for source, section, target in global_rows:
        require(0 <= source <= data_end - 4 and section < 3, "invalid global fixup")
        require(0 <= target < sections[section]["local_fixups"], "global target outside section data")
        require(u32(source) == 0, "nonzero unresolved global pointer")

    def pointed(source: int) -> int:
        if source in local:
            return local[source]
        section, target = global_[source]
        require(section == 1, "unexpected cross-section object pointer")
        return target

    def text(source: int) -> str:
        target = pointed(source)
        stop = data.index(b"\0", base + target, base + data_end)
        return data[base + target:stop].decode("ascii")

    counts = Counter(objects.values())
    totals = Counter()
    mesh_examples = []
    primitive_examples = []
    body_examples = []
    for obj, cls in objects.items():
        if cls == "EAStorageMeshShape":
            vertices, triangles, materials = u32(obj + 0x18), u32(obj + 0x24), u32(obj + 0xC4)
            vp, tp, mp = pointed(obj + 0x14), pointed(obj + 0x20), pointed(obj + 0xC0)
            require(vertices > 0 and triangles > 0, "empty mesh")
            require(vp + vertices * 16 <= data_end and tp + triangles * 12 <= data_end, "mesh array outside data")
            require(mp + materials * 4 <= data_end and materials == triangles, "material count differs from triangle count")
            xyz = [floats(vp + i * 16, 4) for i in range(vertices)]
            indices = struct.unpack_from(">" + "I" * (triangles * 3), data, base + tp)
            require(max(indices) < vertices, "triangle index outside vertex array")
            for i in range(materials):
                require(objects[pointed(mp + i * 4)] == "EAMaterial", "unknown mesh material target")
            totals.update(vertices=vertices, triangles=triangles, material_slots=materials)
            totals["vertex_w_nonzero"] += sum(v[3] != 0 for v in xyz)
            totals["nonadjacent_vertex_arrays"] += vp != obj + 0xD0
            totals["nonadjacent_triangle_arrays"] += tp != vp + vertices * 16
            if len(mesh_examples) < 2:
                mesh_examples.append({"object_offset": obj, "vertices": vertices, "triangles": triangles,
                                      "vertex_array": vp, "triangle_array": tp, "material_array": mp,
                                      "bbox_min": [min(v[k] for v in xyz) for k in range(3)],
                                      "bbox_max": [max(v[k] for v in xyz) for k in range(3)],
                                      "first_triangle": list(indices[:3])})
        elif cls in {"hkBoxShape", "hkSphereShape"}:
            primitive = {"object_offset": obj, "class": cls, "radius": floats(obj + 12, 1)[0]}
            require(primitive["radius"] > 0, "non-positive primitive radius")
            if cls == "hkBoxShape":
                primitive["half_extents_xyzw"] = floats(obj + 16, 4)
            primitive_examples.append(primitive)
        elif cls == "hkConvexVerticesShape":
            groups, vertex_count, planes = u32(obj + 0x34), u32(obj + 0x3C), u32(obj + 0x44)
            require(0 < vertex_count <= groups * 4, "invalid convex vertex count")
            floats(pointed(obj + 0x30), groups * 12)
            floats(pointed(obj + 0x40), planes * 4)
            totals.update(convex_vertices=vertex_count, convex_planes=planes)
        elif cls == "hkRigidBody":
            shape = pointed(obj + 0x1C)
            require(shape in objects, "body shape missing from virtual fixups")
            name = text(obj + 0x10)
            transform = floats(obj + 0xB0, 16)
            if len(body_examples) < (16 if counts["hkSphereShape"] else 2):
                body_examples.append({"object_offset": obj, "name": name, "shape_offset": shape,
                                      "shape_class": objects[shape], "transform_4x4_raw": transform})
        elif cls == "hkMoppBvTreeShape":
            require(objects[pointed(obj + 0x10)] == "EAStorageMeshShape", "unknown MOPP child shape")
            require(objects[pointed(obj + 0x14)] == "hkMoppCode", "unknown MOPP code target")

    require(objects.get(0) == "EAPhysicsSystem", "unknown root object")
    return {"wrapper_hex": data[:16].hex(), "packfile_version": 4,
            "layout_rules_hex": data[32:36].hex(), "contents_version": data[56:72].split(b"\0")[0].decode(),
            "sections": sections, "fixup_counts": {"local": len(local_rows), "global": len(global_rows), "virtual": len(virtual_rows)},
            "instantiated_classes": dict(sorted(counts.items())), "mesh_validation": dict(totals),
            "mesh_examples": mesh_examples, "primitive_examples": primitive_examples, "body_examples": body_examples}


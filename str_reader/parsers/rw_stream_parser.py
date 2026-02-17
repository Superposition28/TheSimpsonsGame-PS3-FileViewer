"""Parser for RenderWare Stream resources."""
import struct


def parse_rw_stream(data):
    """Parse RenderWare stream chunk hierarchy.

    Args:
        data: Raw bytes of RW stream data

    Returns:
        Dict with tree structure describing the RW hierarchy
    """
    nodes = []

    def read_u32_le_at(offset):
        if offset + 4 > len(data):
            return None
        return struct.unpack_from("<I", data, offset)[0]

    rw_names = {
        1: "Struct",
        2: "String",
        3: "Extension",
        0x10: "Clump",
        0x14: "Atomic",
        0x0F: "Geometry",
        0x17: "TextureNative",
        0x1A: "Material",
        0x0E: "FrameList",
        0x16: "TextureDict",
    }
    container_types = {0x10, 0x16, 0x0E, 0x14, 0x0F, 0x1A}

    def read_section(start_offset, parent, depth):
        if depth > 50:
            return
        if start_offset + 12 > len(data):
            return
        chunk_type = read_u32_le_at(start_offset)
        chunk_size = read_u32_le_at(start_offset + 4)
        lib_id = read_u32_le_at(start_offset + 8)
        if chunk_type is None or chunk_size is None or lib_id is None:
            return
        if chunk_size > len(data):
            return

        name = rw_names.get(chunk_type, f"Unknown(0x{chunk_type:X})")
        node = {"label": f"{name} (Size: {chunk_size})", "children": []}
        parent.append(node)

        if chunk_type in container_types:
            end_pos = start_offset + 12 + chunk_size
            current_pos = start_offset + 12
            while current_pos + 12 <= end_pos and current_pos + 12 <= len(data):
                child_size = read_u32_le_at(current_pos + 4)
                if child_size is None or child_size > len(data):
                    break
                read_section(current_pos, node["children"], depth + 1)
                current_pos += 12 + child_size

    current = 0
    while current + 12 <= len(data):
        read_section(current, nodes, 0)
        root_size = read_u32_le_at(current + 4)
        if root_size is None:
            break
        next_pos = current + 12 + root_size
        if next_pos <= current:
            break
        current = next_pos

    return {"tree": nodes, "summary": "RenderWare Stream Hierarchy"}

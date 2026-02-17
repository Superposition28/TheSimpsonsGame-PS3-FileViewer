"""Parser for Preinstanced Mesh resources and unified EARS_MESH."""
import struct
from ..binary_reader import BinaryReader
from .common import read_ascii_string, scan_all_texture_strings, find_all_occurrences

## old
"""
def parse_ears_mesh(data):
    " ""Parse EARS_MESH resource as simple table (legacy format).

    Args:
        data: Raw bytes of EARS_MESH resource

    Returns:
        Dict with table structure describing submeshes
    "" "
    reader = BinaryReader(data)

    if len(data) < 36:
        return {"headers": ["Index"], "rows": [], "summary": "EARS_MESH data too small"}

    header_offset = data.find(b"\x33\xEA\x00\x00")
    if header_offset < 0:
        header_offset = data.find(b"\x16\xEA\x00\x00")

    if header_offset < 0:
        return {
            "headers": ["Index"],
            "rows": [],
            "summary": "EARS_MESH section header not found",
        }

    base_offset = header_offset + 12
    if base_offset >= len(data):
        return {
            "headers": ["Index"],
            "rows": [],
            "summary": "EARS_MESH section header truncated",
        }

    reader.seek(base_offset)
    reader.read_bytes(20)
    data_block_offset = reader.read_u32()
    data_block_size = reader.read_u32()
    reader.read_bytes(4)
    table_entry_count = reader.read_u32()
    submesh_count = reader.read_u32()

    if table_entry_count > 4096 or submesh_count > 4096:
        return {
            "headers": ["Index"],
            "rows": [],
            "summary": f"EARS_MESH invalid counts (table {table_entry_count}, submesh {submesh_count})",
        }

    max_table_entries = (len(data) - reader.pos()) // 8
    for _ in range(min(table_entry_count, max_table_entries)):
        reader.read_bytes(8)

    submesh_headers = []
    max_submesh_headers = (len(data) - reader.pos()) // 12
    for _ in range(min(submesh_count, max_submesh_headers)):
        reader.read_bytes(4)
        submesh_headers.append(
            {
                "size": reader.read_u32(),
                "offset": reader.read_u32(),
            }
        )

    rows = []
    for idx, header in enumerate(submesh_headers):
        info_offset = header["offset"] + 12
        if info_offset <= 0 or info_offset + 16 > len(data):
            continue
        reader.seek(info_offset)
        reader.read_bytes(4)
        shader_hash = reader.read_u32()
        unk0 = reader.read_u32()
        mddb_offset = reader.read_u32()
        split_count = reader.read_u32()

        mddb_pos = mddb_offset + 12
        if mddb_pos <= 0 or mddb_pos + 64 > len(data):
            continue
        reader.seek(mddb_pos)
        vertex_block_size = reader.read_u32()
        vertex_entry_size = reader.read_u32()
        unk1 = reader.read_u32()
        unk2 = reader.read_u32()
        vertex_block_offset = reader.read_u32()
        unk3 = reader.read_u32()
        unk4 = reader.read_u32()
        unk5 = reader.read_u32()
        unk6 = reader.read_u32()
        unk7 = reader.read_u32()
        strip_block_size = reader.read_u32()
        unk8 = reader.read_u32()
        strip_block_offset = reader.read_u32()
        center_x = reader.read_f32()
        center_y = reader.read_f32()
        center_z = reader.read_f32()
        sphere_radius = reader.read_f32()

        vertex_count = 0
        if vertex_entry_size:
            vertex_count = int(vertex_block_size // vertex_entry_size)

        rows.append(
            [
                idx,
                f"0x{shader_hash:08X}",
                split_count,
                vertex_entry_size,
                vertex_block_size,
                vertex_count,
                strip_block_size,
                f"{center_x:.3f},{center_y:.3f},{center_z:.3f}",
                f"{sphere_radius:.3f}",
                f"0x{vertex_block_offset:08X}",
                f"0x{strip_block_offset:08X}",
            ]
        )

    summary = (
        f"EARS_MESH submeshes {len(rows)} dataBlock 0x{data_block_offset:08X} "
        f"size {data_block_size} tableEntries {table_entry_count}"
    )

    return {
        "headers": [
            "Index",
            "ShaderHash",
            "SplitCount",
            "VertexEntrySize",
            "VertexBlockSize",
            "VertexCount",
            "StripBlockSize",
            "BoundsCenter",
            "BoundsRadius",
            "VertexBlockOff",
            "StripBlockOff",
        ],
        "rows": rows,
        "summary": summary,
    }
"""


def scan_texture_events(data):
    """Scan for texture headers, TLFD markers, and mesh chunks.

    Returns:
        tuple: (events list, all_texture_names set, mesh_offsets list, diagnostics dict)
        events: List of (offset, type, payload) tuples sorted by offset
    """
    # Texture header variants from preinstanced spec
    TEX_HDR_VARIANTS = [
        b"\x02\x11\x01\x00\x02\x00\x00\x00\x14\x00\x00\x00\x2D\x00\x02\x1C",
        b"\x02\x11\x01\x00\x02\x00\x00\x00\x18\x00\x00\x00\x2D\x00\x02\x1C",
        b"\x02\x11\x01\x00\x02\x00\x00\x00\x10\x00\x00\x00\x2D\x00\x02\x1C",
        b"\x02\x11\x01\x00\x02\x00\x00\x00\x0C\x00\x00\x00\x2D\x00\x02\x1C",
        b"\x02\x11\x01\x00\x02\x00\x00\x00\x1C\x00\x00\x00\x2D\x00\x02\x1C",
        b"\x02\x11\x01\x00\x02\x00\x00\x00\x20\x00\x00\x00\x2D\x00\x02\x1C",
    ]
    TLFD_MARKER = b"TLFD"
    MESH_SIG_START = b"\x33\xEA\x00\x00"
    MESH_SIG_VERIFY = b"\x2D\x00\x02\x1C"  # Should appear at +8 from mesh start

    events = []
    all_textures = set()
    mesh_offsets = []
    diagnostics = {
        "header_matches": 0,
        "tlfd_matches": 0,
        "mesh_matches": 0,
        "strings_from_headers": 0,
        "strings_from_scan": 0,
        "failed_string_extractions": 0,
        "extraction_failures": [],  # Track detailed failure info
    }

    # Strategy 1: Find texture headers and extract names (precise method)
    # Try multiple offsets to handle variable padding after header
    STRING_OFFSETS_TO_TRY = [16, 20, 24, 17, 18, 12, 28]  # Common alignment values

    for hdr_idx, hdr in enumerate(TEX_HDR_VARIANTS):
        for offset in find_all_occurrences(data, hdr):
            diagnostics["header_matches"] += 1
            name = None

            # Try multiple offsets to find the string
            for string_offset in STRING_OFFSETS_TO_TRY:
                name = read_ascii_string(data, offset + string_offset, 64, min_len=4)
                if name:
                    events.append((offset, "tex", name))
                    all_textures.add(name)
                    diagnostics["strings_from_headers"] += 1
                    break

            if not name:
                diagnostics["failed_string_extractions"] += 1
                # Record failure details for debugging
                if len(diagnostics["extraction_failures"]) < 10:  # Limit to first 10 failures
                    sample_start = offset + 16
                    sample_end = min(len(data), offset + 48)
                    sample_bytes = data[sample_start:sample_end]
                    diagnostics["extraction_failures"].append({
                        "header_offset": f"0x{offset:X}",
                        "expected_string_offset": f"0x{offset + 16:X}",
                        "bytes_at_location": sample_bytes.hex(' ', 1)[:64],  # First 32 bytes
                    })

    # Strategy 2: If no textures found via headers, scan for likely texture strings
    if not all_textures:
        candidates = scan_all_texture_strings(data)
        for name in candidates:
            all_textures.add(name)
            diagnostics["strings_from_scan"] += 1

    # Find TLFD markers
    for offset in find_all_occurrences(data, TLFD_MARKER):
        events.append((offset, "tlfd", None))
        diagnostics["tlfd_matches"] += 1

    # Find mesh chunks (with signature verification)
    for offset in find_all_occurrences(data, MESH_SIG_START):
        # Verify the mesh signature pattern
        if offset + 12 <= len(data):
            if data[offset + 8:offset + 12] == MESH_SIG_VERIFY:
                events.append((offset, "mesh", None))
                mesh_offsets.append(offset)
                diagnostics["mesh_matches"] += 1

    # Sort events by offset for sequential processing
    events.sort(key=lambda x: x[0])

    return events, all_textures, mesh_offsets, diagnostics


def build_texture_mesh_links(events, mesh_offsets):
    """Build texture-to-mesh associations using TLFD markers.

    Algorithm from Blender import script:
    - Accumulate texture names in a pending list
    - When TLFD is encountered, snapshot the pending list
    - Next mesh after TLFD gets the snapshot
    - If no TLFD, mesh gets current pending list

    Returns:
        dict: {mesh_offset: [texture_names]}
    """
    links = {}
    pending_textures = []
    snapshot_after_tlfd = None

    for offset, event_type, payload in events:
        if event_type == "tex":
            pending_textures.append(payload)
        elif event_type == "tlfd":
            # Snapshot current pending textures for next mesh
            snapshot_after_tlfd = pending_textures.copy() if pending_textures else []
        elif event_type == "mesh":
            if snapshot_after_tlfd is not None:
                links[offset] = snapshot_after_tlfd.copy()
                snapshot_after_tlfd = None
                pending_textures.clear()
            elif pending_textures:
                links[offset] = pending_textures.copy()
                pending_textures.clear()
            # else: no textures for this mesh

    return links


def parse_submesh_tree(data, chunk_start, face_off, submesh_rel_off, index):
    """Parse a single sub-mesh and return tree node with structure info."""
    abs_offset = chunk_start + submesh_rel_off

    if abs_offset + 16 > len(data):
        return {"label": f"Sub-Mesh {index} [offset out of bounds]"}

    reader = BinaryReader(data)
    reader.seek(abs_offset + 12)  # Skip 12 unknown bytes

    try:
        vert_info_rel_off = reader.read_u32()  # Big-endian
        vert_info_abs_off = chunk_start + vert_info_rel_off

        if vert_info_abs_off + 48 > len(data):
            return {"label": f"Sub-Mesh {index} [vertex info out of bounds]"}

        # Read vertex info header (all big-endian)
        reader.seek(vert_info_abs_off)
        vert_total_size = reader.read_u32()
        vert_stride = reader.read_u32()
        reader.read_bytes(4)  # Unknown
        vert_start_rel = reader.read_u32()
        reader.read_bytes(20)  # Unknown
        face_byte_len = reader.read_u32()
        reader.read_bytes(4)  # Unknown
        face_start_rel = reader.read_u32()

        # Calculate counts
        vert_count = vert_total_size // vert_stride if vert_stride > 0 else 0
        face_index_count = face_byte_len // 2

        # Calculate absolute offsets
        vert_data_off = chunk_start + face_off + vert_start_rel
        face_data_off = chunk_start + face_off + face_start_rel

        return {
            "label": f"Sub-Mesh {index}",
            "children": [
                {"label": f"Vertex Count: {vert_count}"},
                {"label": f"Vertex Stride: {vert_stride} bytes (0x{vert_stride:X})"},
                {"label": f"Face Index Count: {face_index_count}"},
                {"label": f"Vertex Data Offset: 0x{vert_data_off:08X}"},
                {"label": f"Face Data Offset: 0x{face_data_off:08X}"},
                {"label": f"Sub-Mesh Header: 0x{abs_offset:08X}"},
                {"label": f"Vertex Info Header: 0x{vert_info_abs_off:08X}"},
            ]
        }
    except Exception as e:
        return {"label": f"Sub-Mesh {index} [parse error: {e}]"}


def parse_mesh_chunk_tree(data, mesh_offset, index, tex_links):
    """Parse a single mesh chunk and return detailed tree node."""
    reader = BinaryReader(data)

    try:
        reader.seek(mesh_offset + 12)  # Skip signature and unknown
        reader.read_bytes(4)  # Unknown padding

        # CRITICAL: These two fields are LITTLE-ENDIAN (mixed-endian format)
        face_data_off = struct.unpack("<I", reader.read_bytes(4))[0]
        mesh_data_size = struct.unpack("<I", reader.read_bytes(4))[0]

        mesh_chunk_start = reader.pos()  # Position after MeshDataSize (0x18 from chunk start)

        # Back to big-endian for everything else
        reader.read_bytes(28)  # Unknown
        table_count = reader.read_u32()  # Big-endian
        submesh_count = reader.read_u32()  # Big-endian

        # Validate counts
        if table_count > 4096 or submesh_count > 4096:
            return {
                "label": f"Mesh {index} [invalid counts: table={table_count}, submesh={submesh_count}]"
            }

        # Skip table entries (8 bytes each)
        table_skip = min(table_count, (len(data) - reader.pos()) // 8)
        reader.read_bytes(table_skip * 8)

        # Parse sub-mesh entries (12 bytes each)
        submesh_nodes = []
        max_submeshes = min(submesh_count, (len(data) - reader.pos()) // 12)

        for i in range(max_submeshes):
            reader.read_bytes(8)  # Unknown
            submesh_rel_offset = reader.read_u32()  # Big-endian

            submesh_node = parse_submesh_tree(
                data, mesh_chunk_start, face_data_off, submesh_rel_offset, i
            )
            submesh_nodes.append(submesh_node)

        # Get linked textures
        linked_textures = tex_links.get(mesh_offset, [])
        tex_info = ", ".join(linked_textures) if linked_textures else "(none)"

        return {
            "label": f"Mesh {index} ({submesh_count} sub-meshes)",
            "children": [
                {"label": f"Mesh Chunk Offset: 0x{mesh_offset:08X}"},
                {"label": f"FaceDataOff: 0x{face_data_off:08X} (LE)"},
                {"label": f"MeshDataSize: {mesh_data_size} bytes (0x{mesh_data_size:X}) (LE)"},
                {"label": f"MeshChunkStart: 0x{mesh_chunk_start:08X}"},
                {"label": f"Table Entry Count: {table_count}"},
                {"label": f"Sub-Mesh Count: {submesh_count}"},
                {"label": f"Linked Textures: {tex_info}"},
                {"label": f"Sub-Meshes ({len(submesh_nodes)})", "children": submesh_nodes},
            ]
        }
    except Exception as e:
        return {"label": f"Mesh {index} [parse error: {e}]"}


def parse_preinstanced(data):
    """Parse preinstanced mesh file (.dff.preinstanced, .rws.preinstanced, EARS_MESH).

    Displays:
    - Texture strings with associations
    - Mesh chunk structure
    - Sub-mesh details (vertex/face counts, offsets)
    - Proper mixed-endian handling

    Returns tree structure with full hierarchy.
    """
    if len(data) < 100:
        return {
            "tree": [{"label": "File too small for preinstanced format"}],
            "summary": "Preinstanced: File too small"
        }

    # Phase 1: Scan for all events
    events, all_textures, mesh_offsets, diagnostics = scan_texture_events(data)

    # Phase 2: Build texture-mesh associations
    tex_links = build_texture_mesh_links(events, mesh_offsets)

    # Phase 3: Parse each mesh chunk
    mesh_nodes = []
    for i, mesh_off in enumerate(mesh_offsets):
        mesh_node = parse_mesh_chunk_tree(data, mesh_off, i, tex_links)
        mesh_nodes.append(mesh_node)

    # Build texture list with association info
    texture_nodes = []
    for tex_name in sorted(all_textures):
        # Find which meshes use this texture
        linked_meshes = []
        for mesh_idx, mesh_off in enumerate(mesh_offsets):
            if tex_name in tex_links.get(mesh_off, []):
                linked_meshes.append(mesh_idx)

        link_info = f" → Meshes: {', '.join(map(str, linked_meshes))}" if linked_meshes else " (no mesh links)"
        texture_nodes.append({"label": f"{tex_name}{link_info}"})

    # Build diagnostic info
    diag_method = "header-based" if diagnostics["strings_from_headers"] > 0 else "full-scan"
    diag_nodes = [
        {"label": f"Texture Headers Found: {diagnostics['header_matches']}"},
        {"label": f"TLFD Markers Found: {diagnostics['tlfd_matches']}"},
        {"label": f"Mesh Signatures Found: {diagnostics['mesh_matches']}"},
        {"label": f"Strings from Headers: {diagnostics['strings_from_headers']}"},
        {"label": f"Failed String Extractions: {diagnostics['failed_string_extractions']}"},
        {"label": f"Strings from Full Scan: {diagnostics['strings_from_scan']}"},
        {"label": f"Detection Method: {diag_method}"},
        {"label": f"File Size: {len(data)} bytes (0x{len(data):X})"},
    ]

    # Add failure details if any
    if diagnostics["extraction_failures"]:
        failure_children = []
        for idx, failure in enumerate(diagnostics["extraction_failures"]):
            failure_children.append({
                "label": f"Failure {idx+1}: Header@{failure['header_offset']} String@{failure['expected_string_offset']} Bytes:[{failure['bytes_at_location']}]"
            })
        diag_nodes.append({
            "label": f"Extraction Failure Details ({len(diagnostics['extraction_failures'])} shown)",
            "children": failure_children
        })

    # Build complete tree
    tree_data = [
        {
            "label": f"Texture Strings ({len(all_textures)})",
            "children": texture_nodes if texture_nodes else [{"label": "(no textures found - check diagnostics)"}]
        },
        {
            "label": f"Mesh Chunks ({len(mesh_nodes)})",
            "children": mesh_nodes if mesh_nodes else [{"label": "(no meshes found)"}]
        },
        {
            "label": "Diagnostics",
            "children": diag_nodes
        }
    ]

    summary = f"Preinstanced: {len(mesh_nodes)} meshes, {len(all_textures)} textures ({diag_method})"

    return {"tree": tree_data, "summary": summary}


def parse_ears_mesh_unified(data, metadata=None):
    """Parse EARS_MESH resource with unified view of RWS wrapper + preinstanced data.

    This is the primary parser for .rws and .dff EARS_MESH resources.
    Shows both the RWS metadata AND the embedded preinstanced mesh data as one unified tree.

    Args:
        data: Full asset data (RWS metadata + preinstanced payload)
        metadata: Optional dict with FileName, FullPath, ResourceType from chunk info

    Returns:
        Unified tree structure combining RWS metadata with preinstanced mesh/texture data
    """
    metadata = metadata or {}

    if len(data) < 100:
        return {
            "tree": [{"label": "Data too small"}],
            "summary": "EARS_MESH: Data too small"
        }

    # Find where preinstanced data begins (look for characteristic signatures)
    # Preinstanced data typically starts with texture headers or mesh signatures
    preinstanced_offset = None

    # Look for texture header signature
    for offset in range(0, len(data) - 16):
        # Check for texture header: 02 11 01 00 02 00 00 00 ... 2D 00 02 1C
        if (data[offset:offset+8] == b"\x02\x11\x01\x00\x02\x00\x00\x00" and
            offset + 15 < len(data) and
            data[offset+12:offset+16] == b"\x2D\x00\x02\x1C"):
            preinstanced_offset = offset
            break

    # If no texture header found, look for mesh signature
    if preinstanced_offset is None:
        mesh_sig = b"\x33\xEA\x00\x00"
        for offset in range(0, len(data) - 12):
            if (data[offset:offset+4] == mesh_sig and
                offset + 12 < len(data) and
                data[offset+8:offset+12] == b"\x2D\x00\x02\x1C"):
                preinstanced_offset = offset
                break

    # Build metadata section
    metadata_nodes = []
    if metadata:
        if metadata.get("FileName"):
            metadata_nodes.append({"label": f"Filename: {metadata['FileName']}"})
        if metadata.get("ResourceType"):
            metadata_nodes.append({"label": f"Resource Type: {metadata['ResourceType']}"})
        if metadata.get("FullPath"):
            metadata_nodes.append({"label": f"Full Path: {metadata['FullPath']}"})

    # Extract and parse preinstanced data if found
    preinstanced_nodes = []
    if preinstanced_offset is not None:
        preinstanced_data = data[preinstanced_offset:]
        preinstanced_result = parse_preinstanced(preinstanced_data)
        preinstanced_nodes = preinstanced_result.get("tree", [])
    else:
        preinstanced_nodes = [{"label": "Preinstanced data not found at expected offsets"}]

    # Build unified tree combining metadata and preinstanced data
    tree_data = []

    if metadata_nodes:
        tree_data.append({
            "label": "Resource Metadata",
            "children": metadata_nodes
        })

    tree_data.extend(preinstanced_nodes)

    summary = f"EARS_MESH: {metadata.get('FileName', 'Unknown')} - Preinstanced data at 0x{preinstanced_offset:X}" if preinstanced_offset else "EARS_MESH: Resource metadata + mesh data"

    return {"tree": tree_data, "summary": summary}

"""Parser for Navigation Graph resources."""
from ..binary_reader import BinaryReader
from .common import read_guid128


def parse_graph(data):
    """Parse Navigation Graph resource.
    
    Args:
        data: Raw bytes of graph resource
        
    Returns:
        Dict with tree structure describing nodes and connections
    """
    reader = BinaryReader(data)

    reader.read_bytes(12)

    n_nodes = reader.read_u16()
    n_connections = reader.read_u16()

    guid_bytes = reader.read_bytes(16)
    guid_str = "-".join(f"{b:02X}" for b in guid_bytes)

    node_array_offset = reader.read_u32()
    connection_array_offset = reader.read_u32()

    nodes = []
    if n_nodes > 0 and 0 <= node_array_offset < len(data):
        reader.seek(node_array_offset)
        for i in range(n_nodes):
            if reader.pos() + 32 > len(data):
                break

            x = reader.read_f32()
            y = reader.read_f32()
            z = reader.read_f32()
            radius = reader.read_f32()

            i_conn = reader.read_i16()
            prop_inst = reader.read_i16()
            n_conn = reader.read_u8()
            n_neighbor = reader.read_u8()
            i_neighbor = reader.read_i16()
            flags = reader.read_u16()

            reader.read_bytes(6)

            nodes.append(
                {
                    "label": f"Node {i}",
                    "children": [
                        {"label": f"Pos: ({x:.2f}, {y:.2f}, {z:.2f})"},
                        {"label": f"Radius: {radius:.2f}"},
                        {"label": f"Flags: 0x{flags:04X}"},
                        {"label": f"Connections: {n_conn} (Start Idx: {i_conn})"},
                        {"label": f"PropInstance: {prop_inst}"},
                        {"label": f"Neighbors: {n_neighbor} (Start Idx: {i_neighbor})"},
                    ],
                }
            )

    connections = []
    if n_connections > 0 and 0 <= connection_array_offset < len(data):
        reader.seek(connection_array_offset)
        for i in range(n_connections):
            if reader.pos() + 16 > len(data):
                break

            length = reader.read_f32()
            dst = reader.read_i16()
            src = reader.read_i16()
            prop = reader.read_i16()
            flags = reader.read_u16()
            blocked = reader.read_u8()
            reader.read_bytes(3)

            connections.append(
                {
                    "label": f"Edge {i}: {src} -> {dst}",
                    "children": [
                        {"label": f"Length: {length:.2f}"},
                        {"label": f"Flags: 0x{flags:04X}"},
                        {"label": f"Blocked: {blocked}"},
                        {"label": f"PropInstance: {prop}"},
                    ],
                }
            )

    tree_data = [
        {
            "label": "Header Info",
            "children": [
                {"label": f"GUID: {guid_str}"},
                {"label": f"Nodes: {n_nodes} (Offset: 0x{node_array_offset:X})"},
                {"label": f"Connections: {n_connections} (Offset: 0x{connection_array_offset:X})"},
            ],
        },
        {"label": f"Nodes ({len(nodes)})", "children": nodes},
        {"label": f"Connections ({len(connections)})", "children": connections},
    ]

    return {"tree": tree_data, "summary": f"Graph: {len(nodes)} nodes, {len(connections)} connections"}

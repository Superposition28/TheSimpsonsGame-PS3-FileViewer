"""Parser for SimGroup resources."""
import struct
from ..binary_reader import BinaryReader
from .common import read_guid128


def parse_simgroup(data):
    """Parse SimGroup resource with entity hierarchy.
    
    Args:
        data: Raw bytes of SimGroup resource
        
    Returns:
        Dict with tree structure describing entities and their attributes
    """
    reader = BinaryReader(data)

    reader.read_bytes(8)

    magic = reader.read_u32()
    if magic != 0x53696D47:
        return {"summary": "Invalid SimGroup magic", "tree": []}

    version = reader.read_u32()
    guid_hash = reader.read_u32()
    flags = reader.read_u32()
    n_ents = reader.read_u32()
    n_ents_dispatched = reader.read_u32()
    shared_data_size = reader.read_u32()
    dict_size = reader.read_u32()
    pp_ent_packets = reader.read_u32()

    if 0 <= pp_ent_packets < len(data):
        reader.seek(pp_ent_packets)
        p_ent_packets = reader.read_u32()
        if 0 <= p_ent_packets < len(data):
            reader.seek(p_ent_packets)

    entities = []

    for i in range(n_ents):
        if reader.pos() >= len(data):
            break

        reader.read_bytes(16)

        n_attr_handler_flags = reader.read_u8()
        spawn_mask = reader.read_u8()
        n_attached_res = reader.read_u8()
        n_attr_packets = reader.read_u8()

        reader.read_bytes(4)

        guid_offset = reader.read_i32()
        saved_pos = reader.pos()

        reader.seek(saved_pos - 4 + guid_offset)
        ent_guid = read_guid128(reader)
        reader.seek(saved_pos)

        behavior_id = reader.read_u32()

        attached_res = []
        saved_pos = reader.pos()
        for j in range(n_attached_res):
            reader.seek(saved_pos + (j * 4))
            offset = reader.read_i32()
            reader.seek(reader.pos() - 4 + offset)
            attached_res.append(read_guid128(reader))

        reader.seek(saved_pos + (4 * n_attached_res))

        attr_packets = []
        saved_pos = reader.pos()
        for j in range(n_attr_packets):
            reader.seek(saved_pos + (j * 4))
            offset = reader.read_i32()
            reader.seek(reader.pos() - 4 + offset)

            ap_guid = reader.read_u32()
            n_attrs = reader.read_u16()
            bitfield = reader.read_u32() if n_attrs > 16 else reader.read_u16()
            reader.align(4)

            attributes = []
            for k in range(n_attrs):
                is_set = (bitfield >> k) & 1
                if not is_set:
                    attr_data = reader.read_bytes(4)
                    val_int = int.from_bytes(attr_data, "big", signed=False)
                    val_float = struct.unpack(">f", attr_data)[0]
                    attributes.append(f"[{k}] 0x{val_int:X} ({val_float:.3f})")

            attr_packets.append(
                {
                    "label": f"Handler 0x{ap_guid:08X} ({n_attrs} attrs)",
                    "children": [{"label": a} for a in attributes],
                }
            )

        reader.seek(saved_pos + (4 * n_attr_packets))

        entities.append(
            {
                "label": f"Entity {i}: {ent_guid}",
                "children": [
                    {"label": f"Behavior: 0x{behavior_id:08X}"},
                    {"label": f"SpawnMask: {spawn_mask}"},
                    {
                        "label": f"Attached Resources ({len(attached_res)})",
                        "children": [{"label": r} for r in attached_res],
                    },
                    {
                        "label": f"Attribute Packets ({len(attr_packets)})",
                        "children": attr_packets,
                    },
                ],
            }
        )

    summary = f"SimGroup v{version} Entities: {len(entities)} GUID: 0x{guid_hash:08X}"
    return {"tree": entities, "summary": summary}

"""Parser for Electronic Arts Pathfinder Music Stream Bank (.msb) files."""
import struct
from ..binary_reader import BinaryReader


def parse_msb(data: bytes) -> dict:
    """Parse Electronic Arts Pathfinder v5.3 Music Stream Bank (.msb) file.
    
    Args:
        data: Raw bytes of the MSB file
        
    Returns:
        Dict with summary and tree structure representing the music bank layout,
        including outer header, PFDx sections, and ASCII .nam trailer symbols.
    """
    if len(data) < 84:
        return {"summary": "Truncated MSB file", "tree": []}

    # Outer EA Pathfinder header (80 bytes, 0x00..0x4F)
    pfd_map_size = struct.unpack_from(">I", data, 0x24)[0]
    signature = struct.unpack_from(">I", data, 0x2C)[0]
    paired_mus_raw = data[0x30:0x50].split(b"\0")[0]
    paired_mus = paired_mus_raw.decode("ascii", "replace").strip()

    # PFDx chunk (starts at 0x50)
    magic = data[0x50:0x54]
    if magic != b"PFDx":
        return {"summary": f"Invalid MSB PFDx magic: {magic!r}", "tree": []}

    version = struct.unpack_from(">I", data, 0x54)[0]
    section_offsets = list(struct.unpack_from(">9I", data, 0x58))

    # Section 7 contains the track header with the paired .mus checksum at offset +16
    mus_checksum_str = "Unknown"
    s7_off = 0x50 + section_offsets[7]
    if s7_off + 20 <= len(data):
        mus_checksum = struct.unpack_from(">I", data, s7_off + 16)[0]
        mus_checksum_str = f"0x{mus_checksum:08X}"

    # Parse .nam trailer at 0x50 + pfd_map_size
    trailer_offset = 0x50 + pfd_map_size
    events = []
    parts = []
    defines = []

    if trailer_offset < len(data):
        trailer_text = data[trailer_offset:].decode("latin-1", "replace")
        lines = [line.strip() for line in trailer_text.replace("\r\n", "\r").replace("\n", "\r").split("\r") if line.strip()]

        current_section = None
        for line in lines:
            if line.startswith("numevents"):
                current_section = "events"
                continue
            elif line.startswith("numparts"):
                current_section = "parts"
                continue
            elif line.startswith("numdefines"):
                current_section = "defines"
                continue

            if current_section == "events":
                if ":" in line:
                    ev_name, ev_id = line.split(":", 1)
                    events.append({"label": f"Event: {ev_name.strip()} (ID: {ev_id.strip()})"})
                else:
                    events.append({"label": line})
            elif current_section == "parts":
                parts.append({"label": f"Part: {line}"})
            elif current_section == "defines":
                defines.append({"label": f"Define: {line}"})

    tree = [
        {
            "label": "Pathfinder Container Header",
            "children": [
                {"label": f"Paired Container: {paired_mus}"},
                {"label": f"PFD Map Size: {pfd_map_size:,} bytes (0x{pfd_map_size:X})"},
                {"label": f"Format Signature: 0x{signature:08X}"},
                {"label": f"PFD Version: {version}"},
                {"label": f"Paired MUS Checksum: {mus_checksum_str}"},
            ],
        },
        {
            "label": f"PFD Chunk Sections ({len(section_offsets)})",
            "children": [
                {"label": f"Section 0 (Node Offsets): 0x{section_offsets[0]:X}"},
                {"label": f"Section 1 (Node Table): 0x{section_offsets[1]:X}"},
                {"label": f"Section 2 (Event Offsets): 0x{section_offsets[2]:X}"},
                {"label": f"Section 3 (Event Actions): 0x{section_offsets[3]:X}"},
                {"label": f"Section 4 (Branch Conditions): 0x{section_offsets[4]:X}"},
                {"label": f"Section 5: 0x{section_offsets[5]:X}"},
                {"label": f"Section 6: 0x{section_offsets[6]:X}"},
                {"label": f"Section 7 (Track Header & MUS ID): 0x{section_offsets[7]:X}"},
                {"label": f"Section 8 (Segments & Timing): 0x{section_offsets[8]:X}"},
            ],
        },
        {
            "label": f"Interactive Events ({len(events)})",
            "children": events,
        },
        {
            "label": f"Music Parts / Cues ({len(parts)})",
            "children": parts,
        },
        {
            "label": f"Engine Definitions ({len(defines)})",
            "children": defines,
        },
    ]

    summary = f"EA Pathfinder MSB v{version} -> {paired_mus} (Checksum: {mus_checksum_str}, Events: {len(events)}, Parts: {len(parts)})"
    return {"summary": summary, "tree": tree}


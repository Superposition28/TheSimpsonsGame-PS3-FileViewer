"""Parser for Text Overlay File (TOB) resources."""
from ..binary_reader import BinaryReader


def parse_tob(data):
    """Parse Text Overlay File resource.
    
    Args:
        data: Raw bytes of TOB resource
        
    Returns:
        Dict with table structure including headers, rows, and summary
    """
    reader = BinaryReader(data)

    chunk_id = reader.read_u32()
    file_size = reader.read_u32()
    version = reader.read_u32()
    entry_count = reader.read_u32()

    rows = []
    for i in range(entry_count):
        if reader.pos() + 16 > len(data):
            break
        hash_id = reader.read_u32()
        start_ms = reader.read_u32()
        duration_ms = reader.read_u32()
        user_data = reader.read_i32()
        rows.append([i, f"0x{hash_id:08X}", start_ms, duration_ms, user_data])

    summary = f"TOB v{version} entries {len(rows)} fileSize {file_size} chunk 0x{chunk_id:08X}"

    return {
        "headers": ["Index", "HashID", "StartMS", "DurationMS", "UserData"],
        "rows": rows,
        "summary": summary,
    }

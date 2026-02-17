"""Parser for Controller Event Config (CEC) resources."""
from ..binary_reader import BinaryReader
from .common import read_fixed_string, format_pad_pattern


def parse_cec(data):
    """Parse Controller Event Config resource.
    
    Args:
        data: Raw bytes of CEC resource
        
    Returns:
        Dict with table structure including headers, rows, and summary
    """
    reader = BinaryReader(data)

    version = reader.read_u8()
    reader.read_u8()
    event_count = reader.read_i16()
    config_hash = reader.read_u32()
    ref_count = reader.read_u8()
    config_name = read_fixed_string(reader, 33)
    config_location = read_fixed_string(reader, 143)

    if len(data) >= 0xC0:
        reader.seek(0xC0)

    events = []
    count = max(event_count, 0)
    for i in range(count):
        if reader.pos() + 1 > len(data):
            break

        event_hash = reader.read_u32()
        seq_len = reader.read_u8()
        event_name = read_fixed_string(reader, 26)
        event_category = read_fixed_string(reader, 13)

        patterns = []
        for _ in range(7):
            pattern = {
                "sticks_min": [reader.read_u8(), reader.read_u8()],
                "sticks_max": [reader.read_u8(), reader.read_u8()],
                "min_duration": reader.read_i16(),
                "max_duration": reader.read_i16(),
                "buttons_required": reader.read_u16(),
                "buttons_discarded": reader.read_u16(),
            }
            patterns.append(pattern)

        use_count = max(min(seq_len, 7), 0)
        sequence = " | ".join(format_pad_pattern(p) for p in patterns[:use_count])

        events.append(
            [
                i,
                f"0x{event_hash:08X}",
                event_name,
                event_category,
                seq_len,
                sequence,
            ]
        )

    summary = (
        f"CEC v{version} events {len(events)} name {config_name} ref {ref_count}\n"
        f"Location: {config_location} (hash 0x{config_hash:08X})"
    )

    return {
        "headers": ["Index", "Hash", "EventName", "Category", "SeqLen", "Sequence"],
        "rows": events,
        "summary": summary,
    }

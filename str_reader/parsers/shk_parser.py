"""Parser for Shock Resource (SHK) files."""
from ..binary_reader import BinaryReader


def parse_shk(data):
    """Parse Shock Resource file.
    
    Args:
        data: Raw bytes of SHK resource
        
    Returns:
        Dict with table structure including headers, rows, and summary
    """
    reader = BinaryReader(data)

    name_hash = reader.read_u32()
    version = reader.read_i16()
    command_count = reader.read_i16()
    reader.read_bytes(4)

    rows = []
    count = max(command_count, 0)
    for i in range(count):
        if reader.pos() + 4 > len(data):
            break
        time_offset = reader.read_u16()
        motor_id = reader.read_u8()
        actuator_value = reader.read_u8()
        rows.append([i, time_offset, motor_id, actuator_value])

    summary = f"SHK v{version} commands {len(rows)} nameHash 0x{name_hash:08X}"

    return {
        "headers": ["Index", "TimeOffset", "MotorId", "Actuator"],
        "rows": rows,
        "summary": summary,
    }

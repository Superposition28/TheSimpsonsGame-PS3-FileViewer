"""Common utilities and helper functions shared across all resource parsers."""
import struct
from ..binary_reader import BinaryReader


def read_fixed_string(reader, length):
    """Read a fixed-length null-terminated string from reader."""
    raw = reader.read_bytes(length)
    if not raw:
        return ""
    return raw.split(b"\x00")[0].decode("ascii", errors="replace")


def read_guid128(reader):
    """Read a 128-bit GUID and return as formatted hex string."""
    parts = [reader.read_u32(), reader.read_u32(), reader.read_u32(), reader.read_u32()]
    return "-".join(f"{part:08X}" for part in parts)


def read_matrix(reader):
    """Read a 4x4 matrix (16 floats) from reader."""
    return [reader.read_f32() for _ in range(16)]


def read_null_terminated_at(reader, offset):
    """Read a null-terminated string at absolute offset."""
    if offset < 0 or offset >= len(reader.data):
        return "<InvalidPointer>"
    saved = reader.pos()
    reader.seek(offset)
    raw = bytearray()
    while True:
        b = reader.read_bytes(1)
        if not b or b == b"\x00":
            break
        raw.extend(b)
    reader.seek(saved)
    try:
        return raw.decode("utf-8")
    except Exception:
        return raw.decode("latin-1", errors="replace")


def read_nt_string_ptr(reader, base_offset=0):
    """Read a relative pointer and dereference it as a null-terminated string."""
    ptr = reader.read_i32()
    target = base_offset + ptr
    return read_null_terminated_at(reader, target)


def mm_value_to_display(value_bytes, value_type, meta):
    """Convert metamodel value bytes to displayable string based on type flags."""
    if not value_bytes or len(value_bytes) != 4:
        return ""

    if value_type & 0x1:
        return "true" if value_bytes[0] == 1 else "false"
    if value_type & 0x2:
        return f"0x{int.from_bytes(value_bytes, 'big'):08X}"
    if value_type & 0x4:
        return f"{BinaryReader(value_bytes).read_f32():.6f}"
    if value_type & 0x8:
        ptr = int.from_bytes(value_bytes, "big", signed=False)
        return read_null_terminated_at(meta["reader"], ptr)
    if value_type & 0x10:
        ptr = int.from_bytes(value_bytes, "big", signed=False)
        asset = meta["asset_by_addr"].get(ptr)
        return asset.get("name", f"0x{ptr:08X}") if asset else f"0x{ptr:08X}"
    if value_type & 0x20:
        ptr = int.from_bytes(value_bytes, "big", signed=False)
        return f"Matrix@0x{ptr:08X}"

    return f"0x{int.from_bytes(value_bytes, 'big'):08X}"


def read_ascii_string(data, offset, max_len=64, min_len=4):
    """Extract ASCII string from data at given offset.
    
    Skips leading null bytes and padding to find the actual string start.
    Returns string if valid ASCII sequence of min_len or longer is found,
    otherwise returns None.
    """
    if offset < 0 or offset >= len(data):
        return None
    
    allowed = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.")
    end = min(len(data), offset + max_len)
    
    # Skip leading null bytes and non-ASCII characters (up to 8 bytes of padding)
    start = offset
    max_skip = min(8, end - offset)
    for skip in range(max_skip):
        if start + skip >= end:
            break
        if data[start + skip] in allowed:
            start = start + skip
            break
    else:
        # No valid ASCII character found in search window
        return None
    
    # Now collect the string starting from the first valid character
    result = bytearray()
    for i in range(start, end):
        byte = data[i]
        if byte in allowed:
            result.append(byte)
        else:
            # Stop at first non-allowed character AFTER starting collection
            break
    
    if len(result) >= min_len:
        try:
            return result.decode('ascii')
        except Exception:
            return None
    
    return None


def scan_all_texture_strings(data):
    """Scan entire file for potential texture name strings.
    
    Looks for common texture patterns like names ending in common suffixes,
    or names that match typical texture naming conventions.
    """
    import re
    
    # Find all ASCII strings in the file (at least 4 chars, only valid characters)
    texture_candidates = set()
    allowed_pattern = re.compile(rb'[a-zA-Z0-9_.-]{4,64}')
    
    for match in allowed_pattern.finditer(data):
        candidate = match.group(0)
        try:
            text = candidate.decode('ascii')
            # Filter for likely texture names
            text_lower = text.lower()
            # Common texture patterns: contains underscore, has caps, ends with number, contains 'tex', 'diffuse', etc.
            if ('_' in text or  # Has underscore (common in texture names)
                any(c.isupper() for c in text) or  # Has uppercase (common convention)
                text_lower.endswith(('cm', 'lo', 'hi', 'lod', 'diffuse', 'normal', 'spec')) or  # Common suffixes
                'tex' in text_lower or
                'mat' in text_lower or
                len(text) > 8):  # Longer names are more likely real assets
                texture_candidates.add(text)
        except Exception:
            continue
    
    return texture_candidates


def find_all_occurrences(data, pattern):
    """Find all occurrences of a byte pattern in data."""
    offsets = []
    start = 0
    while True:
        pos = data.find(pattern, start)
        if pos == -1:
            break
        offsets.append(pos)
        start = pos + 1
    return offsets


def format_pad_pattern(pattern):
    """Format a controller pad pattern for display."""
    return (
        "sticks {minx},{miny}-{maxx},{maxy} dur {min_dur}-{max_dur}ms "
        "req 0x{req:04X} disc 0x{disc:04X}"
    ).format(
        minx=pattern["sticks_min"][0],
        miny=pattern["sticks_min"][1],
        maxx=pattern["sticks_max"][0],
        maxy=pattern["sticks_max"][1],
        min_dur=pattern["min_duration"],
        max_dur=pattern["max_duration"],
        req=pattern["buttons_required"],
        disc=pattern["buttons_discarded"],
    )

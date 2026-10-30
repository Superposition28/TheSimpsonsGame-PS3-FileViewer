"""ACS record reader from docs/tools/inspect_acs_collision.py (2026-10-22)."""
from __future__ import annotations
import math
import struct

def parse_acs(data: bytes) -> dict:
    """Walk the observed version-1 layout, retaining uninterpreted identifiers."""
    if len(data) < 4 or data[0] != 1 or data[2:4] != b'\0\0':
        raise ValueError('not the observed ACS header: 01 count 00 00')
    offset = 4
    records = []
    for index in range(data[1]):
        if offset + 76 > len(data):
            raise ValueError(f'record {index}: truncated common header')
        size = struct.unpack_from('>I', data, offset)[0]
        if size < 76 or size % 4 or offset + size > len(data):
            raise ValueError(f'record {index}: invalid size {size}')
        raw = data[offset:offset + size]
        transform = list(struct.unpack_from('>12f', raw, 24))
        parameters = list(struct.unpack_from(f'>{(size - 76) // 4}f', raw, 76))
        if not all(math.isfinite(value) for value in transform + parameters):
            raise ValueError(f'record {index}: non-finite float candidate')
        records.append({
            'offset': offset,
            'size': size,
            'identifier_04': raw[4:8].hex(),
            'binding_identifier_08': raw[8:12].hex(),
            'flags_0c_hex': raw[12:16].hex(),
            'word_10_hex': raw[16:20].hex(),
            'identifier_14': raw[20:24].hex(),
            'transform_18_f32be': transform,
            'kind_48': raw[72],
            'kind_padding_49_hex': raw[73:76].hex(),
            'parameters_4c_f32be': parameters,
            'observed_kind_size_pair': (raw[72], size) in ((1, 80), (2, 84), (3, 84)),
        })
        offset += size
    if offset != len(data):
        raise ValueError(f'{len(data) - offset} trailing bytes after declared count')
    return {'header_hex': data[:4].hex(), 'count': data[1], 'records': records}


"""Parser for LightTOC (Light Table of Contents) resources."""
from ..binary_reader import BinaryReader
from .common import read_guid128, read_matrix


def parse_lighttoc(data):
    """Parse LightTOC resource.
    
    Args:
        data: Raw bytes of LightTOC resource
        
    Returns:
        Dict with table structure including headers, rows, and summary
    """
    reader = BinaryReader(data)

    magic = reader.read_u16_le()
    version = reader.read_u16_le()
    p_light_arr = reader.read_u32()
    p_box_arr = reader.read_u32()
    n_lights = reader.read_u16()
    n_box = reader.read_u16()

    rows = []
    if n_lights > 0 and p_light_arr < len(data):
        reader.seek(p_light_arr)
        for i in range(n_lights):
            guid = read_guid128(reader)
            matrix = read_matrix(reader)
            rw_light_type = reader.read_u8()
            rw_light_flags = reader.read_u8()
            inside_outside = reader.read_u8()
            reader.read_u8()
            diffuse_ambient = reader.read_f32()
            r = reader.read_u8()
            g = reader.read_u8()
            b = reader.read_u8()
            a = reader.read_u8()
            intensity = reader.read_f32()
            radius = reader.read_f32()
            full_bright_radius = reader.read_f32()
            cone_angle = reader.read_f32()
            full_bright_angle = reader.read_f32()

            pos_x = matrix[12]
            pos_y = matrix[13]
            pos_z = matrix[14]
            color = f"{r},{g},{b},{a}"

            rows.append(
                [
                    i,
                    guid,
                    rw_light_type,
                    rw_light_flags,
                    inside_outside,
                    f"{pos_x:.3f}",
                    f"{pos_y:.3f}",
                    f"{pos_z:.3f}",
                    color,
                    f"{diffuse_ambient:.3f}",
                    f"{intensity:.3f}",
                    f"{radius:.3f}",
                    f"{full_bright_radius:.3f}",
                    f"{cone_angle:.3f}",
                    f"{full_bright_angle:.3f}",
                ]
            )

    summary = f"LightTOC magic 0x{magic:04X} v{version} lights {len(rows)} boxLights {n_box}"
    if n_box > 0:
        summary += f" (box lights at 0x{p_box_arr:08X} not parsed)"

    return {
        "headers": [
            "Index",
            "Guid",
            "Type",
            "Flags",
            "InsideOut",
            "PosX",
            "PosY",
            "PosZ",
            "Color",
            "DiffuseAmb",
            "Intensity",
            "Radius",
            "FullBrightR",
            "ConeAngle",
            "FullBrightA",
        ],
        "rows": rows,
        "summary": summary,
    }

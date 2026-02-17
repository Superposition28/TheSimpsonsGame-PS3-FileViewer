"""Parser for MetaModel resources."""
from ..binary_reader import BinaryReader
from .common import read_guid128, read_nt_string_ptr, mm_value_to_display


def parse_metamodel(data):
    """Parse MetaModel resource with its complex hierarchical structure.
    
    Args:
        data: Raw bytes of MetaModel resource
        
    Returns:
        Dict with tree structure and metadata
    """
    reader = BinaryReader(data)
    meta = {"reader": reader}

    magic = reader.read_u32()
    version = reader.read_u32()
    size = reader.read_u32()
    flags = reader.read_u32()
    guid = read_guid128(reader)
    u_name = reader.read_u32()
    u_path = reader.read_u32()
    u_source = reader.read_u32()

    asset_offset = reader.read_i32()
    state_offset = reader.read_i32()
    variable_offset = reader.read_i32()
    attribute_offset = reader.read_i32()
    predicate_offset = reader.read_i32()
    part_offset = reader.read_i32()

    attr_data = reader.read_i32()
    user_data = reader.read_i32()

    n_assets = reader.read_u16()
    n_states = reader.read_u16()
    n_variables = reader.read_u16()
    n_attributes = reader.read_u16()
    n_predicates = reader.read_u16()
    n_parts = reader.read_u16()

    assets = []
    asset_by_addr = {}
    if n_assets > 0 and asset_offset < len(data):
        reader.seek(asset_offset)
        for _ in range(n_assets):
            address = reader.pos()
            name = reader.read_u32()
            path = reader.read_u32()
            type_id = reader.read_u32()
            guid_asset = read_guid128(reader)
            user_ptr = reader.read_i32()
            asset = {
                "address": address,
                "name": f"0x{name:08X}",
                "path": f"0x{path:08X}",
                "type_id": type_id,
                "guid": guid_asset,
                "user_ptr": user_ptr,
            }
            assets.append(asset)
            asset_by_addr[address] = asset

    meta["asset_by_addr"] = asset_by_addr

    states = []
    if n_states > 0 and state_offset < len(data):
        reader.seek(state_offset)
        for _ in range(n_states):
            address = reader.pos()
            class_id = reader.read_u32()
            class_name = read_nt_string_ptr(reader)
            name = read_nt_string_ptr(reader)
            attr_arr_offset = reader.read_i32()
            n_attrs = reader.read_u16()
            obj_type = reader.read_u16()
            part_arr_offset = reader.read_i32()
            predicate_arr_offset = reader.read_i32()
            n_parts_state = reader.read_u16()
            n_pred_state = reader.read_u16()
            states.append(
                {
                    "address": address,
                    "class_id": class_id,
                    "class_name": class_name,
                    "name": name,
                    "attr_arr_offset": attr_arr_offset,
                    "n_attrs": n_attrs,
                    "obj_type": obj_type,
                    "part_arr_offset": part_arr_offset,
                    "predicate_arr_offset": predicate_arr_offset,
                    "n_parts": n_parts_state,
                    "n_predicates": n_pred_state,
                }
            )

    variables = []
    variable_by_addr = {}
    if n_variables > 0 and variable_offset < len(data):
        reader.seek(variable_offset)
        for _ in range(n_variables):
            address = reader.pos()
            name = read_nt_string_ptr(reader)
            var_id = reader.read_u32()
            value_type = reader.read_u16()
            reader.read_u16()
            var = {"address": address, "name": name, "id": var_id, "value_type": value_type}
            variables.append(var)
            variable_by_addr[address] = var

    attributes = []
    attribute_by_addr = {}
    if n_attributes > 0 and attribute_offset < len(data):
        reader.seek(attribute_offset)
        for _ in range(n_attributes):
            address = reader.pos()
            value_bytes = reader.read_bytes(4)
            name = read_nt_string_ptr(reader)
            scope = read_nt_string_ptr(reader)
            u_index = reader.read_u32()
            attr_id = reader.read_u32()
            value_type = reader.read_i32()
            attr = {
                "address": address,
                "value_bytes": value_bytes,
                "name": name,
                "scope": scope,
                "u_index": u_index,
                "id": attr_id,
                "value_type": value_type,
            }
            attributes.append(attr)
            attribute_by_addr[address] = attr

    predicates = []
    if n_predicates > 0 and predicate_offset < len(data):
        reader.seek(predicate_offset)
        for _ in range(n_predicates):
            address = reader.pos()
            value_bytes = reader.read_bytes(4)
            variable_address = reader.read_i32()
            compare_op = reader.read_u16()
            reader.read_u16()
            pred = {
                "address": address,
                "value_bytes": value_bytes,
                "variable_address": variable_address,
                "compare_op": compare_op,
            }
            predicates.append(pred)

    parts = []
    if n_parts > 0 and part_offset < len(data):
        reader.seek(part_offset)
        for _ in range(n_parts):
            address = reader.pos()
            class_id = reader.read_u32()
            class_name = read_nt_string_ptr(reader)
            name = read_nt_string_ptr(reader)
            attr_arr_offset = reader.read_i32()
            n_attrs = reader.read_u16()
            obj_type = reader.read_u16()
            parts.append(
                {
                    "address": address,
                    "class_id": class_id,
                    "class_name": class_name,
                    "name": name,
                    "attr_arr_offset": attr_arr_offset,
                    "n_attrs": n_attrs,
                    "obj_type": obj_type,
                }
            )

    def read_attr_refs(offset, count):
        if offset <= 0 or offset >= len(data):
            return []
        reader.seek(offset)
        result = []
        for _ in range(count):
            addr = reader.read_i32()
            attr = attribute_by_addr.get(addr)
            if attr:
                result.append(attr)
        return result

    def read_part_refs(offset, count):
        if offset <= 0 or offset >= len(data):
            return []
        reader.seek(offset)
        result = []
        for _ in range(count):
            addr = reader.read_i32()
            for part in parts:
                if part["address"] == addr:
                    result.append(part)
                    break
        return result

    def read_pred_refs(offset, count):
        if offset <= 0 or offset >= len(data):
            return []
        reader.seek(offset)
        result = []
        for _ in range(count):
            addr = reader.read_i32()
            for pred in predicates:
                if pred["address"] == addr:
                    result.append(pred)
                    break
        return result

    tree_nodes = []

    asset_nodes = []
    for asset in assets:
        asset_nodes.append(
            {
                "label": f"Asset {asset['guid']} type 0x{asset['type_id']:08X}",
                "children": [
                    {"label": f"NameHash {asset['name']}", "children": []},
                    {"label": f"PathHash {asset['path']}", "children": []},
                ],
            }
        )
    tree_nodes.append({"label": f"Assets ({len(assets)})", "children": asset_nodes})

    var_nodes = []
    for var in variables:
        var_nodes.append(
            {
                "label": f"{var['name']} id 0x{var['id']:08X} type 0x{var['value_type']:04X}",
                "children": [],
            }
        )
    tree_nodes.append({"label": f"Variables ({len(variables)})", "children": var_nodes})

    attr_nodes = []
    for attr in attributes:
        val = mm_value_to_display(attr["value_bytes"], attr["value_type"], meta)
        attr_nodes.append(
            {
                "label": f"{attr['name']} scope {attr['scope']} id 0x{attr['id']:08X}",
                "children": [
                    {"label": f"Index {attr['u_index']}", "children": []},
                    {"label": f"Type 0x{attr['value_type']:08X}", "children": []},
                    {"label": f"Value {val}", "children": []},
                ],
            }
        )
    tree_nodes.append({"label": f"Attributes ({len(attributes)})", "children": attr_nodes})

    pred_nodes = []
    for pred in predicates:
        var = variable_by_addr.get(pred["variable_address"])
        var_name = var["name"] if var else f"0x{pred['variable_address']:08X}"
        val = mm_value_to_display(pred["value_bytes"], 0x7, meta)
        pred_nodes.append(
            {
                "label": f"Predicate var {var_name} op {pred['compare_op']}",
                "children": [{"label": f"Value {val}", "children": []}],
            }
        )
    tree_nodes.append({"label": f"Predicates ({len(predicates)})", "children": pred_nodes})

    part_nodes = []
    for part in parts:
        attrs = read_attr_refs(part["attr_arr_offset"], part["n_attrs"])
        attr_children = [
            {"label": f"{attr['name']} = {mm_value_to_display(attr['value_bytes'], attr['value_type'], meta)}", "children": []}
            for attr in attrs
        ]
        part_nodes.append(
            {
                "label": f"{part['name']} class {part['class_name']} type 0x{part['obj_type']:04X}",
                "children": attr_children,
            }
        )
    tree_nodes.append({"label": f"Parts ({len(parts)})", "children": part_nodes})

    state_nodes = []
    for state in states:
        attrs = read_attr_refs(state["attr_arr_offset"], state["n_attrs"])
        parts_ref = read_part_refs(state["part_arr_offset"], state["n_parts"])
        preds_ref = read_pred_refs(state["predicate_arr_offset"], state["n_predicates"])

        state_children = []
        if attrs:
            state_children.append(
                {
                    "label": f"Attributes ({len(attrs)})",
                    "children": [
                        {
                            "label": f"{attr['name']} = {mm_value_to_display(attr['value_bytes'], attr['value_type'], meta)}",
                            "children": [],
                        }
                        for attr in attrs
                    ],
                }
            )
        if parts_ref:
            state_children.append(
                {
                    "label": f"Parts ({len(parts_ref)})",
                    "children": [
                        {"label": f"{part['name']} class {part['class_name']}", "children": []}
                        for part in parts_ref
                    ],
                }
            )
        if preds_ref:
            state_children.append(
                {
                    "label": f"Predicates ({len(preds_ref)})",
                    "children": [
                        {"label": f"var 0x{pred['variable_address']:08X} op {pred['compare_op']}", "children": []}
                        for pred in preds_ref
                    ],
                }
            )

        state_nodes.append(
            {
                "label": f"State {state['name']} class {state['class_name']}",
                "children": state_children,
            }
        )
    tree_nodes.append({"label": f"States ({len(states)})", "children": state_nodes})

    summary = (
        f"MetaModel v{version} size {size} assets {n_assets} states {n_states} vars {n_variables} "
        f"attrs {n_attributes} preds {n_predicates} parts {n_parts}"
    )

    return {"tree": tree_nodes, "summary": summary, "meta": {"magic": magic, "flags": flags, "guid": guid}}

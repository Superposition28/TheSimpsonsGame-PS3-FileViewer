"""Parser for SimGroup resources."""
import struct
from ..binary_reader import BinaryReader
from .common import read_guid128

# 149 registered actor/entity classes extracted from EBOOT.elf (0x00054C2C..0x00055F60)
# and cross-verified against Xbox 360 default.xex (0x823C3A00).
KNOWN_BEHAVIOR_CLASSES = {
    0x00C255DD: "SimpleTeleport",
    0x00CB4767: "NPCLardLad",
    0x0462307C: "HoGCollectible",
    0x05919766: "Updraft",
    0x05923E4C: "LisaPlayer",
    0x07B471D0: "Turret",
    0x0B251A33: "TriggerBox",
    0x12785E05: "Timer",
    0x14B359CB: "HandOfGodChaseCameraInfo",
    0x16090182: "HandOfGodTrigger",
    0x16BFC575: "PassiveHeadTrackTarget",
    0x17B56F7A: "NPCMeleeRanged",
    0x18409298: "ItemPlantPoint",
    0x18D4BB30: "Maggie",
    0x198D805B: "TuningOverrideCollectible",
    0x1AF3C5F4: "MobItemRandomizer",
    0x1EB84ABF: "NPCMobileRangedFloater",
    0x1F7DB522: "PlayerTuningOverride",
    0x1FDA242A: "LerpCameraInfo",
    0x2414ADFA: "FuncConveyorBelt",
    0x263709DE: "MobInteractDestructible",
    0x2EE14270: "StreamInterior",
    0x31714328: "ScriptableProp",
    0x3243A9F0: "ShakeCameraModifierInfo",
    0x34109553: "CameraTrigger",
    0x35A6789D: "MargePlayer",
    0x35D6758C: "HandOfGodCursor",
    0x383225A1: "Player",
    0x3E438286: "EntityMeter",
    0x3EACFCDB: "EpisodeLauncher",
    0x41D92F27: "SimpleObjective",
    0x463FD53C: "SlidingDoor",
    0x470093E9: "Projectile",
    0x4B590617: "FuncSpawn",
    0x4BF5E8DE: "GrappleSurface",
    0x4C16F745: "ThoughtBubble",
    0x4D83DB06: "NPCBerserker",
    0x52ACCC3D: "Trampoline",
    0x52AD8052: "LedgeHangSurface",
    0x54B9F9D8: "RPGSpecialAttack",
    0x54F4E44C: "PushPopCameraPostBlendModifier",
    0x55D64C24: "Fulcrum",
    0x5674FF63: "PathfinderMusicControl",
    0x584DAF7B: "NPCSelmattyShire",
    0x589CBC0F: "ObjectDropRandomizer",
    0x5B264B93: "NPCDash",
    0x5B9528A8: "EntityDensityManager",
    0x5FEF7F11: "TestEntityExists",
    0x61F31794: "HomerPlayer",
    0x62953046: "SingleAxisConstraint",
    0x63C15F4E: "Door",
    0x63C72601: "EntityList",
    0x65F5D480: "ZipLine",
    0x6600EFC4: "DissolvePlatform",
    0x6629AE72: "PointCameraInfo",
    0x6A9A8C57: "SimpleMove",
    0x6D43B068: "Vehicle",
    0x6FD6B250: "NPCDashEatingContestant",
    0x70EA2398: "NPCMeleeRangedFollower",
    0x738CF41E: "NPCEatingContestant",
    0x7426A374: "ScreenFade",
    0x74A0766B: "TriggerBase",
    0x77E71790: "SimpleSplineFollower",
    0x794A757C: "SimpleSwitch",
    0x798AAF5A: "DynamicObjectTrigger",
    0x7BA9FD12: "CombatKnowledgeTuningRelay",
    0x7D3D229F: "SimplePickup",
    0x80356C4C: "TurretVehicle",
    0x82C7C770: "ScriptVariable",
    0x8479B489: "ScriptFunction",
    0x85CF8871: "NPCMeleeFollower",
    0x86AC090D: "TriggerVolume",
    0x87B7A547: "EventText",
    0x8A9EC733: "SimplePhysicsProp",
    0x8B37409C: "Collectible",
    0x8D8C7A00: "ScriptEntity",
    0x8E19B2B1: "TestTrigger",
    0x8E5E7DC9: "VehicleCameraInfo",
    0x8EF54728: "LadderSurface",
    0x9188448A: "PressurePlate",
    0x933AEF8E: "MobInteractNode",
    0x98FF51A5: "PushBlock",
    0x9C9A1744: "TestCounter",
    0x9E7092E4: "PushBlockSlot",
    0x9F414D02: "SimpleLight",
    0xA0420792: "SimpleSound",
    0xA19E2B6D: "ScriptBranch",
    0xA2BF931D: "SimpleRotator",
    0xA3C339F0: "Rope",
    0xA4AE577C: "ScriptMessage",
    0xA4FBE21D: "SimpleEmitter",
    0xA8043690: "TriggerSphere",
    0xAA6E8DEB: "TriggerCylinder",
    0xAC77BB28: "TriggerCapsule",
    0xACC5F988: "NPCRanged",
    0xAFF2E3C9: "SpringPad",
    0xB12EA814: "EpisodeComplete",
    0xB1CF0B4B: "EntityDamageDealer",
    0xB251A37C: "Counter",
    0xB3CF3689: "CrowdAudio",
    0xB70C43C8: "BoundingVolumeCameraModifierInfo",
    0xB81224B8: "DynamicObjectAudio",
    0xB88A62D3: "FleeArea",
    0xBA989D42: "PlayerModeNotify",
    0xBBF49926: "PlayerMusicMessageHandler",
    0xBC17EB9A: "PlayerState",
    0xBEFEC971: "NPCShakespeare",
    0xC0519B92: "CollectObjectsTuningRelay",
    0xC0CF00BE: "Food",
    0xC17EB9A2: "BartPlayer",
    0xC20454A2: "BusStop",
    0xC3C509AA: "NPCSelmattyLair",
    0xC6BE7A71: "ExplodingItem",
    0xC7FB2A05: "SimpleBreakable",
    0xC8C5D222: "EnterExitTrigger",
    0xCB4B560F: "FollowTargetRelay",
    0xCF929B52: "Attacher",
    0xD07DE9D9: "SimpleSpawner",
    0xD1FFB86C: "DamageableProp",
    0xD2FD8889: "NPCNinja",
    0xD3F4C653: "NPCMelee",
    0xD4A0766B: "TriggerMulti",
    0xD62B75E6: "SimpleDoor",
    0xD761B1B4: "SimpleLever",
    0xD9BF931D: "SimpleOscillator",
    0xDC24DB08: "Checkpoint",
    0xDCBD521B: "EntityFilter",
    0xDD818E50: "SimpleElevator",
    0xDF251A33: "TriggerConvex",
    0xE149AE2F: "SimplePath",
    0xE3928D7D: "NPCRangedGuard",
    0xE479B489: "ScriptTimer",
    0xE6BE6056: "DestructibleDynamicObject",
    0xE73D229F: "SimplePickupSpawner",
    0xE893DE72: "NPCMeleeGuard",
    0xE98627B9: "NPCMobMember",
    0xEAC08401: "PlayerStart",
    0xEFB44A94: "TouchDetectorHurt",
    0xF26BB307: "TriggerHurt",
    0xF2BA83F8: "PopulationControlSpawner",
    0xF776AA00: "TestScore",
    0xF90ED1F9: "ChatterGlobalCullingDistance",
    0xF941297A: "FadeScreenFx",
    0xFB841467: "HoGDestructibleObject",
    0xFBA585D3: "TestVariableContainer",
    0xFE18AA12: "NPCBase",
}


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
        behavior_name = KNOWN_BEHAVIOR_CLASSES.get(behavior_id, None)

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

        behavior_desc = f"{behavior_name} (0x{behavior_id:08X})" if behavior_name else f"0x{behavior_id:08X}"
        entity_title = f"Entity {i} [{behavior_name}]: {ent_guid}" if behavior_name else f"Entity {i}: {ent_guid}"

        entities.append(
            {
                "label": entity_title,
                "children": [
                    {"label": f"Behavior: {behavior_desc}"},
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

    resolved_count = sum(1 for e in entities if "[" in e["label"])
    summary = f"SimGroup v{version} Entities: {len(entities)} (Resolved: {resolved_count}/{len(entities)}) GUID: 0x{guid_hash:08X}"
    return {"tree": entities, "summary": summary}

"""Human-readable descriptions; AudioMap V2 is consulted without modifying it."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from connection_explorer.index import MODULE
from .media import AUDIO, VIDEO, IMAGES, MediaRequest

REGISTRY = MODULE / "reversing/docs/PS3_GAME/USRDIR/A1_Audio/AudioMap.yaml"


@lru_cache(maxsize=2)
def load_audio_map(path: str, modified: int) -> tuple[dict, list[tuple[re.Pattern, dict]]]:
    import yaml
    with Path(path).open(encoding="utf-8") as handle:
        registry = yaml.load(handle, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    if registry.get("schema_version") != 2:
        raise ValueError("AudioMap V2 required")
    patterns = []
    for asset in registry["assets"]:
        for pattern in asset["source"]["file_patterns"]:
            expression = re.escape(pattern.lower()).replace(r"\#\#\#\#\#\#\#", "[0-9a-f]{7}")
            patterns.append((re.compile(expression), asset))
    return registry, patterns


def audio_metadata(path: str, registry_path: Path = REGISTRY) -> dict:
    registry, patterns = load_audio_map(str(registry_path), registry_path.stat().st_mtime_ns)
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    filename = parts[-1]
    scope = "global" if "global" in parts else None
    language = next((part.upper() for part in parts if part in {"en", "fr", "it", "es"}), "EN")
    if scope is None and any(part in {"en", "fr", "it", "es"} for part in parts):
        scope = "localized"
    if scope is None:
        bank_scopes = {asset["source"]["scope"] for _, asset in patterns
                       if asset["source"]["original_directory"].lower() in parts}
        if len(bank_scopes) == 1:
            scope = bank_scopes.pop()
    candidates = []
    for pattern, asset in patterns:
        source = asset["source"]
        if pattern.fullmatch(filename) and (scope is None or source["scope"] == scope):
            banks = [source["original_directory"], *(source.get("legacy_directories") or [])]
            score = max((2 if ("/" + bank.replace("\\", "/").lower().strip("/") + "/") in ("/" + normalized) else 0 for bank in banks), default=0)
            candidates.append((score, asset))
    if not candidates:
        return {"status": "No AudioMap association recorded for this filename", "language": language}
    best = max(score for score, _ in candidates)
    assets = {asset["id"]: asset for score, asset in candidates if score == best}
    if len(assets) != 1:
        return {"status": "Ambiguous AudioMap association", "candidates": sorted(assets), "language": language}
    asset = next(iter(assets.values()))
    speaker = registry["speakers"].get(asset.get("speaker_id"), {})
    usage = asset["usage"]
    locations = [registry["locations"][kind][key]["display_name"] for kind in ("hubs", "levels") for key in usage.get(kind) or []]
    if usage.get("world_hub") and not usage.get("hubs"):
        locations.append("World hub (specific hub unresolved)")
    return dict(status="AudioMap V2 association", asset=asset["id"], type=asset["audio_type"],
                language=language if asset["source"]["scope"] == "localized" else "Global",
                speaker=speaker.get("display_name", ""), review_status=speaker.get("review_status", ""),
                locations=locations, unresolved=usage.get("unresolved") or [],
                notes=asset.get("notes", ""), category=asset.get("category", ""), area=asset.get("area", ""),
                nickname=asset.get("nickname", ""), source_bank=asset["source"]["original_directory"])


def describe_media(request: MediaRequest) -> str:
    suffix = Path(request.name).suffix.lower()
    size = Path(request.source).stat().st_size if request.source else len(request.data or b"")
    title = "Audio" if suffix in AUDIO else "Video" if suffix in VIDEO else "Image"
    lines = [f"{title}: {Path(request.name.replace(chr(92), '/')).name}", f"Size: {size:,} bytes", ""]
    if suffix == ".snu":
        lines += ["EA streamed audio (.exa.snu / SNU wrapper).", "Play decodes this stream to a temporary PCM WAV and opens it in the Windows default player.",
                  "Four-channel streams produce separate front and rear stereo WAVs, as in operation 12.", ""]
        try:
            metadata = audio_metadata(request.source or request.name)
            for key, value in metadata.items():
                if value:
                    lines.append(f"{key.replace('_', ' ').title()}: {', '.join(map(str, value)) if isinstance(value, list) else value}")
            lines += ["", "Association source: reversing/docs/PS3_GAME/USRDIR/A1_Audio/AudioMap.yaml",
                      "Registry associations do not establish original event timing or playback conditions."]
        except (ImportError, OSError, ValueError, KeyError) as exc:
            lines.append(f"AudioMap metadata unavailable: {exc}. PyYAML is required to read the registry.")
    elif suffix == ".sbk":
        lines += ["EA sound bank containing one or more subsongs.", "Play decodes its tracks to temporary WAV files (operation 11). Select a decoded track to hear it."]
    elif suffix == ".mus":
        lines += ["Interactive music archive containing SNR/SNS segment pairs.", "Play extracts the descriptor-selected segments and decodes them to temporary WAV files (operation 13).",
                  "Segment numbers are retained; original adaptive sequencing is not reconstructed."]
    elif suffix == ".vp6":
        lines += ["EA movie container carrying VP6 video and associated audio.", "Watch converts this movie to temporary OGV (Theora/Vorbis), matching operation 14, then opens the default player."]
    elif suffix in IMAGES:
        lines.append("Image preview. Open image uses the Windows default image viewer.")
    else:
        lines.append(f"Playable {title.lower()} file. Open it with the Windows default player.")
    return "\n".join(lines)

# The Simpsons Game file viewer

Run from the game module:

```powershell
python -B reversing/fileviewer/str_reader.py
```

Python 3.11+ with Tkinter is required. Optional dependencies are listed in
`requirements.txt`: Pillow supplies texture previews and PyYAML reads AudioMap.

Opening a folder recursively lists paths without reading payloads. Folders named
`audiostreams` or `A1_Audio` appear immediately but are not scanned until selected
or expanded. There is no file-count limit; listing updates the tree incrementally
so a large audio tree does not block discovery of level archives. The status line
shows file and STR counts. `.history` and `.backup` folders are excluded.

Selecting a STR shows its description; **expanding the archive** reads and parses
it in a background worker. Selecting an embedded or standalone resource shows its
interpretation first: source text, translation table, structured fields, texture
preview, or a media description. **View raw HEX / View interpretation** switches
between those views. Standalone media HEX is paged from disk without loading the
whole stream or movie into memory. Extract Payload saves the exact resource bytes.
Searching only filters listed paths and loaded members. Clear List cancels pending
scans and discards loaded entries.

## Media playback

SNU descriptions include AudioMap V2 associations (speaker, audio type, language,
locations, notes and unresolved associations). Filename patterns use exactly seven
hexadecimal characters for `#######`; bank matches take precedence and ambiguous
associations remain explicit. The registry is read directly and is never modified.

**Play**, **Watch**, or **Open image** prepares the selected resource and opens the
Windows default application. Conversions run in a worker and are cached beneath
`%TEMP%/TheSimpsonsGame-FileViewer/`; source and extracted input files are unchanged.
These previews use installed tools and versions from the module's `Tools.toml`:

- SNU and SBK → PCM16 WAV through vgmstream and FFmpeg, matching operations 11/12.
  Quad audio is split into front/rear stereo WAVs. SBK subsongs have a track selector.
- MUS → SNR/SNS segment pairs → WAV, following `mus.bms` and `SetupMusicFiles.lua`
  (operation 13). Select a segment to hear it; adaptive sequencing is not inferred.
- VP6 → OGV with Theora/Vorbis quality 10, matching operation 14 and `AvTools.cs`.
- Existing WAV/OGG/MP3/FLAC, OGV/MP4/AVI/WebM and image files open directly.

For multi-track previews, the selector beside Play chooses the decoded track,
segment, or front/rear pair. Tools are resolved from `EngineApps/Tools` using the
configured versions; a missing tool produces an actionable error. Closing the
viewer stops an active conversion. Temporary previews remain available to the
external player and can be removed from the named temporary folder later.

## Connections

The entire connections project now lives here: `file_connections.py`,
`connection_explorer/` (including its web assets), and shared `game_formats/`
readers. The desktop toolbar provides **Start connections server**, **Stop
connections server**, **Open connections**, and **Connections settings**. Closing
the viewer stops its own server process. Settings configure the original source,
extracted roots, database, loopback port, and rebuilding. Port `0` picks a free port.
Server output and startup errors appear in the settings log.

The HTTP server binds only to `127.0.0.1`. It reuses an existing index unless a
rebuild is requested. Building an index deliberately reads the selected input
datasets; opening a folder in the desktop viewer does not build an index or start
the server. In the browser, **Documented structure → Read documented structure**
uses the same resource dispatcher as the desktop viewer. This optional view has
a 32 MiB payload limit; larger resources retain the paged raw-word inspector.

```powershell
python -B reversing/fileviewer/file_connections.py --open
python -B reversing/fileviewer/file_connections.py --build-only --no-extracted
```

`python -B reversing/file_connections.py` remains compatible. Generated databases
remain under the parent module's `GameFiles/`, outside all input trees. Default
source/extracted roots and the naming registry use the parent module checkout;
connections indexing requires its documentation submodule.

## Format coverage

Readers follow [the format references](../docs/PS3_GAME/FormatAnalysis/index.html).
Green entries have structured readers; amber entries expose partial documented
observations. Unknown layouts remain available in HEX. Support describes stored
fields, not recovered game runtime behavior.

| Family | Viewer support |
| --- | --- |
| STR / RefPack | Bounded mixed-endian records, exact asset headers/GUIDs/payloads, sequential sections, validated `10 FB` RefPack streams; full SimGroup bodies are preserved. |
| LH2 and EN/FR/IT/ES/SS variants | Validated matrix/pointers, Windows-1252 text, all columns, StringIDs, translation table. |
| ALB / SMB / TOX | 24-byte ALB records, bank/stream IDs, SMB filenames, subtitle StringIDs and cue times; shared with the connections graph. |
| SimGroup / UIE | Entities, attached resource GUIDs, attributes and UIE little-endian GUID words. Legacy shifted SimGroup dumps are labeled and their body base restored. |
| MetaModel / graph / CEC / SHK | Existing detailed readers with current payload framing and bounds checks; controller events and haptic commands. |
| INF | Glyph metrics, signed bearings, 12.4 atlas coordinates, surviving complete kerning records and truncated-tail reporting. |
| BBN / ACS | Rig/alias tables and bindings; primitive IDs, raw transforms, kinds and scalar parameters. |
| HKT / HKO | Reused documented Havok inspector: sections, fixups, instantiated classes, all mesh validation totals, bounded body/mesh/primitive examples. No physics simulation or pose reconstruction. |
| IMB / VFB / BSP | Impact blocks, effect table/tag observations, bounded BSP node arrays; unresolved semantics retain candidate labels. |
| TXD / preinstanced / RWS / DFF | Existing texture preview/DDS conversion and unified mesh/RenderWare structure readers; shared identifier adapters expose texture and HAnim links. |
| MUS | Descriptor table, scaled SNR/SNS offsets, sizes, IDs and segment numbers; temporary WAV segment playback. |
| TXT / Lua / suffixless resources | Text without execution; observed LightTOC floats and StreamSetConfig entries/string pool. |
| AMB / MIB / MSB / UIX / compiled XML / SBK | Known headers, standard 44-byte MIB candidate records, markers and literal strings where documented; event logic, APT execution and codecs remain unresolved. |
| AUB / BNK / CTB / RCB / RCM_B / TOC / generic PS3 | Inventory/header/string observations and raw bytes; references do not yet establish complete parsers. |
| SNU / VP6 / EBOOT.BIN | SNU AudioMap descriptions and WAV playback; VP6 OGV playback; executable wrapper/header observations only. |
| Xbox ITXD | Documented texture metadata, plugin GUID, dimensions, mip/pixel ranges and Xenos descriptor; pixel untile/conversion remains separate from PS3 TXD. |

Two byte-checked EU variants differ from tentative reference tables: VFB samples
use a count byte at `+0x1c` when the listed BE u16 count exceeds the payload; BSP
node arrays can use `+0x28/+0x2c` start/end boundaries instead of the listed
`+0x30` offset/length. Parsed output records the interpretation used. Unknown
variants are rejected rather than read beyond their bounds.

Resource parsing runs on demand; interpretations are the default view. Structured tree display is bounded for large
resources; **Export JSON** retains the complete parsed structure and identifiers.
Havok examples are intentionally bounded by the reference inspector itself.

## Validation

```powershell
python -B -m unittest discover -s reversing/fileviewer/tests -v
python -B reversing/fileviewer/str_reader.py --stats "path/to/file.str"
```

Tests use synthetic archives/resources and a temporary connections database. They
cover raw/compressed framing, exact payloads, unnamed UIE, malformed data, fonts,
localization, recursive/deferred discovery beyond 20,000 entries, expansion-only STR parsing, interpreted defaults, media playback and conversion commands, and HTTP start/stop/restart. Tk tests skip
when the local Tcl/Tk runtime is unavailable. `--stats` intentionally reads every
requested archive; it is separate from GUI lazy loading.

## Project links

- [Main project](https://github.com/Superposition28/TheSimpsonsGame-PS3)
- [File viewer](https://github.com/Superposition28/TheSimpsonsGame-PS3-FileViewer)
- [Documentation repository](https://github.com/Superposition28/TheSimpsonsGame-PS3-Docs)

## License

This tool is intended for educational and reverse engineering purposes only.

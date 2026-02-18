# The Simpsons Game (PS3) - STR File Viewer

A specialized tool for exploring and analyzing `.STR` archives and embedded assets from *The Simpsons Game* (2007) for the PlayStation 3.

## Links
- **Main Project:** [TheSimpsonsGame-PS3](https://github.com/Superposition28/TheSimpsonsGame-PS3)
- **Source Code:** [TheSimpsonsGame-PS3-FileViewer](https://github.com/Superposition28/TheSimpsonsGame-PS3-FileViewer)
- **Documentation Repo:** [TheSimpsonsGame-PS3-Docs](https://github.com/Superposition28/TheSimpsonsGame-PS3-Docs)
- **Hosted Docs:** [Online Documentation](https://superposition28.github.io/TheSimpsonsGame-PS3-Docs/)

## Features

- **Archive Exploration:** Browse the contents of `.STR` (EA Stream) files, including sections and embedded asset chunks.
- **Decompression:** Integrated support for **Refpack** decompression used by the RenderWare engine.
- **Embedded Asset Parsing:**
    - **Textures (.txd):** Preview textures and export to DDS (supports Morton unswizzling and DXT compression).
    - **Localization (.LH2):** View string tables and language columns in a structured table or CSV format.
    - **Navigation Graphs (.graph):** Visualize node structures, positions, and connections.
    - **Metadata & Config:** Support for `.cec.ps3`, `.tob`, `.shk`, `.lighttoc`, `.meta.xml`, and `.simgroup.dat`.
    - **Preinstanced Meshes:** Basic identification and analysis of `.dff` and `.rws` mesh chunks.
- **Advanced Views:**
    - **Tree View:** Hierarchical exploration of file structures.
    - **Hex Viewer:** Integrated hex view for low-level data inspection.
    - **Image Preview:** Real-time rendering of extracted textures (requires Pillow).

## Installation

### Prerequisites
- **Python 3.14+**
- **Tkinter**
- **Pillow** (for texture preview support)

```bash
pip install Pillow
```

## Usage

### GUI Mode
Simply run the main script to open the viewer:
```bash
python str_reader.py
```
Use **File > Open .STR File** or **File > Open Directory** to begin exploring assets.

### CLI Mode (Stats)
You can scan a file or a directory for a summary of embedded assets:
```bash
python str_reader.py --stats "path/to/files"
```

## Contributing

This tool is part of the Remake Engine project effort to preserve and re-implement *The Simpsons Game*. Contributions to parsers and UI features are welcome. Refer to the main repository for contribution guidelines.

## License

This tool is intended for educational and reverse engineering purposes only.

import argparse
import os
import tkinter as tk

from str_reader import STRFile, STRViewerApp


def _print_str_stats(file_path):
    try:
        str_file = STRFile(file_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {file_path}: {exc}")
        return

    print(f"File: {file_path}")
    for idx, section in enumerate(str_file.sections):
        asset_count = sum(1 for chunk in section.chunks if chunk.get("Type") == "Embedded Asset")
        print(f"  Section {idx}: EmbeddedAssets={asset_count}")

        for chunk in section.chunks:
            if chunk.get("Type") != "Embedded Asset":
                continue

            fname = chunk.get("FileName") or "<NoFileName>"
            rtype = chunk.get("ResourceType") or "<NoResourceType>"
            fpath = chunk.get("FullPath") or "<NoPath>"
            print(f"    File: {fname}")
            print(f"      Resource: {rtype}")
            print(f"      Path: {fpath}")


def _gather_str_files(path):
    if os.path.isfile(path) and path.lower().endswith(".str"):
        return [path]

    if os.path.isdir(path):
        found = []
        for root, directories, files in os.walk(path):
            directories[:] = [name for name in directories if name.lower() not in {".history", ".backup", ".git", "__pycache__"}]
            for name in files:
                if name.lower().endswith(".str"):
                    found.append(os.path.join(root, name))
        return found

    return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simpsons Game STR Viewer")
    parser.add_argument(
        "--stats",
        metavar="PATH",
        help="Print section and embedded asset stats for a .str file or directory",
    )
    parser.add_argument("path", nargs="?", help="Optional file or directory to open on startup")
    args = parser.parse_args()

    if args.stats:
        targets = _gather_str_files(args.stats)
        if not targets:
            print(f"No .str files found at: {args.stats}")
        else:
            for target in targets:
                _print_str_stats(target)
        raise SystemExit(0)

    root = tk.Tk()
    app = STRViewerApp(root)
    if args.path:
        if os.path.isdir(args.path):
            app.open_directory(args.path)
        elif os.path.isfile(args.path):
            app.load_single_file(args.path)
    else:
        fallback = app.server_source if os.path.isdir(app.server_source) else None
        app.restore_saved_session(fallback_path=fallback)
    root.mainloop()

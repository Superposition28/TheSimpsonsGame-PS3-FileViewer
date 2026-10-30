from .refpack import Refpack
from .binary_reader import BinaryReader
from .str_parser import STRFile, STRSection

__all__ = [
    "Refpack",
    "BinaryReader",
    "STRFile",
    "STRSection",
    "STRViewerApp",
]


def __getattr__(name: str):
    if name == "STRViewerApp":
        from .app import STRViewerApp
        return STRViewerApp
    raise AttributeError(name)

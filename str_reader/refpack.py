"""Compatibility facade for the shared strict RefPack decoder."""
from game_formats.refpack import refpack


class Refpack:
    @staticmethod
    def decompress(data_bytes: bytes) -> bytes:
        return refpack(data_bytes)[0]

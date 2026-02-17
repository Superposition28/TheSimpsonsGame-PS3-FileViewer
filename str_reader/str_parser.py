import struct

from .binary_reader import BinaryReader
from .refpack import Refpack


class STRSection:
    def __init__(self):
        self.chunks = []
        self.info = {}


class STRFile:
    def __init__(self, filepath):
        self.filepath = filepath
        self.header = {}
        self.stream_info = {}
        self.sections = []

        with open(filepath, "rb") as f:
            self.raw_data = f.read()

        self.reader = BinaryReader(self.raw_data)
        self.parse()

    def parse(self):
        r = self.reader

        r.seek(0)
        magic = r.read_bytes(4)
        if magic != b"SToc":
            raise ValueError("Invalid File Signature (Expected SToc)")

        self.header["Magic"] = magic.decode()
        self.header["Version"] = r.read_i32()
        self.header["nSections"] = r.read_u8()
        self.header["PlatformID"] = r.read_u8()
        r.read_bytes(2)
        self.header["pStreamFile"] = r.read_i32()
        self.header["pSectionArr"] = r.read_i32()

        if self.header["pStreamFile"] != 0:
            r.seek(self.header["pStreamFile"])
            self.stream_info["GUID"] = r.read_u32()

            name_offset = r.read_i32()
            fname_addr = self.header["pStreamFile"] + name_offset
            self.stream_info["FileName"] = r.read_string_at(0, fname_addr)

            self.stream_info["nParents"] = r.read_u8()
            self.stream_info["nForceLoad"] = r.read_u8()
            self.stream_info["nSections"] = r.read_u8()
            self.stream_info["Flags"] = r.read_u8()
            r.read_i32()
            self.stream_info["pRelatives"] = r.read_i32()
            self.stream_info["pSectionInfo"] = r.read_i32()

        section_defs = []
        if self.header["nSections"] > 0 and self.header["pSectionArr"] > 0:
            r.seek(self.header["pSectionArr"])
            for _ in range(self.header["nSections"]):
                s = {}
                s["MemPolicyID"] = r.read_u32()
                s["CompressorID"] = r.read_u32()
                s["DataSize"] = r.read_i32()
                s["AllocSize"] = r.read_i32()
                s["ReadSize"] = r.read_i32()
                s["ReadOffset"] = r.read_i32()
                section_defs.append(s)

        headers_end = self.header["pSectionArr"] + (self.header["nSections"] * 24)
        data_cursor = (headers_end + (0x800 - 1)) & -0x800

        r.seek(data_cursor)

        for i, s_def in enumerate(section_defs):
            section_obj = STRSection()
            section_obj.info = s_def
            section_obj.info["ActualOffset"] = hex(r.pos())

            raw_section_data = r.read_bytes(s_def["ReadSize"])

            if s_def["CompressorID"] == 0xB9F0B9EC:
                try:
                    section_data = Refpack.decompress(raw_section_data)
                    section_obj.info["Compression"] = "Refpack"
                except Exception as e:
                    section_data = raw_section_data
                    section_obj.info["Compression"] = "Refpack (Failed)"
                    section_obj.info["Error"] = str(e)
            else:
                section_obj.info["Compression"] = "None"
                section_data = raw_section_data

            chunk_reader = BinaryReader(section_data)

            while chunk_reader.pos() < len(section_data):
                chunk_start = chunk_reader.pos()
                if len(section_data) - chunk_start < 4:
                    break

                chunk_id = chunk_reader.read_u16()
                if chunk_id == 0:
                    break

                chunk_info = {"ID": chunk_id, "Start": chunk_start, "Data": None, "Type": "Unknown"}

                try:
                    if chunk_id == 0x1607:
                        chunk_info["Type"] = "Embedded Asset"
                        chunk_reader.read_bytes(2)
                        file_size = struct.unpack("<i", chunk_reader.read_bytes(4))[0]
                        chunk_reader.read_bytes(4)

                        asset_start = chunk_reader.pos()
                        header_size = chunk_reader.read_i32()

                        payload_data = None

                        if header_size > 0:
                            chunk_info["FileName"] = chunk_reader.read_rw_string()
                            chunk_reader.read_bytes(16)
                            chunk_info["ResourceType"] = chunk_reader.read_rw_string()
                            chunk_info["FullPath"] = chunk_reader.read_rw_string()

                            header_end = chunk_reader.pos()
                            chunk_reader.read_bytes(12)
                            payload_size = chunk_reader.read_u32()
                            chunk_reader.align(16)
                            payload_start = chunk_reader.pos()
                            payload_end = payload_start + payload_size
                            chunk_end = asset_start + file_size

                            if payload_end <= chunk_end:
                                payload_data = section_data[payload_start:payload_end]
                            else:
                                chunk_reader.seek(header_end)

                        chunk_reader.seek(asset_start)
                        chunk_info["Data"] = chunk_reader.read_bytes(file_size)

                        if payload_data:
                            chunk_info["PayloadData"] = payload_data

                        chunk_reader.seek(asset_start + file_size)

                    elif chunk_id == 0x2207:
                        chunk_info["Type"] = "SimGroup"
                        chunk_reader.read_bytes(2)
                        file_size = struct.unpack("<i", chunk_reader.read_bytes(4))[0]
                        chunk_reader.read_bytes(4)
                        chunk_info["Data"] = chunk_reader.read_bytes(file_size)

                    elif chunk_id == 0x10FB:
                        chunk_info["Type"] = "Refpack Block"
                        chunk_info["Data"] = section_data[chunk_start:]
                        chunk_reader.seek(len(section_data))

                    else:
                        chunk_info["Type"] = f"Unknown (0x{chunk_id:X})"
                        chunk_reader.seek(len(section_data))

                except Exception as e:
                    chunk_info["Type"] += " (Parse Error)"
                    chunk_info["Error"] = str(e)
                    chunk_reader.seek(len(section_data))

                section_obj.chunks.append(chunk_info)

            self.sections.append(section_obj)

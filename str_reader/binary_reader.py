import io
import struct


class BinaryReader:
    def __init__(self, data):
        self.stream = io.BytesIO(data)
        self.data = data

    def seek(self, offset):
        if not 0 <= offset <= len(self.data):
            raise ValueError(f"Seek outside payload: {offset:#x}")
        self.stream.seek(offset)

    def pos(self):
        return self.stream.tell()

    def read_bytes(self, n):
        if n < 0 or self.pos() + n > len(self.data):
            raise ValueError(f"Read outside payload: {self.pos():#x}, size {n}")
        return self.stream.read(n)

    def read_u8(self):
        b = self.read_bytes(1)
        return struct.unpack(">B", b)[0] if len(b) == 1 else 0

    def read_u16(self):
        b = self.read_bytes(2)
        return struct.unpack(">H", b)[0] if len(b) == 2 else 0

    def read_i16(self):
        b = self.read_bytes(2)
        return struct.unpack(">h", b)[0] if len(b) == 2 else 0

    def read_u16_le(self):
        b = self.read_bytes(2)
        return struct.unpack("<H", b)[0] if len(b) == 2 else 0

    def read_i32(self):
        b = self.read_bytes(4)
        return struct.unpack(">i", b)[0] if len(b) == 4 else 0

    def read_u32(self):
        b = self.read_bytes(4)
        return struct.unpack(">I", b)[0] if len(b) == 4 else 0

    def read_u32_le(self):
        b = self.read_bytes(4)
        return struct.unpack("<I", b)[0] if len(b) == 4 else 0

    def read_f32(self):
        b = self.read_bytes(4)
        return struct.unpack(">f", b)[0] if len(b) == 4 else 0.0

    def read_string_at(self, offset_base, relative_ptr):
        old_pos = self.stream.tell()
        target = offset_base + relative_ptr
        if target >= len(self.data) or target < 0:
            return "<Invalid Pointer>"
        self.stream.seek(target)
        chars = []
        while True:
            b = self.read_bytes(1)
            if not b or b == b"\x00":
                break
            chars.append(b.decode("latin-1"))
        self.stream.seek(old_pos)
        return "".join(chars)

    def read_rw_string(self):
        length = self.read_i32()
        if length < 0 or length > 5000:
            return "<ReadError>"

        s_bytes = self.stream.read(length)

        align_pad = (4 - (length % 4)) % 4
        self.stream.read(align_pad)

        try:
            actual_data = s_bytes.split(b"\x00")[0]
            return actual_data.decode("utf-8", errors="replace")
        except Exception:
            return s_bytes.decode("latin-1", errors="replace").split("\x00")[0]

    def align(self, alignment):
        pos = self.stream.tell()
        mod = pos % alignment
        if mod != 0:
            self.stream.read(alignment - mod)

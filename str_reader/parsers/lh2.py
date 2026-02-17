import io


class LH2Parser:
    @staticmethod
    def is_valid(data):
        return data.startswith(b"2HCL")

    @staticmethod
    def parse_to_csv(data):
        """Returns a list of rows (list of strings) representing the CSV data."""
        stream = io.BytesIO(data)

        def read_int():
            return int.from_bytes(stream.read(4), "big")

        def read_str():
            chars = []
            while True:
                b = stream.read(1)
                if b == b"\x00" or not b:
                    break
                chars.append(b)
            return b"".join(chars).decode("1252", errors="replace")

        if stream.read(4) != b"2HCL":
            raise ValueError("Not a valid LH2 file")

        stream.read(4)

        stream.seek(0x10)
        entries = read_int()
        tables = read_int()

        stream.seek(0x20)

        ids = [read_int() for _ in range(entries)]
        ptr = [[read_int() for _ in range(entries)] for _ in range(tables)]
        txt = [[] for _ in range(tables)]

        for i, lst in enumerate(ptr):
            for ofs in lst:
                stream.seek(ofs)
                txt[i].append(read_str())

        rows = []

        columns_count = tables - 1 if tables > 1 else tables
        header = ["String ID"]
        if tables > 1:
            header.append("Label")
        for x in range(columns_count):
            header.append(f"Language {x}")
        rows.append(header)

        for i, id_val in enumerate(ids):
            row = [f"{id_val:08X}"]
            if tables > 1:
                row.append(txt[-1][i])
            for x in range(columns_count):
                row.append(txt[x][i])
            rows.append(row)

        return rows

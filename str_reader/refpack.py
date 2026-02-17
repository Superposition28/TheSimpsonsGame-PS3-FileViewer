import io


class Refpack:
    @staticmethod
    def decompress(data_bytes):
        if not data_bytes:
            return b""

        stream = io.BytesIO(data_bytes)

        dummy = stream.read(2)
        if len(dummy) < 2:
            raise ValueError("Stream too short for Refpack header")

        header = (dummy[0] << 8) | dummy[1]

        if (header & 0x1FFF) != 0x10FB:
            raise ValueError(f"Invalid Refpack Signature: {hex(header)} (Expected 0x10FB)")

        is_long = (header & 0x8000) != 0
        is_doubled = (header & 0x0100) != 0

        if is_doubled:
            raise ValueError("Double compression (isDoubled) not supported.")

        if is_long:
            dummy = stream.read(4)
            if len(dummy) < 4:
                raise ValueError("EOF reading size (Long)")
            uncompressed_size = (dummy[0] << 24) | (dummy[1] << 16) | (dummy[2] << 8) | dummy[3]
        else:
            dummy = stream.read(3)
            if len(dummy) < 3:
                raise ValueError("EOF reading size (Short)")
            uncompressed_size = (dummy[0] << 16) | (dummy[1] << 8) | dummy[2]

        output = bytearray()

        while True:
            prefix_byte = stream.read(1)
            if not prefix_byte:
                break
            prefix = prefix_byte[0]

            plain_size = 0
            copy_size = 0
            copy_offset = 0
            stop = False

            if prefix < 0x80:
                dummy = stream.read(1)
                if len(dummy) < 1:
                    break
                d0 = dummy[0]

                plain_size = prefix & 0x03
                copy_size = ((prefix & 0x1C) >> 2) + 3
                copy_offset = ((prefix & 0x60) << 3) | d0
                copy_offset += 1

            elif prefix < 0xC0:
                dummy = stream.read(2)
                if len(dummy) < 2:
                    break
                d0, d1 = dummy[0], dummy[1]

                plain_size = (d0 >> 6) & 0x03
                copy_size = (prefix & 0x3F) + 4
                copy_offset = ((d0 & 0x3F) << 8) | d1
                copy_offset += 1

            elif prefix < 0xE0:
                dummy = stream.read(3)
                if len(dummy) < 3:
                    break
                d0, d1, d2 = dummy[0], dummy[1], dummy[2]

                plain_size = prefix & 0x03
                copy_size = ((prefix & 0x0C) << 6) | d2
                copy_size += 5
                copy_offset = (((prefix & 0x10) << 4) | d0) << 8 | d1
                copy_offset += 1

            elif prefix < 0xFC:
                plain_size = ((prefix & 0x1F) + 1) * 4

            else:
                plain_size = prefix & 0x03
                stop = True

            if plain_size > 0:
                data = stream.read(plain_size)
                output.extend(data)

            if copy_size > 0:
                current_len = len(output)
                start_index = current_len - copy_offset
                if start_index < 0:
                    start_index = 0

                for i in range(copy_size):
                    if start_index + i < len(output):
                        val = output[start_index + i]
                        output.append(val)
                    else:
                        output.append(0)

            if stop:
                break

        return bytes(output)

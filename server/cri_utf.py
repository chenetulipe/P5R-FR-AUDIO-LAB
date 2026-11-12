"""Lecteur des tables @UTF de CRI (utilisées dans les CPK et les ACB)."""
import struct


def _decrypt(data: bytes) -> bytes:
    m, out = 0x655F, bytearray(data)
    for i in range(len(out)):
        out[i] ^= m & 0xFF
        m = (m * 0x4115) & 0xFFFFFFFF
    return bytes(out)


def read_utf(data: bytes) -> list[dict]:
    """Renvoie les lignes de la table sous forme de dictionnaires."""
    if data[:4] != b"@UTF":
        dec = _decrypt(data[:4])
        if dec != b"@UTF":
            raise ValueError("Table @UTF introuvable")
        data = _decrypt(data)
    size = struct.unpack_from(">I", data, 4)[0]
    base = 8
    rows_off, strings_off, data_off = struct.unpack_from(">HII", data, base + 2)
    n_cols, row_width, n_rows = struct.unpack_from(">HHI", data, base + 16)
    rows_off += base
    strings_off += base
    data_off += base

    def string(off):
        start = strings_off + off
        return data[start:data.index(b"\0", start)].decode("utf-8", "replace")

    fmts = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 9: ">d"}

    def value(kind, pos):
        if kind in fmts:
            return struct.unpack_from(fmts[kind], data, pos)[0], struct.calcsize(fmts[kind])
        if kind == 0xA:
            return string(struct.unpack_from(">I", data, pos)[0]), 4
        if kind == 0xB:
            off, ln = struct.unpack_from(">II", data, pos)
            return data[data_off + off:data_off + off + ln], 8
        raise ValueError(f"Type de colonne inconnu {kind}")

    cols, pos = [], base + 24
    for _ in range(n_cols):
        flags = data[pos]
        name = string(struct.unpack_from(">I", data, pos + 1)[0])
        pos += 5
        storage, kind = flags & 0xF0, flags & 0x0F
        const = None
        if storage == 0x30:
            const, used = value(kind, pos)
            pos += used
        cols.append((name, storage, kind, const))

    rows = []
    for r in range(n_rows):
        p = rows_off + r * row_width
        row = {}
        for name, storage, kind, const in cols:
            if storage == 0x50:
                row[name], used = value(kind, p)
                p += used
            elif storage == 0x30:
                row[name] = const
            else:
                row[name] = None
        rows.append(row)
    return rows

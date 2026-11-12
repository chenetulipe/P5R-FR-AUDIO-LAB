"""Lecture / écriture des archives AWB (format CRI "AFS2")."""
import struct
from pathlib import Path


def _align(v: int, a: int) -> int:
    return v if a <= 1 else (v + a - 1) // a * a


def read_awb(path: Path) -> list[dict]:
    """Renvoie [{index, id, offset, size}] pour chaque clip de l'AWB."""
    data = path.read_bytes()
    if data[:4] != b"AFS2":
        raise ValueError(f"{path.name} n'est pas un AWB (en-tête AFS2 absent)")
    off_size, id_size = data[5], data[6]
    count = struct.unpack_from("<I", data, 8)[0]
    align = struct.unpack_from("<I", data, 12)[0] & 0xFFFF

    id_fmt = {2: "<H", 4: "<I"}[id_size]
    off_fmt = {2: "<H", 4: "<I", 8: "<Q"}[off_size]
    pos = 16
    ids = [struct.unpack_from(id_fmt, data, pos + i * id_size)[0] for i in range(count)]
    pos += count * id_size
    offs = [struct.unpack_from(off_fmt, data, pos + i * off_size)[0] for i in range(count + 1)]

    out = []
    for i in range(count):
        start = _align(offs[i], align)
        out.append({"index": i, "id": ids[i], "offset": start, "size": offs[i + 1] - start})
    return out


def extract_clip(path: Path, entry: dict) -> bytes:
    with open(path, "rb") as f:
        f.seek(entry["offset"])
        return f.read(entry["size"])


def write_awb(path: Path, files: list[bytes], align: int = 32) -> None:
    """Écrit un AWB simple (sert pour la démo)."""
    count = len(files)
    header = bytearray(b"AFS2" + bytes([1, 4, 2, 0]))
    header += struct.pack("<II", count, align)
    header += b"".join(struct.pack("<H", i) for i in range(count))
    table_pos = len(header)
    header += bytes(4 * (count + 1))

    body = bytearray()
    cursor = len(header)
    offs = []
    for blob in files:
        offs.append(cursor)
        pad = _align(cursor, align) - cursor
        body += bytes(pad) + blob
        cursor += pad + len(blob)
    offs.append(cursor)
    for i, o in enumerate(offs):
        struct.pack_into("<I", header, table_pos + i * 4, o)
    path.write_bytes(bytes(header) + bytes(body))

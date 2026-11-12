"""Lecture des archives CPK de CRI (liste des fichiers et extraction)."""
import struct
from pathlib import Path

from cri_utf import read_utf


def _chunk(f, offset: int) -> bytes:
    """Lit un bloc CPK : 4 octets de signature, 4 inutilisés, taille sur 8 octets, puis la table."""
    f.seek(offset)
    head = f.read(16)
    size = struct.unpack_from("<Q", head, 8)[0]
    return f.read(size)


def list_files(path: Path) -> list[dict]:
    with open(path, "rb") as f:
        if f.read(4) != b"CPK ":
            raise ValueError(f"{path.name} n'est pas un CPK")
        header = read_utf(_chunk(f, 0))[0]
        toc_off = header.get("TocOffset") or 0
        content_off = header.get("ContentOffset") or 0
        if not toc_off:
            raise ValueError(f"{path.name} : pas de table des fichiers (TOC)")
        base = min(toc_off, content_off) if content_off else toc_off
        rows = read_utf(_chunk(f, toc_off))

    out = []
    for r in rows:
        name = r.get("FileName") or ""
        d = r.get("DirName") or ""
        out.append({
            "path": f"{d}/{name}" if d else name,
            "offset": base + r["FileOffset"],
            "size": r["FileSize"],
            "extract_size": r.get("ExtractSize") or r["FileSize"],
        })
    return out


def extract(cpk_path: Path, entry: dict, dst: Path) -> None:
    if entry["size"] != entry["extract_size"]:
        raise ValueError(f"{entry['path']} est compressé (CRILAYLA), non géré")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(cpk_path, "rb") as f, open(dst, "wb") as o:
        f.seek(entry["offset"])
        left = entry["size"]
        while left:
            buf = f.read(min(left, 1 << 20))
            o.write(buf)
            left -= len(buf)

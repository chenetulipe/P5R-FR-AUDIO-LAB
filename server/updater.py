"""Mise à jour de l'outil depuis les « Releases » GitHub du projet."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "chenetulipe/P5R-FR-AUDIO-LAB"
ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
# Ce qui appartient à l'utilisateur et ne doit jamais être écrasé
KEEP = {"data", "mod", "tools", ".git"}

_cache = {"at": 0.0, "value": None}


def current_version() -> str:
    try:
        return VERSION_FILE.read_text("utf-8").strip()
    except OSError:
        return "0.0.0"


def _parse(v: str) -> tuple:
    nums = []
    for part in v.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums + [0] * (3 - len(nums)))


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "P5R-FR-Audio-Lab",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check(force: bool = False) -> dict:
    """Dernière version publiée sur GitHub (gardée 10 minutes en mémoire)."""
    if not force and _cache["value"] and time.time() - _cache["at"] < 600:
        return _cache["value"]
    cur = current_version()
    out = {"current": cur, "latest": cur, "available": False, "notes": "", "url": f"https://github.com/{REPO}/releases"}
    try:
        rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        latest = (rel.get("tag_name") or "").lstrip("vV")
        out.update(latest=latest or cur, notes=rel.get("body") or "", url=rel.get("html_url") or out["url"],
                   zip=rel.get("zipball_url"), available=bool(latest) and _parse(latest) > _parse(cur))
    except Exception as e:  # pas d'internet, pas encore de version publiée...
        out["error"] = str(e)
    _cache.update(at=time.time(), value=out)
    return out


def apply() -> dict:
    """Télécharge la dernière version et remplace les fichiers de l'outil (réglages, voix et mod gardés)."""
    info = check(force=True)
    if not info.get("available") or not info.get("zip"):
        raise RuntimeError("Aucune nouvelle version à installer.")
    data = _get(info["zip"], timeout=120)
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        tops = [p for p in Path(tmp).iterdir() if p.is_dir()]
        if len(tops) != 1 or not (tops[0] / "server" / "app.py").exists():
            raise RuntimeError("Le paquet téléchargé n'a pas la forme attendue.")
        src = tops[0]
        # L'ancienne interface compilée est remplacée en entier (sinon de vieux fichiers traînent)
        if (src / "web" / "dist").exists():
            shutil.rmtree(ROOT / "web" / "dist", ignore_errors=True)
        for item in src.iterdir():
            if item.name in KEEP:
                continue
            dst = ROOT / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
    # Nouvelles dépendances éventuelles
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                    "-r", str(ROOT / "requirements.txt")], capture_output=True)
    _cache.update(at=0.0, value=None)
    return {"installed": info["latest"]}

"""Trouve tout seul Persona 5 Royal (via Steam) et Reloaded-II."""
import json
import os
import re
import string
from pathlib import Path

P5R_APPID = "1687950"


def _steam_root() -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return None


def _steam_libraries() -> list[Path]:
    libs = []
    root = _steam_root()
    if root:
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            text = vdf.read_text("utf-8", "ignore")
            libs += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    # Au cas où Steam n'est pas dans le registre : emplacements habituels sur chaque disque
    for d in string.ascii_uppercase:
        for sub in ("SteamLibrary", "Steam", r"Program Files (x86)\Steam", r"Program Files\Steam", "Games\\Steam"):
            p = Path(f"{d}:\\") / sub
            if p.exists():
                libs.append(p)
    seen, out = set(), []
    for p in libs:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def is_p5r_dir(p: Path) -> bool:
    return (p / "CPK" / "SOUND_E.CPK").exists() or (p / "CPK" / "SOUND_J.CPK").exists()


def find_p5r() -> Path | None:
    for lib in _steam_libraries():
        game = lib / "steamapps" / "common" / "P5R"
        if is_p5r_dir(game):
            return game
    return None


def is_reloaded_dir(p: Path) -> bool:
    return (p / "Reloaded-II.exe").exists()


def reloaded_paths(override: str = "") -> dict | None:
    """Dossiers de Reloaded-II : celui choisi à la main, sinon celui de ses réglages Windows.

    Renvoie {"root", "mods", "apps"} ou None si Reloaded-II est introuvable.
    """
    if override:
        root = Path(override)
        if root.name.lower() == "mods" and is_reloaded_dir(root.parent):
            root = root.parent
        if is_reloaded_dir(root):
            return {"root": root, "mods": root / "Mods", "apps": root / "Apps"}
        return None
    cfg = Path(os.environ.get("APPDATA", "")) / "Reloaded-Mod-Loader-II" / "ReloadedII.json"
    try:
        data = json.loads(cfg.read_text("utf-8-sig"))
    except (OSError, ValueError):
        return None
    mods = Path(data.get("ModConfigDirectory", ""))
    if not data.get("ModConfigDirectory") or not mods.exists():
        return None
    launcher = Path(data.get("LauncherPath", ""))
    root = launcher.parent if data.get("LauncherPath") else mods.parent
    apps = Path(data["ApplicationConfigDirectory"]) if data.get("ApplicationConfigDirectory") else root / "Apps"
    return {"root": root, "mods": mods, "apps": apps}


def find_reloaded_mods() -> Path | None:
    p = reloaded_paths()
    return p["mods"] if p else None

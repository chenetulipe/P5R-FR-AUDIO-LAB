"""P5R Audio Lab — serveur local (API + interface)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import warnings
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

warnings.filterwarnings("ignore", category=DeprecationWarning)

import awb
import cpk
import detect
import tools
import updater

ROOT = tools.ROOT
DATA = Path(os.environ["P5R_DATA"]) if os.environ.get("P5R_DATA") else ROOT / "data"
CACHE = DATA / "cache"
CONFIG_FILE = DATA / "config.json"
DIST = ROOT / "web" / "dist"
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}

# Supposition basée sur l'ordre des persos dans P5R : à corriger dans l'appli si faux.
DEFAULT_NAMES = {
    "BP01": "Joker", "BP02": "Skull", "BP03": "Mona", "BP04": "Panther", "BP05": "Fox",
    "BP06": "Queen", "BP07": "Noir", "BP08": "Oracle", "BP09": "Crow", "BP09_01": "Crow (2)",
    "BP10": "Violet", "SPT01": "Navi SPT01", "SPT02": "Navi SPT02", "SPT04": "Navi SPT04",
}

DEFAULT_CONFIG = {
    "sound_dir": "",
    "mod_dir": str(ROOT / "mod" / "p5rpc.vf.combat"),
    "rec_dir": "",
    "game_dir": "",
    "lang": "E",
    "names": DEFAULT_NAMES,
    "match_volume": True,
    "trim_silence": True,
    "reloaded_dir": "",  # vide = détection automatique
}

MOD_CONFIG = {
    "ModId": "p5rpc.vf.combat",
    "ModName": "PERSONA 5 ROYAL MOD VF",
    "ModAuthor": "FreezyWeakBa",
    "ModVersion": "0.1.0",
    "ModDescription": "Doublage français des répliques de combat.",
    "ModDll": "",
    "ModIcon": "",
    "ModR2RManagedDll32": "",
    "ModR2RManagedDll64": "",
    "ModNativeDll32": "",
    "ModNativeDll64": "",
    "IsLibrary": False,
    "ReleaseMetadataFileName": "",
    "PluginData": {},
    "IsUniversalMod": False,
    "ModDependencies": ["p5rpc.modloader", "reloaded.universal.fileemulationframework.awb"],
    "OptionalDependencies": [],
    "SupportedAppId": ["p5r.exe"],
}

_lock = threading.Lock()
NO_CACHE = {"Cache-Control": "no-store"}
app = FastAPI(title="P5R Audio Lab")



from fastapi.responses import JSONResponse  # noqa: E402


@app.exception_handler(RuntimeError)
def _tool_error(_, exc: RuntimeError):
    """Une erreur d'outil audio (vgmstream, ffmpeg, VGAudio) devient un message lisible."""
    return JSONResponse(status_code=500, content={"detail": str(exc)})


SETUP = {"status": "ready", "message": ""}


def auto_setup() -> None:
    """Premier lancement : trouve P5R et Reloaded-II, puis extrait les voix de combat."""
    cfg = load_config()
    try:
        ensure_mod_config()
        link_reloaded()
        if not cfg.get("sound_dir") or not Path(cfg["sound_dir"]).exists():
            SETUP.update(status="detecting", message="Recherche de Persona 5 Royal…")
            game = Path(cfg["game_dir"]) if cfg.get("game_dir") and detect.is_p5r_dir(Path(cfg["game_dir"])) else detect.find_p5r()
            if not game:
                SETUP.update(status="not_found", message="Persona 5 Royal n'a pas été trouvé automatiquement.")
                return
            SETUP.update(status="extracting", message="Extraction des voix de combat…")
            do_extract(str(game), cfg.get("lang") or "E")
        SETUP.update(status="ready", message="")
        warm_all_meta()
    except Exception as e:
        SETUP.update(status="error", message=f"Préparation impossible : {e}")


@app.on_event("startup")
def _startup():
    threading.Thread(target=auto_setup, daemon=True).start()


# ---------- stockage ----------

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text("utf-8-sig")))
        except ValueError:
            # Réglages illisibles : on les met de côté et on repart des réglages par défaut
            CONFIG_FILE.replace(CONFIG_FILE.with_name("config_illisible.json"))
    cfg["names"] = {**DEFAULT_NAMES, **cfg.get("names", {})}
    return cfg


def save_config(cfg: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


def notes_file(bank: str) -> Path:
    return DATA / "notes" / f"{bank}.json"


def load_notes(bank: str) -> dict:
    f = notes_file(bank)
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def save_notes(bank: str, notes: dict) -> None:
    f = notes_file(bank)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(notes, indent=1, ensure_ascii=False), "utf-8")


# ---------- chemins ----------

def check_bank(bank: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", bank):
        raise HTTPException(400, "Nom d'archive invalide.")
    return bank.upper()


def awb_path(bank: str) -> Path:
    sd = load_config()["sound_dir"]
    sound = Path(sd) if sd else None
    for p in (sound.glob("*") if sound else []):
        if p.stem.upper() == bank and p.suffix.lower() == ".awb":
            return p
    raise HTTPException(404, f"{bank}.AWB introuvable dans le dossier du jeu.")


def mod_bank_dir(bank: str) -> Path:
    return Path(load_config()["mod_dir"]) / "FEmulator" / "AWB" / f"{bank}.AWB"


def vf_file(bank: str, index: int) -> Path | None:
    d = mod_bank_dir(bank)
    if not d.exists():
        return None
    for p in d.glob(f"{index}*.adx"):
        if re.match(rf"{index}(\D|$)", p.stem):
            return p
    return None


def ensure_mod_config() -> None:
    mod = Path(load_config()["mod_dir"])
    mod.mkdir(parents=True, exist_ok=True)
    f = mod / "ModConfig.json"
    cfg = dict(MOD_CONFIG)
    if f.exists():
        try:
            old = json.loads(f.read_text("utf-8-sig"))
            cfg = {**old, **{k: MOD_CONFIG[k] for k in ("ModId", "ModName", "ModAuthor", "ModDependencies", "SupportedAppId")}}
        except ValueError:
            pass
    f.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


# ---------- métadonnées et cache audio ----------

_bank_locks: dict[str, threading.Lock] = {}
_warming: set[str] = set()


def bank_lock(bank: str) -> threading.Lock:
    with _lock:
        return _bank_locks.setdefault(bank, threading.Lock())


def source_cache(bank: str) -> Path:
    """Dossier de cache propre au fichier AWB utilisé (démo, anglais ou japonais)."""
    path = awb_path(bank)
    st = path.stat()
    key = hashlib.md5(f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:10]
    return CACHE / bank / key


_meta_mem: dict[str, list[dict]] = {}


def bank_meta(bank: str) -> list[dict]:
    """Infos de tous les clips (nom du cue, durée...). Un seul appel à vgmstream, puis cache disque et mémoire."""
    cache = source_cache(bank) / "meta.json"
    key = str(cache)
    if key in _meta_mem:
        return _meta_mem[key]
    if cache.exists():
        _meta_mem[key] = json.loads(cache.read_text("utf-8"))
        return _meta_mem[key]
    with bank_lock(bank):
        if cache.exists():
            _meta_mem[key] = json.loads(cache.read_text("utf-8"))
            return _meta_mem[key]
        path = awb_path(bank)
        entries = awb.read_awb(path)
        infos = tools.probe_all(path)
        clips = [{**e, **(infos[i] if i < len(infos) else {})} for i, e in enumerate(entries)]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(clips), "utf-8")
        _meta_mem[key] = clips
        return clips


def decode_bank(bank: str) -> Path:
    """Décode toutes les VO d'un perso dans le cache (une seule fois, même si on le demande en parallèle)."""
    out = source_cache(bank) / "vo"
    if (out / ".complete").exists():
        return out
    with bank_lock(bank):
        if (out / ".complete").exists():
            return out
        tmp = Path(tempfile.mkdtemp(prefix="vo_", dir=out.parent if out.parent.exists() else None))
        try:
            tools.decode_all(awb_path(bank), tmp)
            out.mkdir(parents=True, exist_ok=True)
            for f in tmp.glob("*.wav"):
                dst = out / f"{int(f.stem) - 1}.wav"
                if not dst.exists():
                    f.replace(dst)
            (out / ".complete").touch()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def warm_bank(bank: str) -> None:
    """Décode en arrière-plan toutes les VO d'un perso pour que la lecture soit instantanée."""
    with _lock:
        if bank in _warming:
            return
        _warming.add(bank)

    def job():
        try:
            decode_bank(bank)
        except Exception as e:
            print("Préchargement", bank, "impossible :", e)
        finally:
            with _lock:
                _warming.discard(bank)

    threading.Thread(target=job, daemon=True).start()


def warm_all_meta() -> None:
    """Au démarrage : prépare les infos de tous les persos, pour que chaque ouverture soit immédiate."""
    def job():
        for b in banks():
            try:
                bank_meta(b["bank"])
            except Exception as e:
                print("Infos", b["bank"], "impossibles :", e)
    threading.Thread(target=job, daemon=True).start()


def get_clip(bank: str, index: int) -> dict:
    clip = next((c for c in bank_meta(bank) if c["index"] == index), None)
    if not clip:
        raise HTTPException(404, f"Le clip {index} n'existe pas dans {bank}.")
    return clip


def vo_wav(bank: str, index: int) -> Path:
    get_clip(bank, index)
    out = source_cache(bank) / "vo" / f"{index}.wav"
    if not out.exists():
        tools.decode(awb_path(bank), out, index + 1)
    return out


def import_clip(bank: str, index: int, src: Path) -> dict:
    clip = next((c for c in bank_meta(bank) if c["index"] == index), None)
    if not clip:
        raise HTTPException(404, f"Le clip {index} n'existe pas dans {bank}.")
    ensure_mod_config()
    old = vf_file(bank, index)
    if old:
        old.unlink()
    dst = mod_bank_dir(bank) / f"{index}_streaming.adx"
    cfg = load_config()
    match = vo_wav(bank, index) if cfg["match_volume"] else None
    info = tools.encode_p5r_adx(src, dst, clip["rate"] or 48000, clip["channels"] or 1, match,
                                trim=cfg.get("trim_silence", True))
    return {"index": index, "file": dst.name, "path": str(dst), **info}


# ---------- API ----------

class ConfigIn(BaseModel):
    sound_dir: str | None = None
    game_dir: str | None = None
    lang: str | None = None
    mod_dir: str | None = None
    rec_dir: str | None = None
    names: dict | None = None
    match_volume: bool | None = None
    trim_silence: bool | None = None
    reloaded_dir: str | None = None


class NoteIn(BaseModel):
    text: str | None = None
    valid: bool | None = None


class BrowseIn(BaseModel):
    start: str = ""


class OpenIn(BaseModel):
    what: str


# ---------- Reloaded-II ----------
# Le mod vit dans le dossier de l'outil (mod/p5rpc.vf.combat). Si Reloaded-II est installé,
# on crée dans son dossier Mods un lien (jonction Windows) vers ce dossier : un seul mod, visible aux deux endroits.

def _is_link(p: Path) -> bool:
    import ctypes
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
    return attrs not in (-1, 0xFFFFFFFF) and bool(attrs & 0x400)


def reloaded_paths() -> dict | None:
    if os.environ.get("P5R_NO_RELOADED"):  # tests : ne jamais toucher au vrai Reloaded-II
        return None
    return detect.reloaded_paths(load_config().get("reloaded_dir", ""))


def _app_config(paths: dict) -> tuple[Path, dict | None]:
    f = paths["apps"] / "p5r.exe" / "AppConfig.json"
    try:
        return f, json.loads(f.read_text("utf-8-sig"))
    except (OSError, ValueError):
        return f, None


def reloaded_status() -> dict:
    """Où en est le branchement avec Reloaded-II, étape par étape."""
    cfg = load_config()
    mod = Path(cfg["mod_dir"])
    paths = reloaded_paths()
    out = {"installed": bool(paths), "mod": str(mod), "manual": bool(cfg.get("reloaded_dir")),
           "root": "", "target": "", "linked": False, "essentials": False, "p5r_added": False, "enabled": False}
    if not paths:
        return out
    target = paths["mods"] / MOD_CONFIG["ModId"]
    _, app_cfg = _app_config(paths)
    enabled = set((app_cfg or {}).get("EnabledMods") or [])
    out.update(
        root=str(paths["root"]),
        target=str(target),
        linked=target.exists() and target.resolve() == mod.resolve(),
        essentials=(paths["mods"] / "p5rpc.modloader" / "ModConfig.json").exists(),
        p5r_added=app_cfg is not None,
        enabled=MOD_CONFIG["ModId"] in enabled and "p5rpc.modloader" in enabled,
    )
    return out


def link_reloaded() -> dict:
    """Relie le mod de l'outil au dossier Mods de Reloaded-II (sans rien copier)."""
    paths = reloaded_paths()
    mod = Path(load_config()["mod_dir"])
    if not paths or not paths["mods"].exists():
        return reloaded_status()
    mods = paths["mods"]
    mod.mkdir(parents=True, exist_ok=True)
    target = mods / MOD_CONFIG["ModId"]
    if target.exists() and target.resolve() == mod.resolve():
        return reloaded_status()
    if _is_link(target):
        os.rmdir(target)  # retire seulement le lien, pas son contenu
    elif target.exists():
        # Ancien dossier du mod directement dans Reloaded : on récupère ses VF puis on le met de côté
        src = target / "FEmulator"
        if src.exists():
            for f in src.rglob("*"):
                dst = mod / "FEmulator" / f.relative_to(src)
                if f.is_file() and not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
        import time
        backup = DATA / f"ancien_mod_reloaded_{time.strftime('%Y%m%d_%H%M%S')}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(backup))
    subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(mod)], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return reloaded_status()


@app.post("/api/reloaded/link")
def api_link_reloaded():
    ensure_mod_config()
    return link_reloaded()


@app.post("/api/reloaded/enable")
def api_enable_mod():
    """Coche le mod (et Persona Essentials) pour P5R dans Reloaded-II."""
    paths = reloaded_paths()
    if not paths:
        raise HTTPException(404, "Reloaded-II est introuvable.")
    f, app_cfg = _app_config(paths)
    if app_cfg is None:
        raise HTTPException(409, "P5R n'est pas encore ajouté dans Reloaded-II : ouvre Reloaded-II, clique sur « + » et choisis P5R.exe.")
    enabled = list(app_cfg.get("EnabledMods") or [])
    for mid in ("p5rpc.modloader", MOD_CONFIG["ModId"]):
        if mid not in enabled:
            enabled.append(mid)
    app_cfg["EnabledMods"] = enabled
    f.write_text(json.dumps(app_cfg, indent=2, ensure_ascii=False), "utf-8")
    return reloaded_status()


@app.post("/api/reloaded/install")
def api_install_reloaded():
    """Télécharge l'installateur officiel de Reloaded-II et le lance."""
    import urllib.request
    url = "https://github.com/Reloaded-Project/Reloaded-II/releases/latest/download/Setup.exe"
    dst = DATA / "Reloaded-II-Setup.exe"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "P5R-Audio-Lab"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(r.read())
    except Exception as e:
        raise HTTPException(502, f"Téléchargement de Reloaded-II impossible : {e}")
    os.startfile(str(dst))
    return {"ok": True}


@app.get("/api/update")
def api_check_update(force: bool = False):
    return updater.check(force)


@app.post("/api/update")
def api_apply_update():
    try:
        res = updater.apply()
    except Exception as e:
        raise HTTPException(500, f"Mise à jour impossible : {e}")
    threading.Timer(0.8, restart_tool).start()
    return res


def _parent_pid(pid: int) -> tuple[int, str]:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; \"$($p.ParentProcessId) $($p.Name)\""],
                         capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    parts = out.stdout.decode("cp850", "ignore").strip().split(" ", 1)
    try:
        return int(parts[0]), parts[1] if len(parts) > 1 else ""
    except ValueError:
        return 0, ""


def restart_tool() -> None:
    """Après une mise à jour : relance start.bat dans une nouvelle fenêtre et ferme l'ancienne.

    On ne laisse pas l'ancienne fenêtre continuer à lire start.bat : s'il a été remplacé par la mise à jour,
    Windows lirait la suite du nouveau fichier au mauvais endroit.
    """
    env = dict(os.environ, P5R_NO_BROWSER="1", P5R_RESTART="1")
    subprocess.Popen(["cmd", "/c", "start", "P5R FR Audio Lab", "cmd", "/c", str(ROOT / "start.bat")],
                     cwd=str(ROOT), env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    # Retrouve la fenêtre (cmd.exe) qui a lancé l'outil et la ferme
    pid = os.getpid()
    for _ in range(4):
        pid, name = _parent_pid(pid)
        if not pid:
            break
        if name.lower() == "cmd.exe":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            break
    os._exit(0)


@app.get("/api/whoami")
def whoami():
    return {"root": str(ROOT), "version": updater.current_version()}


@app.get("/api/state")
def state():
    cfg = load_config()
    return {"config": cfg, "tools": tools.status(), "keycode": tools.P5R_KEYCODE, "setup": SETUP,
            "version": updater.current_version(),
            "reloaded": reloaded_status()}


@app.post("/api/config")
def set_config(body: ConfigIn):
    if body.reloaded_dir and not detect.reloaded_paths(body.reloaded_dir):
        raise HTTPException(400, "Ce dossier ne contient pas Reloaded-II.exe. Choisis le dossier où se trouve Reloaded-II.exe.")
    relink = body.mod_dir is not None or (body.reloaded_dir is not None and body.reloaded_dir != load_config().get("reloaded_dir", ""))
    old = reloaded_paths() if relink else None
    with _lock:
        cfg = load_config()
        cfg.update({k: v for k, v in body.model_dump().items() if v is not None})
        save_config(cfg)
    if relink:
        # Retire l'ancien lien (ancien dossier de Reloaded-II) s'il pointait vers notre mod
        if old:
            t = old["mods"] / MOD_CONFIG["ModId"]
            new = reloaded_paths()
            if _is_link(t) and (not new or t != new["mods"] / MOD_CONFIG["ModId"]):
                os.rmdir(t)
        ensure_mod_config()
        link_reloaded()
    return cfg


@app.post("/api/browse")
def browse(body: BrowseIn):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(initialdir=body.start or None)
    root.destroy()
    return {"path": path.replace("/", "\\") if path else ""}


@app.post("/api/open")
def open_folder(body: OpenIn):
    cfg = load_config()
    target = {"mod": cfg["mod_dir"], "rec": cfg["rec_dir"], "sound": cfg["sound_dir"]}.get(body.what)
    if not target or not Path(target).exists():
        raise HTTPException(404, "Ce dossier n'existe pas encore.")
    os.startfile(target)
    return {"ok": True}


class ExtractIn(BaseModel):
    game_dir: str
    lang: str = "E"


@app.post("/api/game/extract")
def extract_game(body: ExtractIn):
    return do_extract(body.game_dir, body.lang)


def do_extract(game_dir: str, lang: str = "E") -> dict:
    """Extrait les voix de combat (BPxx + SPTxx) du CPK de voix choisi."""
    lang = "J" if lang.upper().startswith("J") else "E"
    src = Path(game_dir) / "CPK" / f"SOUND_{lang}.CPK"
    if not src.exists():
        raise HTTPException(404, f"SOUND_{lang}.CPK introuvable. Le dossier du jeu doit contenir CPK\\SOUND_{lang}.CPK.")
    dst = DATA / "game" / f"SOUND_{lang}"
    files = [f for f in cpk.list_files(src)
             if re.fullmatch(r"SOUND/BATTLE/(BP|SPT)\w+\.(ACB|AWB)", f["path"], re.I)]
    for f in files:
        out = dst / f["path"].split("/")[-1]
        if not (out.exists() and out.stat().st_size == f["size"]):
            cpk.extract(src, f, out)
    with _lock:
        cfg = load_config()
        cfg.update(game_dir=str(game_dir), lang=lang, sound_dir=str(dst))
        save_config(cfg)
    return {"count": len(files), "sound_dir": str(dst)}


@app.post("/api/banks/{bank}/clips/{index}/reveal")
def reveal(bank: str, index: int):
    """Ouvre l'Explorateur avec le fichier VF sélectionné."""
    f = vf_file(check_bank(bank), index)
    if not f:
        raise HTTPException(404, "Pas encore de VF pour ce clip.")
    import subprocess
    subprocess.Popen(["explorer", "/select,", str(f)])
    return {"ok": True}


@app.get("/api/banks")
def banks():
    cfg = load_config()
    if not cfg.get("sound_dir"):
        return []
    sound = Path(cfg["sound_dir"])
    if not sound.exists():
        return []
    out = []
    for p in sorted(sound.glob("*")):
        if p.suffix.lower() != ".awb":
            continue
        bank = p.stem.upper()
        try:
            count = len(awb.read_awb(p))
        except Exception:
            continue
        notes = load_notes(bank)
        d = mod_bank_dir(bank)
        done = len({m.group(1) for f in d.glob("*.adx") if (m := re.match(r"(\d+)", f.stem))}) if d.exists() else 0
        out.append({
            "bank": bank,
            "name": cfg["names"].get(bank, bank),
            "count": count,
            "done": min(done, count),
            "valid": sum(1 for n in notes.values() if n.get("valid")),
        })
    return out


@app.get("/api/banks/{bank}/clips")
def clips(bank: str):
    bank = check_bank(bank)
    notes = load_notes(bank)
    d = mod_bank_dir(bank)
    vfs = {}
    if d.exists():
        for f in d.glob("*.adx"):
            m = re.match(r"(\d+)(\D|$)", f.stem)
            if m:
                vfs[int(m.group(1))] = f.name
    sugg = load_suggestions(bank)
    tf = DATA / "transcripts" / f"{bank.lower()}_en.json"
    en = json.loads(tf.read_text("utf-8")) if tf.exists() else {}
    out = []
    for c in bank_meta(bank):
        n = notes.get(str(c["index"]), {})
        vf = vfs.get(c["index"])
        vf_dur = tools.adx_duration(d / vf) if vf else 0
        sg = sugg.get(str(c["index"]))
        out.append({"index": c["index"], "name": c.get("name"), "duration": c.get("duration", 0),
                    "en": en.get(f"{c['index']}.wav", ""), "text": n.get("text", ""), "valid": bool(n.get("valid")) and bool(vf), "vf": vf, "vf_duration": vf_dur,
                    "suggest": {"file": Path(sg["file"]).name, "fr": sg.get("fr", ""), "sure": sg.get("sure", True)}
                    if sg and not vf and Path(sg["file"]).exists() else None})
    warm_bank(bank)
    return out


# ---------- propositions (VF trouvées automatiquement, à valider à l'oreille) ----------

def suggestions_file(bank: str) -> Path:
    return DATA / "suggestions" / f"{bank}.json"


def load_suggestions(bank: str) -> dict:
    f = suggestions_file(bank)
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def save_suggestions(bank: str, data: dict) -> None:
    f = suggestions_file(bank)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=1, ensure_ascii=False), "utf-8")


def suggestion(bank: str, index: int) -> dict:
    sg = load_suggestions(bank).get(str(index))
    if not sg or not Path(sg["file"]).exists():
        raise HTTPException(404, "Pas de proposition pour ce clip.")
    return sg


@app.get("/api/banks/{bank}/clips/{index}/suggest")
def play_suggestion(bank: str, index: int):
    return FileResponse(suggestion(check_bank(bank), index)["file"], media_type="audio/wav", headers=NO_CACHE)


@app.post("/api/banks/{bank}/clips/{index}/suggest")
def accept_suggestion(bank: str, index: int):
    bank = check_bank(bank)
    sg = suggestion(bank, index)
    res = import_clip(bank, index, Path(sg["file"]))
    if sg.get("fr"):
        with _lock:
            notes = load_notes(bank)
            n = notes.setdefault(str(index), {})
            if not n.get("text"):
                n["text"] = sg["fr"]
            save_notes(bank, notes)
    return {**res, "text": sg.get("fr", "")}


@app.post("/api/banks/{bank}/suggest/accept-sure")
def accept_sure(bank: str):
    """Pose d'un coup toutes les propositions marquées sûres (celles « à vérifier » restent)."""
    bank = check_bank(bank)
    d = mod_bank_dir(bank)
    taken = {int(m.group(1)) for f in d.glob("*.adx") if (m := re.match(r"(\d+)", f.stem))} if d.exists() else set()
    done, errors = [], []
    for k, sg in load_suggestions(bank).items():
        if not sg.get("sure") or int(k) in taken or not Path(sg["file"]).exists():
            continue
        try:
            done.append(accept_suggestion(bank, int(k))["index"])
        except Exception as e:
            errors.append({"index": int(k), "error": getattr(e, "detail", str(e))})
    return {"done": done, "errors": errors}


@app.delete("/api/banks/{bank}/clips/{index}/suggest")
def reject_suggestion(bank: str, index: int):
    bank = check_bank(bank)
    with _lock:
        data = load_suggestions(bank)
        data.pop(str(index), None)
        save_suggestions(bank, data)
    return {"ok": True}


def export_name(bank: str, clip: dict) -> str:
    """Nom de fichier d'export : BP01_3_Cue3001.wav (l'import groupé reconnaît ce format)."""
    cue = re.sub(r"[^\w\-]+", "-", (clip.get("name") or "").split(";")[0].strip()).strip("-")
    return f"{bank}_{clip['index']}" + (f"_{cue}" if cue else "") + ".wav"


@app.get("/api/banks/{bank}/clips/{index}/download")
def download_clip(bank: str, index: int, kind: str = "vo"):
    bank = check_bank(bank)
    clip = next((c for c in bank_meta(bank) if c["index"] == index), None)
    if not clip:
        raise HTTPException(404, "Clip introuvable.")
    if kind == "vf":
        src = vf_file(bank, index)
        if not src:
            raise HTTPException(404, "Pas encore de VF pour ce clip.")
        out = CACHE / bank / "vf" / str(index) / f"{int(src.stat().st_mtime)}.wav"
        if not out.exists():
            tools.decode(src, out)
        name = export_name(bank, clip).replace(".wav", "_VF.wav")
    else:
        out, name = vo_wav(bank, index), export_name(bank, clip)
    return FileResponse(out, media_type="audio/wav", filename=name, headers=NO_CACHE)


@app.get("/api/banks/{bank}/export")
def export_bank(bank: str):
    """Toutes les VO d'un perso dans un zip, nommées pour l'import groupé, avec une liste CSV."""
    import csv
    import io
    import zipfile
    bank = check_bank(bank)
    clips = bank_meta(bank)
    vo = decode_bank(bank)
    name = load_config()["names"].get(bank, bank)
    safe = re.sub(r"[^\w]+", "_", name)
    out = DATA / "exports" / f"{bank}_{safe}_VO.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    notes = load_notes(bank)
    rows = io.StringIO()
    w = csv.writer(rows, delimiter=";")
    w.writerow(["fichier", "n°", "cue", "durée (s)", "transcription"])
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for c in clips:
            f = vo / f"{c['index']}.wav"
            if not f.exists():
                tools.decode(awb_path(bank), f, c["index"] + 1)
            fname = export_name(bank, c)
            z.write(f, f"{bank}/{fname}")
            w.writerow([fname, c["index"], c.get("name") or "", str(c.get("duration") or "").replace(".", ","),
                        notes.get(str(c["index"]), {}).get("text", "")])
        z.writestr(f"{bank}/liste_{bank}.csv", "﻿" + rows.getvalue())
    return FileResponse(out, media_type="application/zip", filename=out.name, headers=NO_CACHE)


@app.get("/api/banks/{bank}/clips/{index}/vo")
def play_vo(bank: str, index: int):
    return FileResponse(vo_wav(check_bank(bank), index), media_type="audio/wav", headers=NO_CACHE)


@app.get("/api/banks/{bank}/clips/{index}/vf")
def play_vf(bank: str, index: int):
    bank = check_bank(bank)
    src = vf_file(bank, index)
    if not src:
        raise HTTPException(404, "Pas encore de VF pour ce clip.")
    out = CACHE / bank / "vf" / str(index) / f"{int(src.stat().st_mtime)}.wav"
    if not out.exists():
        tools.decode(src, out)
    return FileResponse(out, media_type="audio/wav", headers=NO_CACHE)


@app.post("/api/banks/{bank}/clips/{index}/vf")
async def upload_vf(bank: str, index: int, file: UploadFile):
    bank = check_bank(bank)
    suffix = Path(file.filename or "x.wav").suffix.lower()
    if suffix not in AUDIO_EXT:
        raise HTTPException(400, f"Format {suffix} non géré. Utilise du WAV, MP3, FLAC ou OGG.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{suffix}"
        src.write_bytes(await file.read())
        try:
            return import_clip(bank, index, src)
        except RuntimeError as e:
            raise HTTPException(500, str(e))


@app.delete("/api/banks/{bank}/clips/{index}/vf")
def delete_vf(bank: str, index: int):
    bank = check_bank(bank)
    f = vf_file(bank, index)
    if f:
        trash = DATA / "corbeille" / bank
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(trash / f.name))
    with _lock:
        notes = load_notes(bank)
        notes.setdefault(str(index), {})["valid"] = False
        save_notes(bank, notes)
    return {"ok": True}


@app.post("/api/banks/{bank}/clips/{index}/restore")
def restore_vf(bank: str, index: int):
    """Annule « Retirer » : remet la VF sortie de la corbeille."""
    bank = check_bank(bank)
    trash = DATA / "corbeille" / bank
    found = [p for p in trash.glob(f"{index}*.adx") if re.match(rf"{index}(\D|$)", p.stem)] if trash.exists() else []
    if not found:
        raise HTTPException(404, "Rien à restaurer pour ce clip.")
    if vf_file(bank, index):
        raise HTTPException(409, "Une autre VF a déjà été posée sur ce clip.")
    dst = mod_bank_dir(bank) / found[0].name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(found[0]), str(dst))
    return {"file": dst.name, "vf_duration": tools.adx_duration(dst)}


@app.patch("/api/banks/{bank}/clips/{index}")
def patch_note(bank: str, index: int, body: NoteIn):
    bank = check_bank(bank)
    with _lock:
        notes = load_notes(bank)
        n = notes.setdefault(str(index), {})
        n.update({k: v for k, v in body.model_dump().items() if v is not None})
        save_notes(bank, notes)
    return n


def parse_rec_name(p: Path, bank: str, all_banks: list[str]) -> int | None:
    """Numéro de clip d'un enregistrement pour ce perso : BP01_118_Cue.wav, BP01-118.wav ou BP01/118.wav."""
    stem = p.stem.upper()
    # Le nom de perso le plus long qui correspond (BP09_01 avant BP09)
    owner = max((b for b in all_banks if stem.startswith(b.upper())), key=len, default=None)
    if owner:
        if owner.upper() != bank.upper():
            return None
        m = re.match(r"[_\- #]*(\d+)", stem[len(owner):])
        return int(m.group(1)) if m else None
    if p.parent.name.upper() == bank.upper():
        m = re.match(r"(\d+)", stem)
        return int(m.group(1)) if m else None
    return None


@app.post("/api/banks/{bank}/batch")
def batch(bank: str):
    """Importe tous les enregistrements nommés BP01_118.wav ou rangés dans BP01/118.wav."""
    bank = check_bank(bank)
    rec_dir = load_config().get("rec_dir") or ""
    rec = Path(rec_dir)
    if not rec_dir or not rec.is_dir():
        raise HTTPException(400, "Choisis d'abord le dossier des enregistrements VF dans les réglages.")
    found: dict[int, Path] = {}
    all_banks = [b["bank"] for b in banks()]
    for p in rec.rglob("*"):
        if p.suffix.lower() not in AUDIO_EXT:
            continue
        idx = parse_rec_name(p, bank, all_banks)
        if idx is not None:
            found[idx] = p
    done, errors = [], []
    for idx, p in sorted(found.items()):
        try:
            done.append(import_clip(bank, idx, p))
        except Exception as e:
            errors.append({"index": idx, "file": p.name, "error": getattr(e, "detail", str(e))})
    return {"imported": done, "errors": errors, "found": len(found)}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")


if __name__ == "__main__":
    import webbrowser
    import uvicorn
    import socket
    import time
    import urllib.request
    PORT = 8005
    url = f"http://127.0.0.1:{PORT}"

    def port_busy() -> bool:
        with socket.socket() as sk:
            return sk.connect_ex(("127.0.0.1", PORT)) == 0

    if os.environ.get("P5R_RESTART"):
        # Redémarrage après mise à jour : on attend que l'ancienne version ait libéré la place
        for _ in range(60):
            if not port_busy():
                break
            time.sleep(0.25)
    if port_busy():
        try:
            other = json.load(urllib.request.urlopen(url + "/api/whoami", timeout=3))["root"]
        except Exception:
            other = "une ancienne version"
        if Path(other) == ROOT:
            # Cette copie tourne déjà : on ouvre juste la page
            if not os.environ.get("P5R_NO_BROWSER"):
                webbrowser.open(url)
            raise SystemExit
        # Une autre copie de l'outil occupe la place : on la ferme pour que tout aille dans CE dossier
        print(f"  Une autre copie de l'outil tournait ({other}) : elle est fermée.", flush=True)
        out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout.decode("cp850", "ignore")
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{PORT}") and parts[3] == "LISTENING":
                subprocess.run(["taskkill", "/F", "/PID", parts[4]], capture_output=True)
        for _ in range(40):
            if not port_busy():
                break
            time.sleep(0.25)
    print(f"  Dossier de l'outil : {ROOT}", flush=True)
    print(f"  Version : {updater.current_version()}", flush=True)
    if not os.environ.get("P5R_NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT)

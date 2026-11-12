"""Appels aux outils externes : vgmstream (lecture), VGAudio (encodage ADX), ffmpeg (conversion)."""
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

VGMSTREAM = TOOLS / "vgmstream" / "vgmstream-cli.exe"
VGAUDIO = TOOLS / "vgaudio" / "net451_standalone" / "VGAudioCli.exe"


def _ffmpeg() -> Path:
    """ffmpeg vient du paquet Python imageio-ffmpeg (installé par start.bat)."""
    local = TOOLS / "ffmpeg" / "ffmpeg.exe"
    if local.exists():
        return local
    try:
        import imageio_ffmpeg
        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return local


FFMPEG = _ffmpeg()

# Clé de chiffrement ADX de P5R PC (sans elle, le son sort saturé en jeu).
P5R_KEYCODE = "9923540143823782"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd: list, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, timeout=timeout,
                          creationflags=_NO_WINDOW)


def status() -> dict:
    return {name: p.exists() for name, p in
            {"vgmstream": VGMSTREAM, "vgaudio": VGAUDIO, "ffmpeg": FFMPEG}.items()}


def probe(path: Path, subsong: int | None = None) -> dict:
    """Infos d'un son (ou d'un clip d'AWB, subsong commence à 1)."""
    cmd = [VGMSTREAM, "-m"]
    if subsong:
        cmd += ["-s", subsong]
    out = _run(cmd + [path]).stdout.decode("utf-8", "ignore")

    def grab(pattern, cast=str, default=None):
        m = re.search(pattern, out)
        return cast(m.group(1).strip()) if m else default

    rate = grab(r"sample rate:\s*(\d+)", int, 0)
    samples = grab(r"stream total samples:\s*(\d+)", int, 0)
    return {
        "name": grab(r"stream name:\s*(.+)"),
        "count": grab(r"stream count:\s*(\d+)", int, 1),
        "rate": rate,
        "channels": grab(r"channels:\s*(\d+)", int, 1),
        "duration": round(samples / rate, 2) if rate else 0,
        "codec": grab(r"encoding:\s*(.+)"),
    }


def probe_all(path: Path) -> list[dict]:
    """Infos de tous les clips d'un AWB en un seul appel (beaucoup plus rapide qu'un appel par clip)."""
    out = _run([VGMSTREAM, "-m", "-I", "-s", 1, "-S", 0, path], timeout=300).stdout.decode("utf-8", "ignore")
    clips = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        j = json.loads(line)
        rate = j.get("sampleRate") or 0
        samples = j.get("playSamples") or j.get("numberOfSamples") or 0
        clips.append({
            "name": (j.get("streamInfo") or {}).get("name"),
            "rate": rate,
            "channels": j.get("channels") or 1,
            "duration": round(samples / rate, 2) if rate else 0,
        })
    return clips


def decode_all(src: Path, out_dir: Path) -> None:
    """Décode tous les clips d'un AWB dans out_dir (1.wav, 2.wav... numérotés à partir de 1)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _run([VGMSTREAM, "-s", 1, "-S", 0, "-o", str(out_dir / "?s.wav"), src], timeout=900)


def decode(src: Path, dst: Path, subsong: int | None = None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [VGMSTREAM, "-o", dst]
    if subsong:
        cmd += ["-s", subsong]
    r = _run(cmd + [src])
    if not dst.exists():
        raise RuntimeError("vgmstream n'a pas pu décoder : " + r.stderr.decode("utf-8", "ignore")[-300:])


def mean_volume(path: Path) -> float | None:
    r = _run([FFMPEG, "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr.decode("utf-8", "ignore"))
    return float(m.group(1)) if m else None


# Coupe le silence au début et à la fin (en gardant 30 ms) : la réplique part pile au bon moment en jeu.
TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.03,"
        "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.03,areverse")


def adx_duration(path: Path) -> float:
    """Durée d'un ADX lue directement dans son en-tête (instantané)."""
    try:
        with open(path, "rb") as f:
            h = f.read(16)
        if h[:2] != b"\x80\x00":
            return 0.0
        rate = int.from_bytes(h[8:12], "big")
        samples = int.from_bytes(h[12:16], "big")
        return round(samples / rate, 2) if rate else 0.0
    except OSError:
        return 0.0


def encode_p5r_adx(src: Path, dst: Path, rate: int, channels: int, match_wav: Path | None = None,
                   trim: bool = True) -> dict:
    """WAV/MP3/FLAC... -> ADX chiffré P5R, au même format que l'original."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Mise au format de travail (et silences coupés)
        clean = Path(tmp) / "clean.wav"
        r = _run([FFMPEG, "-y", "-hide_banner", "-i", src] + (["-af", TRIM] if trim else []) +
                 ["-c:a", "pcm_s16le", "-map_metadata", "-1", clean])
        if not clean.exists() or clean.stat().st_size < 1000:
            # Fichier trop court ou silence total : on garde l'original sans couper
            r = _run([FFMPEG, "-y", "-hide_banner", "-i", src, "-c:a", "pcm_s16le", "-map_metadata", "-1", clean])
        if not clean.exists():
            raise RuntimeError("ffmpeg n'a pas pu lire le fichier : " + r.stderr.decode("utf-8", "ignore")[-300:])

        # 2. Volume calé sur la VO (mesuré après la coupe des silences)
        gain = 0.0
        if match_wav and match_wav.exists():
            a, b = mean_volume(match_wav), mean_volume(clean)
            if a is not None and b is not None:
                gain = max(-20.0, min(20.0, a - b))

        # 3. Même fréquence et même nombre de canaux que l'original, puis encodage ADX chiffré
        pcm = Path(tmp) / "pcm.wav"
        r = _run([FFMPEG, "-y", "-hide_banner", "-i", clean,
                  "-af", f"volume={gain:.2f}dB,alimiter=limit=0.97",
                  "-ar", rate, "-ac", channels, "-c:a", "pcm_s16le", "-map_metadata", "-1", pcm])
        if not pcm.exists():
            raise RuntimeError("ffmpeg n'a pas pu convertir le fichier : " + r.stderr.decode("utf-8", "ignore")[-300:])
        r = _run([VGAUDIO, "-i", pcm, "-o", dst, "--keycode", P5R_KEYCODE])
        if not dst.exists():
            raise RuntimeError("VGAudio n'a pas pu encoder : " + r.stdout.decode("utf-8", "ignore")[-300:])
    return {"gain_db": round(gain, 1), "vf_duration": adx_duration(dst)}

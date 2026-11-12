"""Télécharge les outils audio au premier lancement (rien à faire s'ils sont déjà là).

- vgmstream : lecture des voix du jeu
- VGAudio   : encodage ADX chiffré pour P5R
(ffmpeg arrive avec le paquet Python imageio-ffmpeg.)
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"

DOWNLOADS = [
    ("vgmstream", "https://github.com/vgmstream/vgmstream/releases/latest/download/vgmstream-win64.zip",
     TOOLS / "vgmstream" / "vgmstream-cli.exe"),
    ("VGAudio", "https://github.com/Thealexbarney/VGAudio/releases/download/v2.2.1/VGAudioCli.zip",
     TOOLS / "vgaudio" / "net451_standalone" / "VGAudioCli.exe"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "P5R-Audio-Lab"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main() -> int:
    ok = True
    for name, url, check in DOWNLOADS:
        if check.exists():
            continue
        print(f"  Téléchargement de {name}...", flush=True)
        try:
            data = fetch(url)
            dest = check.parent if check.parent.name != "net451_standalone" else check.parent.parent
            dest.mkdir(parents=True, exist_ok=True)
            zipfile.ZipFile(io.BytesIO(data)).extractall(dest)
        except Exception as e:
            print(f"  Impossible de télécharger {name} : {e}", flush=True)
            ok = False
            continue
        if not check.exists():
            print(f"  {name} téléchargé mais introuvable à l'endroit attendu ({check}).", flush=True)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

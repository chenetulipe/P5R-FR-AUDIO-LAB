"""Tests de l'outil, de bout en bout, sur les vraies voix extraites du jeu.

Lancement : py -3 -m pytest tests -q
Ils utilisent un dossier de données temporaire et ne touchent ni au vrai mod, ni à Reloaded-II.
Il faut que les voix aient déjà été extraites une fois (dossier data/game/SOUND_E de l'outil).
"""
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOUND = ROOT / "data" / "game" / "SOUND_E"
if not (SOUND / "BP04.AWB").exists():
    pytest.skip("Voix du jeu non extraites : lance l'outil une fois avant les tests.", allow_module_level=True)

TMP = Path(tempfile.mkdtemp(prefix="p5r_tests_"))
os.environ["P5R_DATA"] = str(TMP / "data")
os.environ["P5R_NO_RELOADED"] = "1"
(TMP / "data").mkdir()
(TMP / "data" / "config.json").write_text(json.dumps({
    "sound_dir": str(SOUND), "mod_dir": str(TMP / "mod" / "p5rpc.vf.combat"), "game_dir": "",
}), "utf-8")
sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402

import app as appmod  # noqa: E402

client = TestClient(appmod.app)
BANK = "BP04"
MOD = TMP / "mod" / "p5rpc.vf.combat" / "FEmulator" / "AWB" / f"{BANK}.AWB"


def wav(seconds=1.0, rate=48000, silence=0.0, tone=True) -> bytes:
    """Petit WAV de test : silence, son, silence."""
    import math
    n_sil, n_tone = int(rate * silence), int(rate * seconds)
    frames = [0] * n_sil + [int(9000 * math.sin(2 * math.pi * 220 * i / rate)) if tone else 0 for i in range(n_tone)] + [0] * n_sil
    data = struct.pack(f"<{len(frames)}h", *frames)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def upload(index, content, name="prise.wav"):
    return client.post(f"/api/banks/{BANK}/clips/{index}/vf", files={"file": (name, content, "audio/wav")})


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    shutil.rmtree(TMP, ignore_errors=True)


# ---------- état et listes ----------

def test_state_and_whoami():
    st = client.get("/api/state").json()
    assert st["tools"] == {"vgmstream": True, "vgaudio": True, "ffmpeg": True}
    assert st["version"]
    assert client.get("/api/whoami").json()["root"] == str(ROOT)


def test_banks_list():
    banks = client.get("/api/banks").json()
    names = {b["bank"] for b in banks}
    assert {"BP01", "BP04", "SPT02"} <= names
    assert sum(b["count"] for b in banks) == 5245


def test_clips_have_names_and_durations():
    clips = client.get("/api/banks/BP01/clips").json()
    assert len(clips) == 410
    assert clips[3]["name"] == "Cue3001"
    assert all(c["duration"] > 0 for c in clips)


@pytest.mark.parametrize("bad", ["B..1", "BP01;rm", "BP 01"])
def test_bad_bank_names_rejected(bad):
    assert client.get(f"/api/banks/{bad}/clips").status_code in (400, 404)


def test_unknown_bank_is_404():
    assert client.get("/api/banks/BP99/clips").status_code == 404


# ---------- écoute ----------

def test_play_vo():
    r = client.get(f"/api/banks/{BANK}/clips/0/vo")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"


def test_play_vo_out_of_range_is_404():
    assert client.get(f"/api/banks/{BANK}/clips/99999/vo").status_code == 404


def test_play_vf_when_none_is_404():
    assert client.get(f"/api/banks/{BANK}/clips/1/vf").status_code == 404


# ---------- poser une VF ----------

def test_upload_trims_silence_and_matches_format():
    r = upload(5, wav(1.0, silence=0.8))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file"] == "5_streaming.adx"
    assert 0.9 < body["vf_duration"] < 1.3  # 2,6 s avec les silences -> ~1 s
    assert (MOD / "5_streaming.adx").exists()
    clip = client.get(f"/api/banks/{BANK}/clips").json()[5]
    assert clip["vf"] == "5_streaming.adx" and clip["vf_duration"] == body["vf_duration"]


def test_upload_replaces_previous_vf():
    upload(6, wav(0.5))
    upload(6, wav(0.7))
    assert [p.name for p in MOD.glob("6*.adx")] == ["6_streaming.adx"]


def test_upload_pure_silence_still_works():
    r = upload(7, wav(1.0, tone=False))
    assert r.status_code == 200, r.text


def test_upload_wrong_extension_rejected():
    r = upload(8, b"hello", name="notes.txt")
    assert r.status_code == 400


def test_upload_corrupt_audio_gives_clear_error():
    r = upload(8, b"RIFF" + os.urandom(2000), name="casse.wav")
    assert r.status_code in (400, 500)
    assert "detail" in r.json()
    assert not (MOD / "8_streaming.adx").exists()


def test_upload_out_of_range_is_404():
    assert upload(99999, wav(0.3)).status_code == 404


def test_upload_mp3():
    import tools
    src = TMP / "take.mp3"
    import subprocess
    subprocess.run([str(tools.FFMPEG), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=0.8", str(src)], check=True)
    r = client.post(f"/api/banks/{BANK}/clips/9/vf", files={"file": ("prise.mp3", src.read_bytes(), "audio/mpeg")})
    assert r.status_code == 200, r.text


def test_play_and_download_vf():
    assert client.get(f"/api/banks/{BANK}/clips/5/vf").status_code == 200
    r = client.get(f"/api/banks/{BANK}/clips/5/download?kind=vf")
    assert r.status_code == 200 and "_VF.wav" in r.headers["content-disposition"]
    r = client.get(f"/api/banks/{BANK}/clips/5/download")
    assert r.status_code == 200 and f"{BANK}_5_" in r.headers["content-disposition"]


# ---------- notes, validation ----------

def test_note_with_accents_is_saved():
    t = "Ça va être génial, « Panther » !"
    assert client.patch(f"/api/banks/{BANK}/clips/5", json={"text": t}).status_code == 200
    assert client.get(f"/api/banks/{BANK}/clips").json()[5]["text"] == t


def test_valid_flag_only_with_vf():
    client.patch(f"/api/banks/{BANK}/clips/5", json={"valid": True})
    client.patch(f"/api/banks/{BANK}/clips/10", json={"valid": True})  # pas de VF
    clips = client.get(f"/api/banks/{BANK}/clips").json()
    assert clips[5]["valid"] is True and clips[10]["valid"] is False


def test_bank_counts():
    b = next(x for x in client.get("/api/banks").json() if x["bank"] == BANK)
    assert b["done"] == len(list(MOD.glob("*.adx")))


# ---------- retirer / annuler ----------

def test_remove_and_restore():
    assert client.delete(f"/api/banks/{BANK}/clips/6/vf").status_code == 200
    assert not (MOD / "6_streaming.adx").exists()
    r = client.post(f"/api/banks/{BANK}/clips/6/restore")
    assert r.status_code == 200 and (MOD / "6_streaming.adx").exists()
    assert client.post(f"/api/banks/{BANK}/clips/6/restore").status_code == 404


def test_remove_resets_valid():
    client.delete(f"/api/banks/{BANK}/clips/5/vf")
    assert client.get(f"/api/banks/{BANK}/clips").json()[5]["valid"] is False
    client.post(f"/api/banks/{BANK}/clips/5/restore")


def test_restore_refused_if_new_vf_posed():
    client.delete(f"/api/banks/{BANK}/clips/7/vf")
    upload(7, wav(0.4))
    assert client.post(f"/api/banks/{BANK}/clips/7/restore").status_code == 409


def test_remove_when_nothing_is_ok():
    assert client.delete(f"/api/banks/{BANK}/clips/200/vf").status_code == 200


# ---------- import / export groupés ----------

def test_batch_without_folder_is_400():
    client.post("/api/config", json={"rec_dir": ""})
    assert client.post(f"/api/banks/{BANK}/batch").status_code == 400


def test_export_then_batch_import_roundtrip():
    r = client.get(f"/api/banks/{BANK}/export")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert f"{BANK}/liste_{BANK}.csv" in names
    wavs = [n for n in names if n.endswith(".wav")]
    assert len(wavs) == len(client.get(f"/api/banks/{BANK}/clips").json())
    rec = TMP / "rec"
    (rec / BANK).mkdir(parents=True)
    pick = next(n for n in wavs if n.split("/")[-1].startswith(f"{BANK}_20_"))
    (rec / pick.split("/")[-1]).write_bytes(z.read(pick))            # format d'export : BP04_20_Cue....wav
    (rec / BANK / "21.wav").write_bytes(wav(0.5))                      # rangé dans un sous-dossier
    (rec / "notes.txt").write_text("à ignorer")
    client.post("/api/config", json={"rec_dir": str(rec)})
    res = client.post(f"/api/banks/{BANK}/batch").json()
    assert sorted(x["index"] for x in res["imported"]) == [20, 21] and not res["errors"]


# ---------- réglages ----------

def test_rename_character():
    names = client.get("/api/state").json()["config"]["names"]
    client.post("/api/config", json={"names": {**names, BANK: "Ann"}})
    assert next(b for b in client.get("/api/banks").json() if b["bank"] == BANK)["name"] == "Ann"


def test_invalid_reloaded_dir_rejected():
    r = client.post("/api/config", json={"reloaded_dir": str(TMP)})
    assert r.status_code == 400
    assert client.get("/api/state").json()["config"].get("reloaded_dir", "") == ""


def test_extract_with_wrong_game_dir_is_404():
    assert client.post("/api/game/extract", json={"game_dir": str(TMP), "lang": "E"}).status_code == 404


def test_corrupt_config_is_recovered():
    cfg = appmod.CONFIG_FILE
    saved = cfg.read_text("utf-8")
    cfg.write_text("{ ceci n'est pas du json", "utf-8")
    assert client.get("/api/state").status_code == 200
    assert (cfg.parent / "config_illisible.json").exists()
    cfg.write_text(saved, "utf-8")


def test_update_check_never_crashes():
    r = client.get("/api/update")
    assert r.status_code == 200 and "current" in r.json()

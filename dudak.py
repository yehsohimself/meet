"""dudak.py - Dublajlı videoda dudakları yeni sese eşler (2026-10-23; sync.so bulut servisi, lipsync-2-pro).

Kullanıcı yerel MuseTalk denemesini beğenmedi (ağız bulanık); bulutu seçti: ÜCRETLİ (dakikası ~4-5 $) ve video Mac'ten çıkıp sync.so'ya gider.
Bu yüzden her çalıştırma kullanıcının sitede onayladığı bir iştir (pencere maliyeti ve gönderimi söyler); kendiliğinden ASLA çalışmaz.
Anahtar: Ayarlar → Video → "Dudak senkronu (sync.so)" (`sync_anahtar`, Anahtar Zinciri'nde; gizli.SIRLAR).

Akış: video (dublajlı mp4) + o videonun ses kanalı (m4a) → POST https://api.sync.so/v2/generate (multipart: video, audio, model, options)
→ GET /v2/generate/<id>?include=progress (10 sn'de bir) → outputUrl indirilir → <ad> [dudak senkronlu].mp4.
Kullanım: python dudak.py <video.mp4> --cikti <çıktı.mp4> [--model lipsync-2-pro]
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

KLASOR = Path(__file__).resolve().parent
API = "https://api.sync.so/v2"
MODEL = "lipsync-2-pro"
DAKIKA_UCRET = {"lipsync-2": 3.0, "lipsync-2-pro": 5.0}       # üst sınır (sync.so fiyat sayfası, 23 Ekim 2026: 2,40-3 / 4-5 $)
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def log(m):
    print(m, flush=True)


def anahtar():
    try:
        d = json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        d = {}
    try:
        import gizli
        d = gizli.birlestir(d)
    except Exception:  # noqa: BLE001
        pass
    return str(d.get("sync_anahtar") or "").strip()


def hazir():
    return bool(anahtar())


def sure(yol):
    r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(yol)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def maliyet(sn, model=MODEL):
    """Tahmini üst sınır, dolar."""
    return round(sn / 60 * DAKIKA_UCRET.get(model, 5.0), 2)


def senkronla(video, cikti, model=MODEL):
    k = anahtar()
    if not k:
        raise SystemExit("HATA: sync.so anahtarı yok; Ayarlar → Video → Dudak senkronu.")
    video = Path(video); cikti = Path(cikti)
    sn = sure(video)
    log(f"[1/4] Hazırlanıyor ({sn:.0f} sn, en çok ~{maliyet(sn, model)} $)")
    gecici = Path(tempfile.mkdtemp(prefix="dudak_"))
    ses = gecici / "ses.m4a"
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-vn", "-c:a", "aac", "-b:a", "192k", str(ses)], capture_output=True, text=True)
    if r.returncode != 0 or not ses.exists():
        raise SystemExit("HATA: Videonun sesi ayrılamadı.")
    log("[2/4] sync.so'ya gönderiliyor")
    with open(video, "rb") as fv, open(ses, "rb") as fa:
        y = requests.post(f"{API}/generate", headers={"x-api-key": k},
                          files={"video": (video.name, fv, "video/mp4"), "audio": ("ses.m4a", fa, "audio/mp4")},
                          data={"model": model, "options": json.dumps({"sync_mode": "cut_off"})}, timeout=600)
    if y.status_code >= 400:
        try:
            j = y.json()
        except ValueError:
            j = {}
        raise SystemExit(f"HATA: sync.so kabul etmedi ({y.status_code}): {j.get('message') or j.get('error') or y.text[:200]}")
    gid = y.json().get("id")
    log(f"      İş numarası {gid}")
    log("[3/4] Dudaklar eşleniyor")
    t0 = time.time(); son = ""
    while True:
        g = requests.get(f"{API}/generate/{gid}", headers={"x-api-key": k}, params={"include": "progress"}, timeout=60)
        j = g.json() if g.ok else {}
        durum = j.get("status") or ""
        yuzde = j.get("progress_percent")
        if yuzde is not None:
            log(f"      ilerleme {int(yuzde)}%")
        elif durum != son:
            log(f"      {durum.lower()}")
        son = durum
        if durum == "COMPLETED" and j.get("outputUrl"):
            break
        if durum in ("FAILED", "REJECTED"):
            raise SystemExit(f"HATA: sync.so işi tamamlayamadı: {j.get('error') or j.get('errorCode') or durum}")
        if time.time() - t0 > 3 * 3600:
            raise SystemExit("HATA: sync.so 3 saatte bitirmedi.")
        time.sleep(10)
    log("[4/4] İndiriliyor")
    with requests.get(j["outputUrl"], stream=True, timeout=600) as d, open(cikti, "wb") as f:
        d.raise_for_status()
        for parca in d.iter_content(1 << 20):
            f.write(parca)
    log(f"Bitti. Dosya: {cikti} (süre {j.get('outputDuration') or sn:.0f} sn)")
    return cikti


if __name__ == "__main__":
    a = sys.argv[1:]
    v = a[0]; c = None; m = MODEL
    if "--cikti" in a:
        c = a[a.index("--cikti") + 1]
    if "--model" in a:
        m = a[a.index("--model") + 1]
    if not c:
        c = str(Path(v).with_name(Path(v).stem + " [dudak senkronlu].mp4"))
    senkronla(v, c, m)

"""temizle.py - Konuşma sesini temizler: gürültü bastırma (RNNoise, ffmpeg arnndn) + spektral gürültü azaltma + ses dengeleme.

Ek kurulum yok: ffmpeg'in içindeki filtreler ve modeller/rnnoise_sh.rnnn (RNNoise "somnolent hogwash" modeli, ~300 KB).
Kullanım: temizle(girdi, cikti, seviye="orta") → çıktı yolu (m4a/wav). seviye: hafif | orta | guclu
ffmpeg filtre zinciri: filtre_zinciri(seviye) (yakma.py bunu doğrudan -af olarak kullanır).
Elle: python temizle.py girdi.m4a cikti.m4a [hafif|orta|guclu]
"""
import subprocess
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"
RNNOISE = KLASOR / "modeller" / "rnnoise_sh.rnnn"


def filtre_zinciri(seviye="orta"):
    mix = {"hafif": 0.6, "orta": 0.85, "guclu": 1.0}.get(seviye, 0.85)
    nr = {"hafif": 6, "orta": 10, "guclu": 16}.get(seviye, 10)
    parcalar = []
    if RNNOISE.exists():
        parcalar.append(f"arnndn=m='{RNNOISE}':mix={mix}")
    parcalar.append(f"afftdn=nf=-25:nr={nr}:tn=1")
    parcalar.append("speechnorm=e=6:r=0.0001:l=1")          # konuşma seviyesini dengele (yumuşak)
    return ",".join(parcalar)


def temizle(girdi, cikti, seviye="orta", log=print):
    girdi, cikti = Path(girdi), Path(cikti)
    kodek = ["-c:a", "aac", "-b:a", "160k"] if cikti.suffix.lower() in (".m4a", ".mp4", ".aac") else ["-c:a", "pcm_s16le"]
    komut = [FFMPEG, "-y", "-v", "error", "-i", str(girdi), "-af", filtre_zinciri(seviye), "-ar", "48000"] + kodek + [str(cikti)]
    r = subprocess.run(komut, capture_output=True, text=True)
    if r.returncode != 0 or not cikti.exists():
        raise RuntimeError("ffmpeg ses temizleme başarısız: " + (r.stderr.strip()[-300:] or "bilinmeyen hata"))
    log(f"      Ses temizlendi ({seviye})")
    return cikti


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(1)
    print(temizle(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "orta"))

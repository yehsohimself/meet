"""sesnot.py - Kısa sesli notu yazıya döker (Ghost: fikir, günün sorusuna cevap, maç tepkisi). Ayrı süreçte çalışır ki site belleğine ses modeli
yüklenmesin. Kullanım: python sesnot.py <ses dosyası> [dil]  → stdout'a JSON {"metin": "...", "sure": sn}. Yalnızca kullanıcının KENDİ sesi için
(Almanya §201 StGB: başkalarının konuşmasını izinsiz kaydetmek suç; bu giriş sürekli kayıt yapmaz, kullanıcı düğmeye basar).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def yaziya_dok(yol, dil="tr"):
    import mlx_whisper
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "s.wav"
        subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-loglevel", "error", "-i", str(yol), "-ac", "1", "-ar", "16000", str(wav)], check=True)
        sure = float(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                                    capture_output=True, text=True).stdout.strip() or 0)
        r = mlx_whisper.transcribe(str(wav), path_or_hf_repo="mlx-community/whisper-large-v3-turbo", language=dil or None,
                                   condition_on_previous_text=False, temperature=(0.0, 0.2, 0.4))
    metin = " ".join(s.get("text", "").strip() for s in r.get("segments") or []).strip()
    return {"metin": metin, "sure": round(sure, 1)}


if __name__ == "__main__":
    print(json.dumps(yaziya_dok(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "tr"), ensure_ascii=False))

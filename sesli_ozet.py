"""sesli_ozet.py - Toplantının sesli özeti (2026-10-22; kullanıcının Transcript tanıtımındaki "toplantı notlarını sesli ve yazılı özetliyor").
Kısaca kartının özeti + kullanıcının işleri, macOS'in kendi Türkçe sesiyle (Yelda; kurulum yok, bilgisayarda kalır) okunur → `<temel>.ozet.m4a`.
"""
import json
import subprocess
import tempfile
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
SES = "Yelda"


def metin(veri):
    k = veri.get("kisaca") or {}
    konu = str(veri.get("baslik") or "").split(" · ")
    bas = (konu[1] if len(konu) > 1 else konu[0]) if konu else "Toplantı"
    parca = [f"{bas}."] + [str(p) for p in k.get("ozet") or []]
    try:
        import gorevler
        isler = gorevler.benim_isler(veri)
    except Exception:  # noqa: BLE001
        isler = []
    if isler:
        parca.append("Sizin işleriniz: " + "; ".join(i["is"] + (f", {i['ne_zaman']}" if i.get("ne_zaman") else "") for i in isler[:6]) + ".")
    return "\n\n".join(parca).replace("·", ",")


def uret(temel, veri=None):
    """`<temel>.ozet.m4a` yazar. Döner: (dosya yolu, saniye) ya da (None, 0)."""
    if veri is None:
        veri = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"]
    m = metin(veri)
    if len(m) < 40:
        return None, 0
    hedef = KLASOR / f"{temel}.ozet.m4a"
    with tempfile.TemporaryDirectory() as t:
        txt, aiff = Path(t) / "o.txt", Path(t) / "o.aiff"
        txt.write_text(m, encoding="utf-8")
        subprocess.run(["say", "-v", SES, "-r", "185", "-f", str(txt), "-o", str(aiff)], check=True, timeout=300)
        subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-c:a", "aac", "-b:a", "96k", str(hedef)], check=True, timeout=300)
    sn = float(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(hedef)],
                              capture_output=True, text=True).stdout.strip() or 0)
    return hedef, round(sn)


if __name__ == "__main__":
    import sys
    print(uret(Path(sys.argv[1]).stem))

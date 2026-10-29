#!/usr/bin/env python3
"""
goruntu.py - Videodan sahne kareleri çıkarır, ekrandaki yazıları okur (macOS yazı tanıma),
seçili kareleri bilgisayardaki görüntü modeliyle betimler. Dışarı veri gitmez.

Kullanım (tek başına): python goruntu.py video.mp4 cikti_klasoru
"""
import base64
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
MODEL = os.environ.get("GORUNTU_MODEL", "gemma3:4b")
EN_COK_KARE = 40            # çıkarılacak en çok sahne karesi
EN_COK_BETIM = 12           # modelle betimlenecek en çok kare (kare başına ~40 sn)


def _ffmpeg():
    for aday in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"):
        if Path(aday).exists() or aday == "ffmpeg":
            return aday
    return "ffmpeg"


def kareleri_cikar(video, klasor, sure=0.0, log=print):
    """Sahne değişimlerinde (en az 10 sn, en çok 60 sn aralıkla) 640px kareler çıkarır.
    Döner: [(saniye, dosya_yolu)]"""
    klasor = Path(klasor); klasor.mkdir(parents=True, exist_ok=True)
    for f in klasor.glob("k_*.jpg"):
        f.unlink()
    en_az = max(10.0, (sure or 0) / EN_COK_KARE)          # uzun videoda kareler seyrekleşir
    secim = f"gt(scene,0.3)*gte(t-prev_selected_t,{en_az:.1f})+isnan(prev_selected_t)+gte(t-prev_selected_t,60)"
    komut = [_ffmpeg(), "-hide_banner", "-loglevel", "info", "-i", str(video),
             "-vf", f"select='{secim}',scale=640:-2,showinfo", "-fps_mode", "vfr", "-q:v", "4",
             str(klasor / "k_%04d.jpg")]
    p = subprocess.run(komut, capture_output=True, text=True)
    zamanlar = [float(z) for z in re.findall(r"pts_time:([0-9.]+)", p.stderr)]
    dosyalar = sorted(klasor.glob("k_*.jpg"))
    kareler = [(z, str(d)) for z, d in zip(zamanlar, dosyalar)]
    if len(kareler) > EN_COK_KARE:                           # yine de fazlaysa eşit seyrelt
        adim = len(kareler) / EN_COK_KARE
        kareler = [kareler[int(i * adim)] for i in range(EN_COK_KARE)]
    log(f"      {len(kareler)} sahne karesi çıkarıldı.")
    return kareler


_ocr_hazir = None


def yazi_oku(yol):
    """macOS yazı tanıma ile karedeki yazıları okur. Döner: [satır, ...]"""
    global _ocr_hazir
    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except Exception:  # noqa: BLE001
        return []
    url = NSURL.fileURLWithPath_(str(yol))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return []
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(["tr-TR", "en-US"])
    req.setUsesLanguageCorrection_(True)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    h.performRequests_error_([req], None)
    out = []
    for o in (req.results() or []):
        c = o.topCandidates_(1)
        if c and c[0].confidence() > 0.45:
            t = c[0].string().strip()
            if len(t) >= 2 and not re.fullmatch(r"[\W\d_]+", t):
                out.append(t)
    return out


def model_hazir(model=MODEL):
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
            adlar = [m.get("name", "") for m in json.load(r).get("models", [])]
        return any(a == model or a.split(":")[0] == model.split(":")[0] for a in adlar)
    except Exception:  # noqa: BLE001
        return False


def betimle(yol, dil="tr", yazilar=None):
    """Kareyi 1-2 cümleyle betimler (görüntü modeli)."""
    dil_adi = {"tr": "Türkçe", "en": "İngilizce"}.get(dil, "Türkçe")
    istem = (f"Bu bir videodan alınmış tek bir kare. {dil_adi} olarak, 1-2 kısa cümleyle, nesnel biçimde ne görüldüğünü yaz: "
             "ortam, nesneler, eylem, kadraj (yakın plan / geniş plan). Kişileri tanımaya çalışma, yalnızca betimle "
             "(ör. 'gri gömlekli bir adam'). Yorum, tahmin ve övgü ekleme. Ekrandaki yazıları tekrar yazma. "
             "Düz metin yaz: başlık, madde işareti, kalın yazı kullanma.")
    img = base64.b64encode(open(yol, "rb").read()).decode()
    govde = {"model": MODEL, "prompt": istem, "images": [img], "stream": False,
             "options": {"temperature": 0.1, "num_predict": 110}}
    req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(govde).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return temizle(json.load(r).get("response", ""))


def temizle(metin):
    """Modelin bazen döndürdüğü başlık/madde/kalın biçimlerini düz, tek paragraf metne çevirir."""
    metin = re.sub(r"\*\*|__|^#+\s*", "", metin, flags=re.M)
    metin = re.sub(r"^\s*(işte betimleme|betimleme|açıklama)\s*:\s*", "", metin, flags=re.I)
    satirlar = []
    for sat in metin.splitlines():
        sat = re.sub(r"^\s*[-*•\d.)]+\s*", "", sat).strip()
        sat = re.sub(r"^(ortam|nesneler|eylem|kadraj|kişiler|yazılar?)\s*:\s*", "", sat, flags=re.I)
        sat = re.sub(r"\b(ekran üzerindeki yazı|ekrandaki yazı(lar)?|ekran yazısı|süper)\s*:\s*\.?\s*$", "", sat, flags=re.I).strip()
        if sat:
            satirlar.append(sat if sat[-1] in ".!?…" else sat + ".")
    return re.sub(r"\s+", " ", " ".join(satirlar)).strip()[:400]


def _claude_betimle(notlar, klasor, dil, log):
    """Claude ile TÜM kareler (20'lik gruplar, tek istekte); başarılıysa True."""
    try:
        import claude_yaz
        if not claude_yaz.hazir():
            return False
    except Exception:  # noqa: BLE001
        return False
    dil_adi = {"tr": "Türkçe", "en": "İngilizce"}.get(dil, "Türkçe")
    tamam = 0
    for g in range(0, len(notlar), 20):
        grup = notlar[g:g + 20]
        log(f"      Görüntü: {g + 1}-{g + len(grup)}. kareler Claude ile betimleniyor...")
        istem = (f"Bunlar bir videodan sırayla alınmış {len(grup)} kare. Her kare için {dil_adi} olarak 1-2 kısa cümleyle, nesnel biçimde ne "
                 "görüldüğünü yaz: ortam, kişiler (tanımaya çalışmadan, ör. 'gri gömlekli bir adam'), eylem, kadraj (yakın/geniş plan, grafik, "
                 "ekran kaydı). Ekrandaki yazıları tekrar yazma; yorum ve övgü ekleme. Biçim: {\"1\": \"...\", \"2\": \"...\"} "
                 f"(1'den {len(grup)}'e kadar hepsi).")
        try:
            c = claude_yaz.json_coz(claude_yaz.sor_gorsel(istem, [Path(klasor) / n["kare"] for n in grup],
                                                          "Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun."))
        except Exception as e:  # noqa: BLE001
            log(f"      Claude kareleri betimleyemedi ({str(e)[:80]})"); return tamam > 0
        for i, n in enumerate(grup, 1):
            if isinstance(c.get(str(i)), str) and c[str(i)].strip():
                n["aciklama"] = temizle(c[str(i)]); tamam += 1
    return tamam > 0


def incele(video, klasor, sure=0.0, dil="tr", betim=True, log=print):
    """Tam görüntü incelemesi. Döner: [{"sn","kare","yazi":[...],"aciklama":str}]"""
    kareler = kareleri_cikar(video, klasor, sure, log=log)
    if not kareler:
        return []
    notlar = []
    for sn, yol in kareler:
        notlar.append({"sn": round(sn, 1), "kare": Path(yol).name, "yazi": yazi_oku(yol), "aciklama": ""})
    okunan = sum(1 for n in notlar if n["yazi"])
    log(f"      Ekran yazısı okunan kare: {okunan}/{len(notlar)}")
    if betim and _claude_betimle(notlar, klasor, dil, log):
        pass
    elif betim and model_hazir():
        secilen = list(range(len(notlar)))
        if len(secilen) > EN_COK_BETIM:
            adim = len(secilen) / EN_COK_BETIM
            secilen = [int(i * adim) for i in range(EN_COK_BETIM)]
        for i, idx in enumerate(secilen, 1):
            n = notlar[idx]
            log(f"      Görüntü: kare {i}/{len(secilen)} betimleniyor...")
            try:
                n["aciklama"] = betimle(Path(klasor) / n["kare"], dil, n["yazi"])
            except Exception as e:  # noqa: BLE001
                log(f"      Kare betimlenemedi: {e}")
    elif betim:
        log("      Görüntü modeli hazır değil; yalnızca ekran yazıları okundu.")
    return notlar


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(1)
    for n in incele(sys.argv[1], sys.argv[2]):
        print(n)

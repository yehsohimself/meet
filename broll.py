"""broll.py - Bağlamsal B-roll: klipteki konuşmaya uygun kısa stok görüntüler (Pexels, ücretsiz API anahtarı).

Ayarlar → "Pexels anahtarı" (ayarlar.json "pexels_anahtar"; https://www.pexels.com/api/ adresinden ücretsiz alınır).
plan(cueler, sure, dikey, log) → [{"bas", "sure", "dosya", "anahtar"}]: her ~15 sn'de bir, cümle başında 3-4 sn'lik
kesme görüntü; anahtar kelimeyi gemma3 seçer (somut, görselleştirilebilir, İngilizce arama terimi). Dosyalar
indirilenler/.broll/ altına iner (yeniden kullanılır). Anahtar yoksa boş liste döner.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
BROLL = KLASOR / "indirilenler" / ".broll"
ARALIK = 15.0          # kaç saniyede bir b-roll
SURE = 3.5             # b-roll uzunluğu
ILK = 4.0              # ilk b-roll en erken


def _anahtar():
    try:
        import gizli
        return gizli.birlestir(json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8"))).get("pexels_anahtar") or ""
    except Exception:  # noqa: BLE001
        return ""


def _terimler(cumleler, log):
    """Her cümle için 1-3 kelimelik İngilizce görsel arama terimi (gemma3). Dönüş: [terim|''] aynı sırayla."""
    import ozet as ozet_modulu
    if not ozet_modulu.hazir() or not cumleler:
        return [""] * len(cumleler)
    satirlar = "\n".join(f"[{i}] {c}" for i, c in enumerate(cumleler))
    istem = ("Aşağıdaki Türkçe cümlelerin her biri için, stok video aramasında kullanılacak 1-3 kelimelik İNGİLİZCE, somut ve "
             "görselleştirilebilir bir arama terimi ver (ör. 'city traffic', 'laptop typing', 'coffee meeting'). Soyut ya da "
             "görselleştirilemeyen cümlelere boş string ver. Yalnızca JSON: {\"terimler\": {\"0\": \"...\", \"1\": \"\"}}\n\n" + satirlar)
    try:
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=8192, zaman_asimi=180)) or {}
        t = c.get("terimler") or {}
        return [str(t.get(str(i)) or "").strip()[:40] for i in range(len(cumleler))]
    except Exception as e:  # noqa: BLE001
        log(f"      B-roll terimleri alınamadı ({e})"); return [""] * len(cumleler)


def _pexels_ara(terim, dikey, anahtar):
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": terim, "per_page": 5, "orientation": "portrait" if dikey else "landscape", "size": "medium"})
    req = urllib.request.Request(url, headers={"Authorization": anahtar, "User-Agent": "Transkript/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("videos") or []


def _indir(video, hedef):
    dosyalar = [f for f in video.get("video_files") or [] if f.get("file_type") == "video/mp4" and (f.get("height") or 0) <= 1080]
    if not dosyalar:
        return None
    dosyalar.sort(key=lambda f: -(f.get("height") or 0))
    link = dosyalar[0]["link"]
    req = urllib.request.Request(link, headers={"User-Agent": "Transkript/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(hedef, "wb") as f:
        while True:
            parca = r.read(1 << 20)
            if not parca:
                break
            f.write(parca)
    return hedef if hedef.exists() and hedef.stat().st_size > 50_000 else None


def plan(cueler, sure, dikey=False, log=print):
    """cueler: [{"bas","bit","metin"}] (klip zamanına göre). Döner: [{"bas","sure","dosya","anahtar"}]"""
    anahtar = _anahtar()
    if not anahtar or not cueler:
        return []
    BROLL.mkdir(parents=True, exist_ok=True)
    # Her ARALIK penceresinde bir cümle başı seç
    adaylar, son = [], -ARALIK
    for c in cueler:
        if c["bas"] >= ILK and c["bas"] - son >= ARALIK and c["bas"] + SURE <= sure - 1.0:
            adaylar.append(c); son = c["bas"]
    if not adaylar:
        return []
    terimler = _terimler([a["metin"] for a in adaylar], log)
    sonuc, kullanilan = [], set()
    for a, terim in zip(adaylar, terimler):
        if not terim or terim.lower() in kullanilan:
            continue
        try:
            videolar = _pexels_ara(terim, dikey, anahtar)
        except Exception as e:  # noqa: BLE001
            log(f"      Pexels araması başarısız ({terim}: {e})"); continue
        for v in videolar[:3]:
            hedef = BROLL / f"pexels_{v.get('id')}_{'d' if dikey else 'y'}.mp4"
            if not hedef.exists():
                try:
                    if not _indir(v, hedef):
                        continue
                except Exception:  # noqa: BLE001
                    continue
            sonuc.append({"bas": round(a["bas"], 2), "sure": SURE, "dosya": str(hedef), "anahtar": terim, "kaynak": v.get("url", "")})
            kullanilan.add(terim.lower()); break
        time.sleep(0.3)
    log(f"      B-roll: {len(sonuc)} kesme görüntü ({', '.join(s['anahtar'] for s in sonuc)})")
    return sonuc


def filtre_ekle(komut_girdileri, filtre_zinciri_sonu, brolls, w, h):
    """ffmpeg komutuna b-roll girdilerini ve overlay filtrelerini ekler. Döner: (ek girdi argümanları, filtre parçası, son etiket).
    filtre_zinciri_sonu: üzerine bindirilecek akışın etiketi (ör. '[v]'). Son etiket yeni akış."""
    ek, filtre, giris_no, cur = [], "", komut_girdileri, filtre_zinciri_sonu
    for i, b in enumerate(brolls):
        ek += ["-ss", "0", "-t", f"{b['sure'] + 0.2:.2f}", "-i", b["dosya"]]
        et = f"[br{i}]"; out = f"[bo{i}]"
        filtre += (f"[{giris_no}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
                   f"setpts=PTS-STARTPTS+{b['bas']:.3f}/TB{et};{cur}{et}overlay=0:0:enable='between(t,{b['bas']:.3f},{b['bas'] + b['sure']:.3f})':eof_action=pass{out};")
        cur = out; giris_no += 1
    return ek, filtre, cur

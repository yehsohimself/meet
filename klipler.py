#!/usr/bin/env python3
"""
klipler.py - Öne çıkan anlar: yerel modele transkripti verir, sosyal medyada tek başına işe yarayacak 3-5 kısa
bölüm (15-60 sn) seçtirir; sınırlar cümle (segment) başı/sonuna oturtulur.

Kullanım: python klipler.py transkript_x.json   → JSON'a veri["klipler"] yazar
"""
import json
import re
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
from ozet import _json_coz, _sor, _parcala  # noqa: E402

EN_AZ, EN_COK = 12.0, 75.0


def _zaman(sn):
    import ortak                                           # tek sürüm: bir saatin üstünde h:mm:ss (2026-10-25)
    return ortak.zaman(sn)


def _sn(z):
    m = re.search(r"(?:(\d+):)?(\d{1,2}):(\d{2})", str(z))
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def _oturt(bas, bit, segmentler):
    """Başlangıcı bas'tan önceki en yakın cümle başına, bitişi bit'ten sonraki en yakın cümle sonuna çeker."""
    b = max([s["bas"] for s in segmentler if s["bas"] <= bas + 0.5] or [bas])
    e = min([s["bit"] for s in segmentler if s["bit"] >= bit - 0.5] or [bit])
    if e - b > EN_COK:
        e = min([s["bit"] for s in segmentler if s["bit"] >= b + EN_AZ and s["bit"] <= b + EN_COK] or [b + 60])
    return round(b, 2), round(e, 2)


# 2026-10-23 (ChatGPT brifi, Studio 3): kesit tek başına anlaşılmalı; önceki konuşmaya yaslanan açılış ya da yarım kalan kapanış denetlenir.
BOSTA_BAS = re.compile(r"^\W*(bu|bunu|bunun|buna|bunlar\w*|o|onu|onun|ona|onlar\w*|şu|şunu|şunlar\w*|orada|burada|oraya|işte|ve|ama|fakat|ancak|çünkü|yani|zaten|"
                       r"dediğim gibi|az önce|demin|biraz önce|aynen|evet|hayır|tabii|o yüzden|bu yüzden|bu arada|bir de|this|that|these|those|it|so|and|but|"
                       r"because|which|they|he|she|also)\b", re.I)
BOSTA_SON = re.compile(r"\b(ve|ama|fakat|çünkü|yani|ki|ile|gibi|için|da|de|and|but|because|so|the|a|to|of)\W*$", re.I)


def _yasli(t):
    """Açılış önceki konuşmaya yaslanıyor mu: göndermeli söz ya da küçük harfle (cümle ortasından) başlama."""
    t = str(t or "").strip()
    return bool(BOSTA_BAS.search(t)) or bool(re.match(r"^[a-zçğıöşü]", t))


def _kesit_metni(b, e, seg):
    return [s for s in seg if s["bit"] > b + 0.2 and s["bas"] < e - 0.2]


def denetle(k, seg):
    """Kesiti tek başına anlaşılırlık için denetler: açılış önceki konuşmaya yaslanıyorsa başlangıç (en çok 2 cümle) geri çekilir, kapanış yarım kalıyorsa
    bitiş (en çok 2 cümle) uzatılır; düzelmezse 'uyari'. Yerinde günceller; döner: klip."""
    notlar = []
    for _ in range(2):
        ilk = _kesit_metni(k["bas"], k["bit"], seg)
        if not ilk or not _yasli(ilk[0]["metin"]):
            break
        once = [s for s in seg if s["bit"] <= ilk[0]["bas"] + 0.2]
        if not once or k["bit"] - once[-1]["bas"] > EN_COK:
            break
        k["bas"] = round(once[-1]["bas"], 2); notlar.append("başlangıç önceki cümleye çekildi")
    for _ in range(2):
        son = _kesit_metni(k["bas"], k["bit"], seg)
        t = son[-1]["metin"].strip() if son else ""
        if not son or (re.search(r"[.!?…]['\"”’)]*$", t) and not BOSTA_SON.search(t)):
            break
        sonra = [s for s in seg if s["bas"] >= son[-1]["bit"] - 0.2]
        if not sonra or sonra[0]["bit"] - k["bas"] > EN_COK:
            break
        k["bit"] = round(sonra[0]["bit"], 2); notlar.append("bitiş sonraki cümleye uzatıldı")
    ilk = _kesit_metni(k["bas"], k["bit"], seg)
    uyari = []
    if ilk and _yasli(ilk[0]["metin"]):
        m = BOSTA_BAS.search(ilk[0]["metin"].strip())
        uyari.append(f"'{m.group(1)}' ile başlıyor; öncesi olmadan anlaşılmayabilir" if m else "cümlenin ortasından başlıyor olabilir")
    if ilk:
        t = ilk[-1]["metin"].strip()
        if not re.search(r"[.!?…]['\"”’)]*$", t) or BOSTA_SON.search(t):
            uyari.append("cümle ortasında bitiyor olabilir")
    k["duzeltme"] = notlar; k["uyari"] = uyari
    k["ilk_soz"] = (ilk[0]["metin"].strip()[:90] if ilk else ""); k["son_soz"] = (ilk[-1]["metin"].strip()[-90:] if ilk else "")
    return k


def sec(json_yolu, log=print, en_cok=5):
    d = json.loads(Path(json_yolu).read_text(encoding="utf-8"))
    veri, seg = d["veri"], d["segmentler"]
    if not seg:
        return []
    from transkript import paragrafla
    paragraflar = paragrafla(seg, veri["etiket"])
    satirlar = [f"[{_zaman(p['bas'])}-{_zaman(p['bit'])}] {p['ad']}: {p['metin']}" for p in paragraflar]
    parcalar = _parcala(satirlar)
    kural = ("Sosyal medyada (Reels, TikTok, Shorts) tek başına izlenebilecek, merak uyandıran ya da net bir bilgi/fikir veren "
             "anları seç. Her an 15-60 saniye olsun, bir cümlenin başında başlasın ve bir cümlenin sonunda bitsin; "
             "bağlam gerektiren yarım konuşmaları seçme. 'bas' ve 'bit' alanları satır başındaki köşeli parantez zamanlarından "
             "alınsın (mm:ss). 'baslik' 3-6 kelimelik çarpıcı ama abartısız bir başlık, 'neden' tek cümle, 'puan' 1-10 arası "
             "paylaşılabilirlik puanı, 'sinir' tek cümle: neden tam orada başlayıp orada bittiği (ör. 'soru burada soruluyor, cevap burada tamamlanıyor'). "
             "'bu', 'o', 'az önce', 'dediğim gibi' gibi öncesine yaslanan bir sözle BAŞLAYAN kesit seçme. Metinde olmayan bir şey uydurma.")
    adaylar = []
    for i, parca in enumerate(parcalar, 1):
        if len(parcalar) > 1:
            log(f"      Öne çıkanlar: parça {i}/{len(parcalar)}")
        istem = (f"Aşağıda bir videonun zaman damgalı transkripti{' (' + str(i) + '. parça)' if len(parcalar) > 1 else ''} var. {kural}\n"
                 f"En iyi {2 if len(parcalar) > 1 else en_cok} anı seç. Şu JSON yapısında yanıt ver: "
                 '{"klipler": [{"bas": "mm:ss", "bit": "mm:ss", "baslik": "...", "neden": "...", "sinir": "...", "puan": 8}]}\n\nTRANSKRİPT:\n' + "\n".join(parca))
        c = _json_coz(_sor(istem, json_bekle=True, num_ctx=16384))
        for k in c.get("klipler") or []:
            if not isinstance(k, dict):
                continue
            b, e = _sn(k.get("bas")), _sn(k.get("bit"))
            if b is None or e is None or e <= b:
                continue
            try:
                puan = float(k.get("puan") or 5)
            except (TypeError, ValueError):
                puan = 5.0
            adaylar.append({"bas": b, "bit": e, "baslik": str(k.get("baslik") or "").strip()[:80], "neden": str(k.get("neden") or "").strip()[:200], "puan": puan,
                            "sinir": str(k.get("sinir") or "").strip()[:200]})
    adaylar.sort(key=lambda k: -k["puan"])
    secilen = []
    for k in adaylar:
        b, e = _oturt(k["bas"], k["bit"], seg)
        if e - b < EN_AZ:
            continue
        if any(not (e <= s["bas"] or b >= s["bit"]) for s in secilen):      # çakışan anları atla
            continue
        aday = denetle({"bas": b, "bit": e, "baslik": k["baslik"] or f"{_zaman(b)}", "neden": k["neden"], "puan": k["puan"], "sinir": k.get("sinir", "")}, seg)
        if any(not (aday["bit"] <= s["bas"] or aday["bas"] >= s["bit"]) for s in secilen):
            continue
        secilen.append(aday)
        if len(secilen) >= en_cok:
            break
    secilen.sort(key=lambda k: k["bas"])
    try:
        paketle(secilen, seg, log)
    except Exception as e:  # noqa: BLE001
        log(f"      Klip paketi üretilemedi ({e})")
    veri["klipler"] = secilen
    with open(json_yolu, "w", encoding="utf-8") as f:
        json.dump({"veri": veri, "segmentler": seg}, f, ensure_ascii=False, indent=1)
    log(f"      {len(secilen)} öne çıkan an seçildi")
    return secilen


def paketle(klipler, seg, log=print):
    """Her klip için paylaşım paketi: kanca (kısa başlık), aciklama (1-2 cümle), etiketler (5 hashtag). Yerinde doldurur."""
    if not klipler:
        return
    parcalar = []
    for i, k in enumerate(klipler):
        metin = " ".join(s["metin"] for s in seg if s["bit"] > k["bas"] and s["bas"] < k["bit"])[:1500]
        parcalar.append(f"[{i}] ({_zaman(k['bas'])}-{_zaman(k['bit'])}) {metin}")
    istem = ("Aşağıda kısa video kliplerinin konuşma metinleri var. Her klip için Reels/TikTok/Shorts paylaşımına hazır paket üret, Türkçe:\n"
             "- kanca: en çok 60 karakter, merak uyandıran ama metinde geçen bir şeye dayanan başlık (tıklama tuzağı değil, abartı yok)\n"
             "- aciklama: 1-2 cümle, klipte ne olduğunu söyleyen açıklama\n- etiketler: 5 adet hashtag, Türkçe/İngilizce karışık olabilir, # ile\n"
             "Metinde olmayan bir şey uydurma. Yalnızca JSON: {\"paketler\": [{\"i\": 0, \"kanca\": \"...\", \"aciklama\": \"...\", \"etiketler\": [\"#...\"]}]}\n\n"
             + "\n\n".join(parcalar))
    c = _json_coz(_sor(istem, json_bekle=True, num_ctx=16384)) or {}
    for p in c.get("paketler") or []:
        try:
            i = int(p.get("i"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(klipler):
            klipler[i]["kanca"] = str(p.get("kanca") or "").strip()[:80]
            klipler[i]["aciklama"] = str(p.get("aciklama") or "").strip()[:300]
            etk, gorulen = [], set()
            for e in (p.get("etiketler") or []):
                e = "#" + str(e).strip().lstrip("#").replace(" ", "")
                if 2 <= len(e) <= 26 and e.lower() not in gorulen:
                    gorulen.add(e.lower()); etk.append(e)
            klipler[i]["etiketler"] = etk[:6]
    log("      Klip paketleri hazır (kanca, açıklama, etiketler)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    for k in sec(sys.argv[1]):
        print(f"{_zaman(k['bas'])}-{_zaman(k['bit'])}  {k['baslik']}  ({k['puan']})  {k['neden']}")

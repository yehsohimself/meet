"""sozler.py - Söz takibi (2026-10-21). Toplantılarda kullanıcının üstlendiği işler (Kısaca kartının "Kim ne yapacak" listesinden) tek listede:
"pazartesi", "hafta içinde", "yarın" gibi ifadeler toplantının tarihine göre gerçek güne çevrilir; geciken / bugün / yakında / tarihsiz diye
sıralanır. Başkalarının üstlendiği işler ayrıca "beklediklerin" olarak döner (takip için). İşaretleme `veri["kisaca"]` üzerinden
(site `POST /api/kisaca/<temel>/is`). Hatırlatma: site her sabah 09.00'dan sonra bir kez bildirim gönderir (`hatirlatma_metni`).
"""
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
GUNLER = {"pazartesi": 0, "salı": 1, "sali": 1, "çarşamba": 2, "carsamba": 2, "perşembe": 3, "persembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}


def _k(s):
    return str(s or "").replace("İ", "i").replace("I", "ı").lower()


def son_tarih(ifade, toplanti_gunu):
    """'pazartesi', 'bugün', 'yarın', 'hafta içinde', 'cuma', '19 Ekim', 'ay sonu' → date ya da None (anlaşılmazsa)."""
    t = _k(ifade).strip()
    if not t:
        return None
    g = toplanti_gunu
    if "bugün" in t or "bu akşam" in t or "hemen" in t or "toplantıdan sonra" in t:
        return g
    if "yarın" in t:
        return g + timedelta(days=1)
    m = re.search(r"(\d{1,2})\s*(" + "|".join(AYLAR) + r")", t)
    if m:
        y = g.year
        try:
            d = date(y, AYLAR[m.group(2)], int(m.group(1)))
            return d if d >= g - timedelta(days=30) else date(y + 1, d.month, d.day)
        except ValueError:
            return None
    bulunan = []                                          # "cumaya kadar", "salıdan önce": gün adı + en çok 3 harflik ek
    for ad, no in sorted(GUNLER.items(), key=lambda kv: -len(kv[0])):
        m = re.search(r"(?<![a-zçğıöşü])" + ad + r"(?:ya|ye|a|e|ı|i|dan|den|ta|te|da|de|ndan|nden)?(?![a-zçğıöşü])", t)
        if m and not any(abs(m.start() - b0) < 3 for b0, _ in bulunan):
            bulunan.append((m.start(), no))
    if bulunan:
        no = max(bulunan)[1] if "-" in t or "ya da" in t or " veya " in t else min(bulunan)[1]   # "çarşamba-perşembe" → geç olan
        ileri = (no - g.weekday()) % 7 or 7
        if "haftaya" in t or "gelecek hafta" in t or "önümüzdeki hafta" in t:
            ileri = (no - g.weekday()) % 7 + 7
        return g + timedelta(days=ileri)
    if "haftaya" in t or "gelecek hafta" in t or "önümüzdeki hafta" in t:
        return g + timedelta(days=7 + (4 - g.weekday()) % 7)
    if "hafta içi" in t or "bu hafta" in t or "hafta sonuna" in t or "hafta sonu" in t:
        if g.weekday() >= 4:                              # cuma/hafta sonu konuşulan "hafta içinde" = gelecek haftanın cuması
            return g + timedelta(days=(4 - g.weekday()) % 7 + 7) if g.weekday() == 4 else g + timedelta(days=(4 - g.weekday()) % 7)
        return g + timedelta(days=(4 - g.weekday()) % 7)
    if "ay sonu" in t:
        sonraki = (g.replace(day=28) + timedelta(days=4)).replace(day=1)
        return sonraki - timedelta(days=1)
    return None


def _ben():
    try:
        return _k((json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8")).get("benim_adim") or "").split()[0])
    except Exception:  # noqa: BLE001
        return ""


def _toplanti_gunu(veri):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", veri.get("baslik") or "")
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return datetime.fromtimestamp(veri.get("olusturma") or time.time()).date()


def liste(gun=60):
    """{sozlerin: [...], bekledigin: [...]} — her öğe: temel, konu, sirket, musteri, is, ne_zaman, son (YYYY-MM-DD|None), durum, k, i, kim."""
    ben = _ben(); bugun = date.today(); sinir = time.time() - gun * 86400
    sozlerin, bekledigin = [], []
    import kitaplik_onbellek
    for kayit in kitaplik_onbellek.hepsi():                  # 2026-10-25: mtime önbellekli (150 ms → ~5 ms)
        js, v = kayit["yol"], kayit["veri"]
        if kayit["mtime"] < sinir - 30 * 86400:
            continue
        if not v.get("toplanti") or v.get("onay_bekliyor") or not v.get("kisaca") or (v.get("olusturma") or 0) < sinir:
            continue
        g = _toplanti_gunu(v)
        konu = re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", v.get("baslik") or "")
        konu = re.sub(r" · [^·]+$", "", konu) or v.get("baslik")
        for ki, kisi in enumerate(v["kisaca"].get("kisiler") or []):
            benim = bool(ben) and _k(kisi.get("ad")).split()[:1] == [ben]
            for ii, x in enumerate(kisi.get("isler") or []):
                if x.get("bitti"):
                    continue
                st = son_tarih(x.get("ne_zaman"), g)
                durum = "tarihsiz" if not st else ("gecikti" if st < bugun else "bugun" if st == bugun else "yakinda" if (st - bugun).days <= 3 else "ileride")
                oge = {"temel": js.stem, "konu": konu, "toplanti_gunu": g.isoformat(), "sirket": v.get("sirket") or "", "musteri": v.get("musteri") or "",
                       "is": x.get("is"), "ne_zaman": x.get("ne_zaman") or "", "son": st.isoformat() if st else None, "durum": durum, "k": ki, "i": ii,
                       "sn": x.get("sn"), "kim": kisi.get("ad")}
                (sozlerin if benim else bekledigin).append(oge)
        for ii, x in enumerate(v["kisaca"].get("senden_karar") or []):  # kullanıcının vermesi beklenen kararlar (2026-10-23)
            if x.get("bitti") or not str(x.get("konu") or "").strip():
                continue
            sozlerin.append({"temel": js.stem, "konu": konu, "toplanti_gunu": g.isoformat(), "sirket": v.get("sirket") or "", "musteri": v.get("musteri") or "",
                             "is": x.get("konu"), "ne_zaman": "", "son": None, "durum": "karar", "k": -2, "i": ii, "sn": x.get("sn"), "kim": "",
                             "alinti": x.get("alinti") or ""})
    sira = {"gecikti": 0, "bugun": 1, "karar": 2, "yakinda": 3, "ileride": 4, "tarihsiz": 5}
    anahtar = lambda o: (sira[o["durum"]], o["son"] or "9999", o["toplanti_gunu"])   # noqa: E731
    return {"sozlerin": sorted(sozlerin, key=anahtar), "bekledigin": sorted(bekledigin, key=anahtar)}


def hatirlatma_metni():
    """Sabah bildirimi: (başlık, metin) ya da None."""
    s = liste()["sozlerin"]
    gec = [o for o in s if o["durum"] == "gecikti"]; bug = [o for o in s if o["durum"] == "bugun"]
    if not gec and not bug:
        return None
    parca = []
    if bug:
        parca.append("Bugün: " + "; ".join(o["is"] for o in bug[:2]))
    if gec:
        parca.append(f"{len(gec)} söz gecikti: " + gec[0]["is"])
    return (f"{len(bug) + len(gec)} sözün var", " · ".join(parca)[:180])


if __name__ == "__main__":
    d = liste()
    for o in d["sozlerin"]:
        print(o["durum"], o["son"], "|", o["is"], "|", o["konu"][:40], "|", o["ne_zaman"])
    print("--- beklediklerin")
    for o in d["bekledigin"][:10]:
        print(o["durum"], o["son"], "|", o["kim"], ":", o["is"])

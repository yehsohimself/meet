"""Kaydedilmeyen toplantılar (2026-10-29; kullanıcı: "Kurs meetlerini kaydetmeye gerek yok. Her hafta tekrar ediyor, anlarsın zaten.").

Her hafta tekrar eden ve toplantı olmayan görüşmeler (ör. çevrimiçi dil kursu) bir kez tanınınca bir daha kaydedilmez. Liste ayarlar.json
`kayit_disi` = [{ad, desenler, neden, eklenme, otomatik}] (git dışı; adlar koda yazılmaz). Kaydedici aynı listeyi okuyup bu görüşmelerde
kayda hiç başlamaz; site de gelen kaydı, canlı yazıya dökmeyi ve bildirimi atlar. Liste kendiliğinden büyür:
- kullanıcı "Bu kayıt bir toplantıya benzemiyor" kartında Kaldır derse, kaydın toplantı adı listeye girer;
- toplantı kapısı aynı adlı kaydı iki ayrı günde "toplantı değil" bulursa listeye girer (haftalık tekrar).
"""
import json
import re
import time
from pathlib import Path

# Teams/Meet/Zoom sekme başlıklarındaki genel parçalar ("(2) Toplantıya katılma | IK 18 | Microsoft Teams" → "IK 18")
GENEL = {"toplantıya katılma", "toplantiya katilma", "join meeting", "meeting", "toplantı", "toplanti", "microsoft teams", "teams", "google meet", "meet",
         "zoom", "zoom meeting", "zoom workplace", "ekipler ve kanallar", "teams and channels", "genel", "general", "sohbet", "chat", "takvim", "calendar",
         "arama", "aramalar", "calls", "görüşme", "etkinlik", "activity", "microsoft teams toplantısı", "microsoft teams meeting", "kayıt", "kayit"}


def _norm(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip().lower()
    return re.sub(r"^\(\d+\)\s*", "", s)


def imza(baslik):
    """Başlıktan toplantının kalıcı adı: genel parçalar ve tarih/saat atılır, kalan en anlamlı parça. Yoksa boş."""
    s = re.sub(r"^\s*\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}[.:]\d{2})?\s*·\s*", "", str(baslik or ""))      # Meet başlığı "2026-10-28 20.21 · Konu"
    s = re.sub(r"^\s*\(\d+\)\s*", "", s)
    s = re.sub(r"^\s*Meet\s*[-–]\s*", "", s)
    parcalar = [p.strip(" -–·") for p in re.split(r"\s[|·–-]\s", s) if p.strip(" -–·")]
    iyi = [p for p in parcalar if _norm(p) not in GENEL and not re.fullmatch(r"[a-z]{3}-[a-z]{4}-[a-z]{3}", p.lower())
           and not re.search(r"🔊|youtube|netflix", p, re.I) and len(p) >= 3]
    return iyi[0][:60] if iyi else ""


def liste(ay):
    out = []
    for x in (ay or {}).get("kayit_disi") or []:
        if isinstance(x, str):
            x = {"ad": x, "desenler": [x]}
        if isinstance(x, dict) and (x.get("desenler") or x.get("ad")):
            x = {**x, "desenler": [d for d in (x.get("desenler") or [x.get("ad")]) if isinstance(d, str) and len(d.strip()) >= 3]}
            if x["desenler"]:
                out.append(x)
    return out


def desenler(ay):
    return [d for x in liste(ay) for d in x["desenler"]]


def eslesen(basliklar, ay):
    """Başlıklardan biri listedeki bir desene uyuyorsa o kayıt (dict), yoksa None. Desen sözcük sınırıyla, büyük/küçük harf ve boşluk farkı yok sayılır."""
    bs = [_norm(b) for b in basliklar if b]
    if not bs:
        return None
    for x in liste(ay):
        for d in x["desenler"]:
            r = r"(?<![\w])" + re.escape(_norm(d)).replace(r"\ ", r"\s+") + r"(?![\w])"
            if any(re.search(r, b) for b in bs):
                return x
    return None


def ekle(ay, ad, desenler_=None, neden="", otomatik=False):
    """Listeye ekler (aynı ad ya da desen varsa eklemez). Döner: (yeni liste, eklendi mi)."""
    ad = re.sub(r"\s+", " ", str(ad or "")).strip()[:60]
    ds = [re.sub(r"\s+", " ", d).strip()[:60] for d in (desenler_ or [ad]) if isinstance(d, str) and len(d.strip()) >= 3]
    L = list((ay or {}).get("kayit_disi") or [])
    if not ad or not ds or eslesen(ds, {"kayit_disi": L}):
        return L, False
    L.append({"ad": ad, "desenler": ds, "neden": str(neden or "")[:120], "eklenme": time.strftime("%Y-%m-%d"), "otomatik": bool(otomatik)})
    return L, True


def aday_kaydet(dosya, ad, kaynak, gun=None):
    """Toplantı olmadığı anlaşılan bir kaydın adını geçmişe yazar. Döner: aynı adın kaç ayrı günde görüldüğü."""
    dosya = Path(dosya); gun = gun or time.strftime("%Y-%m-%d")
    try:
        g = json.loads(dosya.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        g = {}
    k = _norm(ad)
    if not k:
        return 0
    e = g.setdefault(k, {"ad": ad, "gunler": [], "kaynak": []})
    if gun not in e["gunler"]:
        e["gunler"] = (e["gunler"] + [gun])[-12:]
    if kaynak not in e["kaynak"]:
        e["kaynak"].append(kaynak)
    try:
        dosya.parent.mkdir(parents=True, exist_ok=True); dosya.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return len(e["gunler"])

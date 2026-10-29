"""takvim.py - Google Takvim'in gizli iCal (ICS) adresinden etkinlikleri okur; kayıt zamanına denk gelen toplantıyı bulur.

Kurulum: Google Takvim → Ayarlar → (takviminiz) → "Takvimi entegre et" → "iCal biçimindeki gizli adres" → Ayarlar'a yapıştır
(ayarlar.json "takvim_ics"). Giriş/izin gerekmez; adres gizli olduğu için kimseyle paylaşılmamalı.

Kullanım: etkinlik_bul(baslangic_epoch, bitis_epoch) -> {"ad", "katilimcilar": [{"ad","eposta"}], "bas", "bit", "link"} | None
Elle: python takvim.py            (şu anki/yaklaşan etkinlikleri listeler)
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
ONBELLEK = KLASOR / "kayitlar" / ".takvim.ics"
ONBELLEK_SN = 600


def _ayar():
    import ortak                                           # tek sürüm (2026-10-25)
    return ortak.ayar()


def adresler(url=None):
    """Ayarlardaki takvim adresleri (birden fazla olabilir; satır/boşlukla ayrılmış)."""
    ham = url if url is not None else (_ayar().get("takvim_ics") or "")
    if isinstance(ham, list):
        ham = "\n".join(ham)
    return [u.strip() for u in re.split(r"[\s,]+", str(ham)) if u.strip().startswith("http")]


def _davet_metni(url):
    """E-posta davetlerinden kurulan takvim (davetler.py; iş hesaplarının gizli takvim adresi yoksa). Tek adres sınanırken eklenmez."""
    if url is not None:
        return ""
    try:
        import davetler
        return davetler.metin()
    except Exception:  # noqa: BLE001
        return ""


def ics_getir(url=None, zorla=False):
    """Tüm takvimlerin ICS metni (art arda; VEVENT'ler birlikte ayrıştırılır) + e-posta davetleri. 10 dk önbellek."""
    davet = _davet_metni(url)
    return "\n".join(x for x in (_ics_getir(url, zorla), davet) if x)


def _ics_getir(url=None, zorla=False):
    urls = adresler(url)
    if not urls:
        return ""
    ONBELLEK.parent.mkdir(parents=True, exist_ok=True)
    if not zorla and ONBELLEK.exists() and time.time() - ONBELLEK.stat().st_mtime < ONBELLEK_SN:
        return ONBELLEK.read_text(encoding="utf-8")
    parcalar = []
    for u in urls:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "VideoHub/1.0"}), timeout=20) as r:
                metin = r.read().decode("utf-8", "replace")
            if "BEGIN:VCALENDAR" in metin:
                parcalar.append(metin)
        except Exception:  # noqa: BLE001
            continue
    if parcalar:
        ONBELLEK.write_text("\n".join(parcalar), encoding="utf-8")
        return "\n".join(parcalar)
    return ONBELLEK.read_text(encoding="utf-8") if ONBELLEK.exists() else ""


_TEK = {}


def durum():
    """Takvim takvim durum (adresler gizli kalır): [{no, ad, etkinlik, gorusme_30, hata}]. 10 dk önbellek."""
    out = []
    for no, u in enumerate(adresler()):
        onb = _TEK.get(u)
        if not onb or time.time() - onb[0] > ONBELLEK_SN:
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "VideoHub/1.0"}), timeout=20) as r:
                    metin = r.read().decode("utf-8", "replace")
                hata = "" if "BEGIN:VCALENDAR" in metin else "takvim biçiminde değil"
            except Exception as e:  # noqa: BLE001
                metin, hata = "", str(e)[:120]
            onb = (time.time(), metin, hata); _TEK[u] = onb
        _, metin, hata = onb
        ad = ""
        m = re.search(r"^X-WR-CALNAME:(.+)$", metin or "", re.M)
        if m:
            ad = _unescape(m.group(1).strip())
        E = etkinlikler(metin) if metin and not hata else []
        simdi = time.time()
        gorusme = sum(1 for e in E for ob, oe in _oluslar(e, simdi - 30 * 86400, simdi) if simdi - 30 * 86400 <= ob <= simdi and gorusme_mi(e, ob, oe))
        out.append({"no": no, "ad": ad or urllib.parse.urlparse(u).netloc, "etkinlik": len(E), "gorusme_30": gorusme, "hata": hata})
    return out


def dogrula(url):
    """Eklenmeden önce: adres takvim mi? Döner: (ad, etkinlik sayısı) ya da ValueError."""
    if not str(url).startswith("http"):
        raise ValueError("Adres https:// ile başlamalı")
    try:
        with urllib.request.urlopen(urllib.request.Request(url.strip(), headers={"User-Agent": "VideoHub/1.0"}), timeout=20) as r:
            metin = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Adrese ulaşılamadı ({str(e)[:80]})") from e
    if "BEGIN:VCALENDAR" not in metin:
        raise ValueError("Bu adres bir takvim değil (iCal/ICS adresi olmalı)")
    m = re.search(r"^X-WR-CALNAME:(.+)$", metin, re.M)
    return (_unescape(m.group(1).strip()) if m else ""), len(etkinlikler(metin))


def _satirlar(metin):
    """ICS satır katlamasını açar (devam satırları boşlukla başlar)."""
    sonuc = []
    for s in metin.splitlines():
        if s[:1] in (" ", "\t") and sonuc:
            sonuc[-1] += s[1:]
        else:
            sonuc.append(s)
    return sonuc


def _zaman(deger, params):
    """DTSTART değerini epoch'a çevirir (UTC 'Z', TZID'li yerel ya da tüm gün)."""
    from dateutil import tz
    deger = deger.strip()
    if re.fullmatch(r"\d{8}", deger):                        # tüm gün
        d = datetime.strptime(deger, "%Y%m%d").replace(tzinfo=tz.tzlocal())
        return d.timestamp(), True
    m = re.fullmatch(r"(\d{8}T\d{6})(Z?)", deger)
    if not m:
        return None, False
    d = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S")
    if m.group(2) == "Z":
        d = d.replace(tzinfo=timezone.utc)
    else:
        tzid = params.get("TZID")
        d = d.replace(tzinfo=(tz.gettz(tzid) if tzid else None) or tz.tzlocal())
    return d.timestamp(), False


def _unescape(s):
    return s.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


def etkinlikler(metin):
    """ICS metnini VEVENT listesine çevirir: [{"ad","bas","bit","rrule","exdates","katilimcilar","aciklama","konum","uid","tumgun"}]"""
    sonuc, cur = [], None
    for s in _satirlar(metin):
        if s == "BEGIN:VEVENT":
            cur = {"ad": "", "bas": None, "bit": None, "rrule": "", "exdates": [], "katilimcilar": [], "aciklama": "", "konum": "", "uid": "", "tumgun": False, "iptal": False, "bos": False}
            continue
        if s == "END:VEVENT":
            if cur and cur["bas"] is not None:
                if cur["bit"] is None:
                    cur["bit"] = cur["bas"] + (86400 if cur["tumgun"] else 3600)
                sonuc.append(cur)
            cur = None; continue
        if cur is None or ":" not in s:
            continue
        anahtar, _, deger = s.partition(":")
        ad, *paramlar = anahtar.split(";")
        params = dict(p.split("=", 1) for p in paramlar if "=" in p)
        ad = ad.upper()
        if ad == "SUMMARY":
            cur["ad"] = _unescape(deger)
        elif ad == "DTSTART":
            cur["bas"], cur["tumgun"] = _zaman(deger, params)
        elif ad == "DTEND":
            cur["bit"], _ = _zaman(deger, params)
        elif ad == "RRULE":
            cur["rrule"] = deger.strip()
        elif ad == "EXDATE":
            for v in deger.split(","):
                z, _ = _zaman(v, params)
                if z:
                    cur["exdates"].append(z)
        elif ad in ("ATTENDEE", "ORGANIZER"):
            eposta = re.sub(r"^mailto:", "", deger.strip(), flags=re.I)
            cn = _unescape(params.get("CN", "")).strip('"')
            if not cn or "@" in cn:
                cn = ""
            cur["katilimcilar"].append({"ad": cn, "eposta": eposta, "organizator": ad == "ORGANIZER"})
        elif ad == "DESCRIPTION":
            cur["aciklama"] = _unescape(deger)[:2000]
        elif ad == "LOCATION":
            cur["konum"] = _unescape(deger)[:300]
        elif ad == "UID":
            cur["uid"] = deger.strip()
        elif ad == "STATUS" and deger.strip().upper() == "CANCELLED":
            cur["iptal"] = True
        elif ad == "TRANSP" and deger.strip().upper() == "TRANSPARENT":
            cur["bos"] = True
    return sonuc


def _oluslar(e, pencere_bas, pencere_bit):
    """Tekrarlı etkinliğin pencere içindeki (bas, bit) oluşlarını üretir."""
    sure = e["bit"] - e["bas"]
    if not e["rrule"]:
        return [(e["bas"], e["bit"])]
    try:
        from dateutil.rrule import rrulestr
        from dateutil import tz
        dt0 = datetime.fromtimestamp(e["bas"], tz.tzlocal())
        kural = rrulestr(e["rrule"], dtstart=dt0)
        b0 = datetime.fromtimestamp(pencere_bas - sure, tz.tzlocal()); b1 = datetime.fromtimestamp(pencere_bit, tz.tzlocal())
        ex = {round(x) for x in e["exdates"]}
        return [(d.timestamp(), d.timestamp() + sure) for d in kural.between(b0, b1, inc=True) if round(d.timestamp()) not in ex]
    except Exception:  # noqa: BLE001
        return [(e["bas"], e["bit"])]


LINK = re.compile(r"https://(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|[\w.]*zoom\.us)/\S+")
YOKLUK = re.compile(r"^\s*(ooo\b|out of office|ofis ?dışı|izin|izinli|tatil|yıllık izin|abwesend|urlaub|holiday|vacation|focus time|odak|busy|meşgul|"
                    r"blok|block|lunch|öğle yemeği)", re.I)


def gorusme_mi(e, ob=None, oe=None):
    """Takvim etkinliği gerçek bir görüşme mi? (2026-10-23: 22 Ekim 09.26 Teams toplantısı bütün günü kaplayan 'OOO' etkinliğiyle eşleşti; adı 'OOO'
    oldu, katılımcı e-postası ajans alanından diye başka şirketin toplantısı ajansa yazıldı.) Tüm gün, 6 saatten uzun blok, iptal, ofis dışı/izin/odak
    gibi adlar ve kişinin kendisinden başka davetlisi ve görüşme linki olmayan etkinlikler görüşme sayılmaz."""
    if e.get("tumgun") or e.get("iptal"):
        return False
    ob = e["bas"] if ob is None else ob
    oe = e["bit"] if oe is None else oe
    if oe - ob >= 6 * 3600 or YOKLUK.search(e.get("ad") or ""):
        return False
    benim = {a.lower() for a in (_ayar().get("benim_epostalar") or [])}
    baskasi = [k for k in e.get("katilimcilar") or [] if k.get("eposta") and k["eposta"].lower() not in benim]
    link = LINK.search((e.get("konum") or "") + " " + (e.get("aciklama") or ""))
    if not baskasi and not link:
        return False
    return True


def etkinlik_bul(bas, bit=None, metin=None, pay=600):
    """Kayıt aralığıyla en çok örtüşen takvim etkinliği (±10 dk pay). Döner: sözlük ya da None."""
    bit = bit or bas + 1800
    metin = metin if metin is not None else ics_getir()
    if not metin:
        return None
    en, en_ortu = None, 0.0
    for e in etkinlikler(metin):
        if e["tumgun"] or e["iptal"]:
            continue
        for ob, oe in _oluslar(e, bas - 86400, bit + 86400):
            if not gorusme_mi(e, ob, oe):
                continue
            ortu = min(oe + pay, bit) - max(ob - pay, bas)
            if ortu > en_ortu:
                en_ortu, en = ortu, {**e, "bas": ob, "bit": oe}
    if not en or en_ortu < 120:
        return None
    link = ""
    m = re.search(r"https://(?:meet\.google\.com|teams\.microsoft\.com|[\w.]*zoom\.us)/\S+", (en["konum"] + " " + en["aciklama"]))
    if m:
        link = m.group(0).rstrip(">)")
    kat = [{"ad": k["ad"] or k["eposta"].split("@")[0], "eposta": k["eposta"]} for k in en["katilimcilar"] if k["eposta"]]
    return {"ad": en["ad"], "bas": en["bas"], "bit": en["bit"], "katilimcilar": kat, "link": link, "uid": en["uid"]}


def gun(metin=None, tarih=None):
    """Bir günün (yerel saat; varsayılan bugün) etkinlikleri: [{ad, bas, bit, link, kisiler}] sırayla. Transcript'in 'Bugün' akışı için."""
    metin = metin if metin is not None else ics_getir()
    t = time.localtime(tarih or time.time())
    bas = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)); bit = bas + 86400
    benim = {a.lower() for a in (_ayar().get("benim_epostalar") or [])}
    sonuc = []
    for e in etkinlikler(metin or ""):
        if e["tumgun"] or e["iptal"]:
            continue
        m = re.search(r"https://(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|[\w.]*zoom\.us)/\S+", e["konum"] + " " + e["aciklama"])
        kisiler = []
        for k in e["katilimcilar"]:
            ep = (k.get("eposta") or "").lower()
            ad = k.get("ad") or ep.split("@")[0]
            if ep in benim or ad.lower() in ("me", "ben") or not ad or ad in kisiler:
                continue
            kisiler.append(ad)
        for ob, oe in _oluslar(e, bas - 86400, bit):
            if bas <= ob < bit and oe - ob < 12 * 3600:            # 24 saatlik "OOO" gibi blokları atla
                sonuc.append({"ad": e["ad"], "bas": ob, "bit": oe, "link": m.group(0).rstrip(">)") if m else "", "kisiler": kisiler,
                              "gorusme": gorusme_mi(e, ob, oe)})
    return sorted(sonuc, key=lambda x: x["bas"])


def siradaki(metin=None, gun_sayisi=7):
    """Şu andan sonraki ilk görüşme (en çok N gün içinde; tüm gün ve 12 saatten uzun bloklar hariç)."""
    simdi = time.time()
    for g in range(gun_sayisi + 1):
        for e in gun(metin, simdi + g * 86400):
            if e["bas"] > simdi and e.get("gorusme"):
                return e
    return None


def suren(metin=None, simdi=None, once=300, sonra=600):
    """Şu an süren (5 dk öncesinden 10 dk sonrasına) çevrimiçi görüşme: Meet/Zoom/Teams linki ya da başka davetlisi olan etkinlik.
    Kaydedici, Chrome uzantısı susarsa tarayıcı kaydına bununla başlar (.takvim_arama). Döner: {ad, bas, bit, link} ya da None."""
    metin = metin if metin is not None else ics_getir()
    simdi = simdi or time.time()
    for e in etkinlikler(metin or ""):
        if e["tumgun"] or e["iptal"]:
            continue
        m = re.search(r"https://(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|[\w.]*zoom\.us)/\S+", e["konum"] + " " + e["aciklama"])
        if not m and len(e["katilimcilar"]) < 2:
            continue
        for ob, oe in _oluslar(e, simdi - 86400, simdi + 3600):
            if ob - once <= simdi <= oe + sonra and gorusme_mi(e, ob, oe):
                return {"ad": e["ad"], "bas": ob, "bit": oe, "link": m.group(0).rstrip(">)") if m else ""}
    return None


def yaklasan(metin=None, saat=12):
    """Önümüzdeki saatlerdeki etkinlikler (sırayla)."""
    metin = metin if metin is not None else ics_getir()
    simdi = time.time(); sonuc = []
    for e in etkinlikler(metin or ""):
        if e["tumgun"] or e["iptal"]:
            continue
        for ob, oe in _oluslar(e, simdi - 3600, simdi + saat * 3600):
            if oe >= simdi - 3600 and ob <= simdi + saat * 3600:
                sonuc.append({"ad": e["ad"], "bas": ob, "bit": oe, "katilimcilar": [k["ad"] or k["eposta"] for k in e["katilimcilar"]]})
    return sorted(sonuc, key=lambda x: x["bas"])


if __name__ == "__main__":
    metin = ics_getir(zorla=True)
    if not metin:
        print("Takvim adresi yok ya da ulaşılamadı (Ayarlar → Takvim)."); raise SystemExit(1)
    for e in yaklasan(metin, saat=48):
        print(time.strftime("%d.%m %H:%M", time.localtime(e["bas"])), "·", e["ad"], "·", ", ".join(e["katilimcilar"][:5]))

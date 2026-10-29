"""sirketler.py - Birlikte çalışılan şirketler katmanı (2026-10-20). Kullanıcı: "Toplantıları şirketlere böl; onların müşterileri var; şirketlerin
kendi alt sayfaları ve genel yorumlamaları olsun; logoları profil gibi."

Hiyerarşi: Şirket (ajans, kendi şirketi... | Genel) → Müşteri (marka) → Toplantı.
- Tanımlar YALNIZCA `ayarlar.json` "sirketler" (kullanıcı sitede düzenler; kodda şirket ya da kişi adı yok, 2026-10-25): her şirket
  {kod, ad, renk, alan (e-posta alan adları), aciklama, musteriler, anahtar (tanıma sözcükleri), kisiler, drive_klasor, kisisel}.
  `alt_isler` {"<seri adı>": "<ana marka>"}: ayrı marka değil, bir markanın serisi (müşteri her yerde ana marka olur).
- `sec(veri, segmentler)`: önce kurallar (müşteri listesi, şirket adı geçmesi, takvimdeki e-posta alan adı, öğrenilmiş kişiler), olmazsa Claude.
  Güvenli atamada katılımcı adları şirketin `kisiler` listesine öğrenilir (bir dahaki toplantıda kuralla bulunur).
- `yorum(kod)`: şirketin son 45 günlük toplantılarından genel yorum (durum, tekrar eden konular, açık işleriniz, ilişki, fırsatlar).
Logolar `static/logolar/<kod>.png` (müşteriler de); yoksa sitede baş harf; kullanıcı sürükleyip bırakınca kaydedilir.
"""
import json
import re
import time
import unicodedata
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
AYAR = KLASOR / "ayarlar.json"
LOGO = KLASOR / "static" / "logolar"
YORUM = KLASOR / "profil" / "sirket_yorum"

VARSAYILAN = []          # şirketler yalnız ayarlar.json'da (eskiden kullanıcının şirketleri burada sabitti)


def alt_isler():
    """ayarlar.json `alt_isler`: {"<seri adı>": "<ana marka>"}; ayrı marka değil, bir markanın serisi."""
    d = _ayar().get("alt_isler") or {}
    return {str(k).strip().casefold(): str(v) for k, v in d.items() if k and v} if isinstance(d, dict) else {}


def ana_marka(ad):
    """Seri/alt iş adı → ana marka; diğerleri olduğu gibi."""
    return alt_isler().get(str(ad or "").strip().casefold(), ad)


GENEL = {"kod": "genel", "ad": "Genel", "renk": "#8E8E93", "aciklama": "Hiçbir şirketle ilgisi olmayan kayıtlar (aile sohbeti, yayın, kısa denemeler)."}


def _ayar():
    import ortak                                           # tek sürüm (2026-10-25)
    return ortak.ayar()


def liste():
    s = _ayar().get("sirketler")
    if not (isinstance(s, list) and s):
        return []
    renkler = ["#141414", "#F0383E", "#17A65B", "#7A5AF8", "#2D5BFF", "#F2C230"]
    for i, x in enumerate(s):
        x.setdefault("renk", renkler[i % len(renkler)])
    return s


def kaydet(sirketler):
    d = _ayar(); d["sirketler"] = sirketler
    AYAR.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def kod_yap(ad):
    t = unicodedata.normalize("NFKD", str(ad or "").replace("ı", "i").replace("İ", "I")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)[:30] or "x"


def _k(s):
    return str(s or "").replace("İ", "i").replace("I", "ı").lower().strip()


# Marka simgeleri (2026-10-20). Kullanıcı: "orijinal logo olmasın; minimal temsili görsel", sonra "bu aileyi beğenmedim; tatlı, birbirinden
# kopuk olmayan, aynı ailenin yayılımı gibi, markalarla çok ilgili olsun; renkler ayarlardan; tonlar sitenin
# renkleriyle uyumlu (biri pastel biri fosforlu olmasın)". Aile: Phosphor Icons duotone (MIT, static/ikon/). Zemin şirket rengi, simge beyaz
# (duotone dolgusu yarı saydam beyaz). Şirketler: aynı yumuşak dolgu dairesi içinde yuvarlak harf.
IKON = KLASOR / "static" / "ikon"
def _glif():
    """Marka kodu → Phosphor simge adı; ayarlar.json `logo_simgeler` (kodda marka adı yok, 2026-10-25)."""
    d = _ayar().get("logo_simgeler") or {}
    return d if isinstance(d, dict) else {}




def _ikon_ic(ad):
    """Phosphor SVG'nin iç yolları (fill=currentColor → beyaz)."""
    try:
        t = (IKON / f"{ad}.svg").read_text(encoding="utf-8")
    except OSError:
        return ""
    ic = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", t.strip(), flags=re.S)
    return ic


def _harf(ad):
    import harfler
    h = (harfler.ust(str(ad or "?").strip().split(" ")[0]) or "?")[:1]
    return ('<circle cx="128" cy="128" r="70" fill="#fff" opacity="0.2"/>'
            f'<text x="128" y="131" text-anchor="middle" dominant-baseline="central" fill="#fff" font-family="\'Arial Rounded MT Bold\',\'SF Pro Rounded\','
            f'ui-rounded,\'Nunito\',\'Helvetica Neue\',Arial,sans-serif" font-weight="700" font-size="116">{h}</text>')


def acik_mi(renk):
    """Açık zemin mi (kırık beyaz #F4F2EE gibi): üstündeki harf/simge koyu olmalı."""
    h = str(renk or "").lstrip("#")
    if len(h) != 6:
        return False
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.7


def _svg(renk, ic, ikon=True):
    yazi = "#141414" if acik_mi(renk) else "#fff"
    if yazi != "#fff":
        ic = ic.replace('fill="#fff"', f'fill="{yazi}"').replace("fill='#fff'", f"fill='{yazi}'").replace('fill="rgba(255,255,255', 'fill="rgba(20,20,20')
    govde = f'<g fill="{yazi}" transform="translate(46 46) scale(0.64)">{ic}</g>' if ikon else ic
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" fill="{renk}"/>{govde}</svg>'


def logolari_uret():
    """Her şirket (harf) ve müşterisi (aile simgesi ya da harf) için static/logolar/<kod>.svg; şirketin renginde."""
    LOGO.mkdir(parents=True, exist_ok=True)
    for x in liste():
        renk = x.get("renk") or "#141414"
        hedefler = [(x["kod"], _svg(renk, _harf(x["ad"]), ikon=False))]
        for m in x.get("musteriler") or []:
            kod = kod_yap(m) + ("_urun" if kod_yap(m) == x["kod"] else "")
            glif = _glif(); ic = _ikon_ic(glif[kod]) if kod in glif else ""
            hedefler.append((kod, _svg(renk, ic) if ic else _svg(renk, _harf(m), ikon=False)))
        for kod, icerik in hedefler:
            yol = LOGO / f"{kod}.svg"
            if not yol.exists() or yol.read_text(encoding="utf-8") != icerik:
                yol.write_text(icerik, encoding="utf-8")


def logo(kod):
    for uz in ("svg", "png"):
        p = LOGO / f"{kod}.{uz}"
        if p.exists():
            return f"/static/logolar/{kod}.{uz}?v={int(p.stat().st_mtime)}"
    return ""


def _kural(veri, metin=""):
    """Döner (sirket_kod, neden) ya da (None, '')."""
    s = liste()
    musteri = _k(ana_marka(veri.get("musteri")))
    for x in s:
        if musteri and (musteri == _k(x["ad"]) or musteri in {_k(m) for m in list(x.get("musteriler") or []) + list(x.get("anahtar") or [])}):
            return x["kod"], f"müşteri {veri.get('musteri')}"
    eposta = [str(k.get("eposta") or "").lower() for k in ((veri.get("takvim") or {}).get("katilimcilar") or [])]
    for x in s:
        if any(e.endswith("@" + a) for a in x.get("alan") or [] for e in eposta):
            return x["kod"], "takvim e-posta alan adı"
    bas = _k(veri.get("baslik")) + " " + _k((veri.get("takvim") or {}).get("ad"))
    for x in s:
        if any(len(m) >= 4 and _k(m) in bas for m in [x["ad"]] + list(x.get("musteriler") or []) + list(x.get("anahtar") or [])):
            return x["kod"], "başlıkta adı geçiyor"
    kisiler = {_k(a) for a in list((veri.get("etiket") or {}).values()) + list(veri.get("katilimcilar") or []) if not str(a).startswith("Konuşmacı")}
    puan = {x["kod"]: len(kisiler & {_k(k) for k in x.get("kisiler") or []}) for x in s}
    en = max(puan.items(), key=lambda kv: kv[1]) if puan else (None, 0)
    if en[1] >= 2 and list(puan.values()).count(en[1]) == 1:
        return en[0], "tanıdık kişiler"
    m = _k(veri.get("baslik")) + " " + _k(metin[:20000])
    say = {x["kod"]: sum(m.count(_k(n)) for n in [x["ad"]] + list(x.get("musteriler") or []) + list(x.get("anahtar") or []) if len(n) >= 4) for x in s}
    en = max(say.items(), key=lambda kv: kv[1]) if say else (None, 0)
    sirali = sorted(say.values(), reverse=True)
    if en[1] >= 3 and (len(sirali) < 2 or sirali[1] * 3 <= en[1]):
        return en[0], "adı konuşmada geçiyor"
    return None, ""


def sec(veri, segmentler, log=print, claude=True):
    """Toplantının şirketi: {kod, neden, musteri (öneri)}. Kurallar yetmezse Claude (toplantı izniyle)."""
    metin = " ".join(s.get("metin", "") for s in segmentler or [])
    kod, neden = _kural(veri, metin)
    if kod:
        return {"kod": kod, "neden": neden}
    if not claude:
        return {"kod": "genel", "neden": "kural yok"}
    try:
        import claude_yaz
        import ozet as ozet_modulu
        with claude_yaz.toplanti():
            if not claude_yaz.hazir():
                return {"kod": "genel", "neden": "Claude yok"}
            tanim = "\n".join(f"- {x['kod']}: {x['ad']} — {x.get('aciklama', '')} Müşterileri / ilgili adlar: {', '.join(list(x.get('musteriler') or []) + list(x.get('anahtar') or [])) or '-'}. "
                              f"Bilinen kişiler: {', '.join(x.get('kisiler') or []) or '-'}" for x in liste())
            import ortak
            alt = "".join(f"\nNot: '{k.title()}' {v} markasının serisidir; müşteri {v}." for k, v in alt_isler().items())
            istem = (f"Kullanıcı ({ortak.kimlik()['ilk_ad']}) serbest çalışan bir kreatif; şu şirketlerle çalışıyor:\n{tanim}{alt}\n- genel: hiçbiri (kişisel, ağ, etkinlik, eğitim, alakasız kayıt)\n\n"
                     f"Toplantı başlığı: {veri.get('baslik') or ''}\nKatılımcılar: {', '.join(veri.get('katilimcilar') or []) or '-'}\n"
                     f"Konuşmacılar: {', '.join(v for v in (veri.get('etiket') or {}).values())}\n\nBu toplantı hangi şirketle ilgili? Konuşulan marka/müşteri, "
                     "kişiler ve iş içeriğine bak. Toplantı değilse (ör. yayın, video) 'genel'. Ayrıca konuşulan müşteri markası (yoksa boş).\n"
                     'Yalnızca JSON: {"sirket": "kod", "musteri": "marka ya da boş", "guven": 0.0-1.0, "neden": "kısa"}\n\nKONUŞMA (kısaltılmış):\n' + metin[:30000])
            c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, zaman_asimi=180)) or {}
        kod = str(c.get("sirket") or "genel")
        if kod not in {x["kod"] for x in liste()} or float(c.get("guven") or 0) < 0.6:
            kod = "genel"
        return {"kod": kod, "neden": "Claude: " + str(c.get("neden") or "")[:120], "musteri": ana_marka(str(c.get("musteri") or "")[:40])}
    except Exception as e:  # noqa: BLE001
        log(f"      Şirket seçilemedi ({e})")
        return {"kod": "genel", "neden": "hata"}


def ogren(kod, veri):
    """Atanan şirketin kişi listesine bu toplantının adlı konuşmacılarını ekler (kullanıcının kendisi hariç)."""
    if kod == "genel":
        return
    ben = _k((_ayar().get("benim_adim") or "").split(" ")[0])
    adlar = [a for a in list((veri.get("etiket") or {}).values()) + list(veri.get("katilimcilar") or [])
             if a and not str(a).startswith("Konuşmacı") and _k(a).split(" ")[0] != ben]
    import kisiler
    adlar = [a for a in adlar if kisiler.ad_mi(a)]          # Meet panelinin arayüz yazıları kişi sanılmasın
    s = liste(); degisti = False
    for x in s:
        if x["kod"] == kod:
            for a in adlar:
                if _k(a) not in {_k(k) for k in x.setdefault("kisiler", [])}:
                    x["kisiler"].append(a); degisti = True
    if degisti:
        kaydet(s)


def yorum(kod, toplantilar, log=print):
    """Şirket için genel yorum (markdown). toplantilar: [veri] son 45 gün, yeniden eskiye."""
    import claude_yaz
    x = next((s for s in liste() if s["kod"] == kod), GENEL)
    parca = []
    for v in toplantilar[:15]:
        ks = v.get("kisaca") or {}
        ozet = " ".join(ks.get("ozet") or []) or ((v.get("ozet") or {}).get("ozet") if isinstance(v.get("ozet"), dict) else "") or ""
        isler = "; ".join(f"{k['ad']}: " + ", ".join(i["is"] + (" ✓" if i.get("bitti") else "") for i in k["isler"]) for k in ks.get("kisiler") or [])
        dn = v.get("danisman") or {}
        parca.append(f"### {v.get('baslik')} (müşteri: {v.get('musteri') or '-'})\nÖzet: {ozet[:1500]}\nİşler: {isler[:800]}\n"
                     + (f"Danışman gözlemi: {dn.get('ozet', '')[:500]}" if dn else ""))
    if not parca:
        return ""
    istem = (f"Kullanıcının {x['ad']} ile çalışması hakkında, son toplantılara bakarak kısa bir genel yorum yaz ({x.get('aciklama', '')}).\n"
             "Bölümler (markdown, kalın başlıklar): **Durum** (2-3 cümle), **Tekrar eden konular**, **Açık işleriniz** (kullanıcının bitmemiş işleri, "
             "hangi toplantıdan), **İlişki ve dinamik** (kim karar veriyor, işler nasıl akıyor, gerilim noktaları), **Fırsatlar** (bu şirketle işi "
             "büyütmek ya da kolaylaştırmak için 1-3 öneri). Somut, isimli; uydurma yok; en fazla 250 kelime. Sen dili.\n\n" + "\n\n".join(parca))
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return ""
        metin = claude_yaz.sor(istem, "", zaman_asimi=300)
    YORUM.mkdir(parents=True, exist_ok=True)
    (YORUM / f"{kod}.json").write_text(json.dumps({"metin": metin, "zaman": time.time(), "adet": len(parca)}, ensure_ascii=False), encoding="utf-8")
    return metin


def yorum_oku(kod):
    try:
        return json.loads((YORUM / f"{kod}.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None

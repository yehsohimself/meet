"""kisiler.py - Kişi profilleri (2026-10-21; kategoriyi zorlayan fikirler, kullanıcı "ekle" dedi). Şirket profilleri gibi, toplantılarda geçen her
insanın da bir profili: hangi toplantılarda vardı, hangi şirketten, ondan beklediğin işler, senden istedikleri (kapsam), onarılmamış kırılmalar ve
Claude'un "bilmen gereken" notu (neyi önemsiyor, nasıl ikna olur, iletişim tarzı, dikkat). Not yalnızca o kişinin kendi sözlerinden yazılır;
`profil/kisiler/<kod>.json` önbellek, yeni toplantı gelince tazelenir. Kullanıcının kendisi ve adı konmamış "Konuşmacı N" etiketleri liste dışı.
"""
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
NOT = KLASOR / "profil" / "kisiler"


def _oku(yol, bos):
    try:
        return json.loads(Path(yol).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return bos


def _k(s):
    return str(s or "").replace("İ", "i").replace("I", "ı").lower().strip()


def kod(ad):
    t = unicodedata.normalize("NFKD", _k(ad).replace("ı", "i")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40] or "x"


def _ben():
    return _k((_oku(KLASOR / "ayarlar.json", {}).get("benim_adim") or "").split(" ")[0])


_ONB = {}   # dosya → (mtime, toplantı mı, veri, segmentler); video transkriptleri büyük, her istekte yeniden okunmasın


def _toplantilar():
    gorulen = set()
    for js in KLASOR.glob("transkript_*.json"):
        gorulen.add(js)
        try:
            mt = js.stat().st_mtime
        except OSError:
            continue
        o = _ONB.get(js)
        if not o or o[0] != mt:
            d = _oku(js, {})
            v = d.get("veri") or {}
            gec = bool(v.get("toplanti")) and not v.get("onay_bekliyor")
            o = _ONB[js] = (mt, gec, v if gec else None, (d.get("segmentler") or []) if gec else None)
        if o[1]:
            yield js.stem, o[2], o[3]
    for js in [k for k in _ONB if k not in gorulen]:
        _ONB.pop(js, None)


ARAYUZ = re.compile(r"\b(sesini|kadraj|arka plan|efekt|sustur|kamera|mikrofon|katılımcı|sunum|ekran|paylaş|toplantı|görüşme|ayarlar|"
                    r"mute|unmute|camera|participants?|backgrounds?|effects?|reframe|present\w*|meeting|you|siz|sen|zoom|window|screen|full|open|close|"
                    r"pin|unpin|captions?|chat|more options|settings|leave|raise|hand|layout|tile|spotlight|host|remove|enter|exit|yakınlaştır|uzaklaştır|tam ekran|"
                    r"pencere|minimi[sz]e|maximi[sz]e|picture)\b", re.I)


def ad_mi(a):
    """Kişi adı mı? Uzantı Meet panelinden 'Yeniden kadraja al', 'Başka kullanıcının sesini açamazsınız' gibi arayüz yazılarını da katılımcı sanmıştı
    (2026-10-22). Ad = 1-4 sözcük, her sözcük büyük harfle (ya da hepsi küçük: 'ali veli') başlar, arayüz sözcüğü yok."""
    a = str(a or "").strip()
    p = a.split()
    if not 1 <= len(p) <= 4 or len(a) > 40 or ARAYUZ.search(a) or re.search(r"[\d@#:/]", a):
        return False
    return all(w[0].isupper() for w in p) or all(w.islower() for w in p) and len(p) <= 3


def _adlar(v):
    adlar = [a for a in list((v.get("etiket") or {}).values()) + list(v.get("katilimcilar") or []) if a and not str(a).startswith("Konuşmacı") and ad_mi(a)]
    return list(dict.fromkeys(adlar))


def _birlestir():
    """Ad yazımlarını birleştirir: 'ali veli' = 'Ali Veli'; tek ad ('Umut') aynı adla başlayan TEK tam ad varsa ona bağlanır."""
    tum = Counter()
    for _t, v, _s in _toplantilar():
        for a in _adlar(v):
            tum[a] += 1
    gorunen = {}
    for a, n in tum.most_common():                      # en sık yazım görünen ad olur; büyük harfli tercih
        k = kod(a)
        if k not in gorunen or (a[:1].isupper() and not gorunen[k][:1].isupper()):
            gorunen[k] = a
    for k, a in gorunen.items():                         # hep küçük yazılmışsa ('ali veli') baş harfler büyük
        if a == a.lower():
            gorunen[k] = " ".join(("İ" + w[1:]) if w[:1] == "i" else w[:1].upper() + w[1:] for w in a.split())
    tam = {k: a for k, a in gorunen.items() if " " in a.strip()}
    harita = {}
    for k, a in gorunen.items():
        if " " not in a.strip():
            esler = [k2 for k2, a2 in tam.items() if _k(a2).split()[0] == _k(a)]
            harita[k] = esler[0] if len(esler) == 1 else k
        else:
            harita[k] = k
    return harita, gorunen


def liste():
    """[{kod, ad, sirket, toplanti, son, bekleyen, kirilma}] — en çok görüşülen önce."""
    harita, gorunen = _birlestir(); ben = _ben()
    kisiler = {}
    for temel, v, _s in _toplantilar():
        for a in _adlar(v):
            k = harita.get(kod(a), kod(a))
            if ben and _k(gorunen.get(k, a)).split()[:1] == [ben]:
                continue
            x = kisiler.setdefault(k, {"kod": k, "ad": gorunen.get(k, a), "toplantilar": set(), "sirketler": Counter(), "son": 0})
            x["toplantilar"].add(temel); x["sirketler"][v.get("sirket") or "genel"] += 1
            x["son"] = max(x["son"], v.get("olusturma") or 0)
    out = []
    for x in kisiler.values():
        p = profil(x["kod"], hafif=True)
        out.append({"kod": x["kod"], "ad": x["ad"], "sirket": x["sirketler"].most_common(1)[0][0], "toplanti": len(x["toplantilar"]), "son": x["son"],
                    "bekleyen": len(p["bekledigin"]), "kirilma": len(p["kirilmalar"])})
    return sorted(out, key=lambda x: (-x["toplanti"], -x["son"]))


def _eslesir(ad, k, harita):
    return bool(ad) and harita.get(kod(ad), kod(ad)) == k


def cozumle(k):
    """Kod ya da ad → birleştirilmiş kişi kodu ('selin' → 'selin-donmez' tekse)."""
    harita, gorunen = _birlestir()
    k = kod(k)
    if k in harita:
        return harita[k]
    esler = {harita.get(k2, k2) for k2 in gorunen if k2.split("-")[0] == k}   # yalnız ilk ad verildiyse ('selin') tek eşleşen tam ad
    return esler.pop() if len(esler) == 1 else k


def profil(k, hafif=False):
    """Kişinin tüm bilgisi. hafif=True ise Claude notu ve sözler olmadan (liste için)."""
    harita, gorunen = _birlestir()
    k = harita.get(k, k)
    ad = gorunen.get(k) or k
    toplantilar, bekledigin, istekler, kirilmalar, sozleri = [], [], [], [], []
    onarilan = set()
    for _t, v, _s in _toplantilar():
        onarilan |= set((v.get("sinyaller") or {}).get("onarilan") or [])
    for temel, v, seg in _toplantilar():
        adlar = _adlar(v)
        if not any(_eslesir(a, k, harita) for a in adlar):
            continue
        baslik = v.get("baslik") or temel
        toplantilar.append({"temel": temel, "baslik": baslik, "zaman": v.get("olusturma") or 0, "sirket": v.get("sirket") or "genel", "musteri": v.get("musteri") or ""})
        for kisi in (v.get("kisaca") or {}).get("kisiler") or []:
            if _eslesir(kisi.get("ad"), k, harita):
                for i, x in enumerate(kisi.get("isler") or []):
                    if not x.get("bitti"):
                        bekledigin.append({"is": x.get("is"), "ne_zaman": x.get("ne_zaman"), "temel": temel, "toplanti": baslik})
        sy = v.get("sinyaller") or {}
        for x in sy.get("kapsam") or []:
            if _eslesir(x.get("kim"), k, harita):
                istekler.append({**x, "temel": temel, "toplanti": baslik})
        for x in sy.get("kirilmalar") or []:
            if _eslesir(x.get("kim"), k, harita) and not x.get("onarildi") and x.get("id") not in onarilan:
                kirilmalar.append({**x, "temel": temel, "toplanti": baslik})
        if not hafif:
            etiket = {str(kk): vv for kk, vv in (v.get("etiket") or {}).items()}
            for s in seg:
                if _eslesir(etiket.get(str(s.get("k")), ""), k, harita):
                    sozleri.append(s.get("metin", "").strip())
    toplantilar.sort(key=lambda x: -x["zaman"])
    p = {"kod": k, "ad": ad, "toplantilar": toplantilar, "bekledigin": bekledigin, "istekler": istekler, "kirilmalar": kirilmalar,
         "sirket": Counter(t["sirket"] for t in toplantilar).most_common(1)[0][0] if toplantilar else "genel"}
    if not hafif:
        p["soz_kelime"] = sum(len(x.split()) for x in sozleri)
        p["_sozleri"] = sozleri
    return p


def not_oku(k):
    return _oku(NOT / f"{k}.json", None)


def not_uret(k, log=print):
    """'Bilmen gereken' notu: yalnızca kişinin kendi sözlerinden + ondan beklenenler ve kırılmalar. Döner: sözlük ya da None."""
    import claude_yaz
    import ozet as ozet_modulu
    p = profil(k)
    if not p["toplantilar"]:
        return None
    sozler = p.pop("_sozleri")
    metin = " ".join(sozler)
    if len(metin.split()) < 60:
        n = {"yetersiz": True, "zaman": time.time(), "toplanti": len(p["toplantilar"])}
        NOT.mkdir(parents=True, exist_ok=True); (NOT / f"{k}.json").write_text(json.dumps(n, ensure_ascii=False), encoding="utf-8")
        return n
    istem = (f"Kullanıcı (serbest kreatif) bu kişiyle toplantılarda çalışıyor: {p['ad']}. Aşağıda bu kişinin {len(p['toplantilar'])} toplantıdaki KENDİ sözleri var "
             f"(toplantılar: {'; '.join(t['baslik'] for t in p['toplantilar'][:6])}).\n"
             + (f"Ondan beklenen işler: {'; '.join(x['is'] for x in p['bekledigin'][:8])}\n" if p["bekledigin"] else "")
             + (f"kullanıcıdan istedikleri: {'; '.join(x['istek'] for x in p['istekler'][:8])}\n" if p["istekler"] else "")
             + "\nKullanıcı bu kişiyle bir sonraki görüşmeye girmeden önce 20 saniyede okuyacak. Yalnızca sözlerde dayanağı olanı yaz, kişilik analizi ya da "
             "teşhis yapma, uydurma. 'Sen' diliyle, kısa ve somut.\n"
             "- bilmen: tam 3 madde, her biri en fazla 18 kelime: bu kişiyle çalışırken en çok işine yarayacak şeyler.\n"
             "- onemsedigi: en fazla 3 kısa madde (neyi sık vurguluyor).\n- ikna: tek cümle (hangi tür gerekçeyle ikna oluyor, ne zaman itiraz ediyor).\n"
             "- tarz: tek cümle (iletişim tarzı: kısa mı uzun mu, karar mı tartışma mı, resmî mi samimi mi).\n- dikkat: varsa tek cümle (hassas nokta), yoksa boş.\n"
             "- rol: tek kısa ifade (ör. 'ajans tarafında müşteri ilişkileri', 'kurgucu', 'marka tarafı karar verici') — emin değilsen boş.\n"
             'Yalnızca JSON: {"rol": "", "bilmen": ["", "", ""], "onemsedigi": [], "ikna": "", "tarz": "", "dikkat": ""}\n\nSÖZLERİ:\n' + metin[:60000])
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return None
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, zaman_asimi=300)) or {}
    if not c.get("bilmen"):
        return None
    c.update({"zaman": time.time(), "toplanti": len(p["toplantilar"]), "model": ozet_modulu.SON_MODEL})
    NOT.mkdir(parents=True, exist_ok=True)
    (NOT / f"{k}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Kişi notu: {p['ad']}")
    return c


if __name__ == "__main__":
    for x in liste():
        print(x)

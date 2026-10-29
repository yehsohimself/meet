"""danisman.py - Toplantı sonrası kişisel kariyer danışmanı notu (2026-10-20).

Kullanıcı: "Toplantıdaki konuşmalara bakıp bir kariyer danışmanı rolüyle bana tavsiyelerde bulun: 'bugün şöyle konuştun ama şöyle davransan daha
iyi olabilirdi', 'şu konuda bir fırsat görüyorum'. Kariyerimi büyütmem ya da bambaşka konularda dersler, aksiyonlar. Drive'daki dokümana ekle."

- Kullanıcının hangi konuşmacı olduğu: ayarlardaki ad etikette varsa o; yoksa Claude konuşmadan çıkarır (hitap, "<ad> sen..." vb.).
- Ölçüler (kodla, dayanak olsun): kişi başına konuşma süresi/payı, soru sayısı, en uzun kesintisiz konuşma, söz kesme sayısı (yaklaşık).
- Süreklilik: `profil/danisman.json` önceki toplantılardaki dersler ve aksiyonlar; yeni not ilerlemeyi ya da tekrar eden kalıbı söyler.
- Yazı modeli opus (koçluk kalitesi); toplantı içeriği için 'Toplantılarda da Claude' izni gerekir.
Çıktı `veri["danisman"]`; Word belgesinin sonunda "Kişisel: Kariyer danışmanı notu" bölümü (Drive'a giden belge).
"""
import json
import re
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
GECMIS = KLASOR / "profil" / "danisman.json"


def _misafir():
    try:
        import claude_yaz
        return claude_yaz.MISAFIR.get()
    except Exception:  # noqa: BLE001
        return None


def _gecmis_yolu():
    """Davetlinin danışman geçmişi kendi klasöründe; sahibinkine okunmaz, yazılmaz."""
    m = _misafir()
    return KLASOR / "misafir" / re.sub(r"[^a-f0-9]", "", m["id"]) / "danisman.json" if m and m.get("id") else GECMIS


def _ben():
    m = _misafir()
    if m:
        return (m.get("ad") or "").strip()
    try:
        return (json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8")).get("benim_adim") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def olculer(segmentler, etiket):
    """{ad: {sn, pay, soru, en_uzun, kesme}} (kesme: başkası konuşurken 0,3 sn içinde söze girmesi)."""
    o = {}
    toplam = 0.0
    onceki = None
    blok = {"ad": None, "bas": 0, "bit": 0}
    for s in segmentler:
        ad = etiket.get(str(s.get("k")), f"Konuşmacı {s.get('k')}") if s.get("k") is not None else "?"
        sure = max(0.0, s["bit"] - s["bas"]); toplam += sure
        x = o.setdefault(ad, {"sn": 0.0, "soru": 0, "en_uzun": 0.0, "kesme": 0})
        x["sn"] += sure; x["soru"] += s["metin"].count("?")
        if onceki and onceki["ad"] != ad and s["bas"] < onceki["bit"] - 0.3:
            x["kesme"] += 1
        if blok["ad"] == ad and s["bas"] - blok["bit"] < 2.5:
            blok["bit"] = s["bit"]
        else:
            blok = {"ad": ad, "bas": s["bas"], "bit": s["bit"]}
        x["en_uzun"] = max(x["en_uzun"], blok["bit"] - blok["bas"])
        onceki = {"ad": ad, "bit": s["bit"]}
    for x in o.values():
        x["pay"] = round(100 * x["sn"] / toplam) if toplam else 0
        x["sn"] = round(x["sn"]); x["en_uzun"] = round(x["en_uzun"])
    return o


def _gecmis(n=6):
    try:
        return json.loads(_gecmis_yolu().read_text(encoding="utf-8"))[-n:]
    except Exception:  # noqa: BLE001
        return []


def _gecmise_ekle(veri, d):
    try:
        g = json.loads(_gecmis_yolu().read_text(encoding="utf-8")) if _gecmis_yolu().exists() else []
    except Exception:  # noqa: BLE001
        g = []
    baslik = veri.get("baslik") or ""
    g = [x for x in g if x.get("baslik") != baslik]
    g.append({"zaman": time.time(), "baslik": baslik, "musteri": veri.get("musteri") or "",
              "dersler": [x.get("baslik") or x.get("ders") or "" for x in d.get("dersler") or []][:3],
              "aksiyonlar": [a.get("ne") for a in d.get("aksiyonlar") or []][:4],
              "kalip": [a.get("daha_iyi", "")[:140] for a in d.get("anlar") or []][:3]})
    _gecmis_yolu().parent.mkdir(parents=True, exist_ok=True)
    _gecmis_yolu().write_text(json.dumps(g[-60:], ensure_ascii=False, indent=1), encoding="utf-8")


def uret(veri, segmentler, log=print):
    import claude_yaz
    from transkript import paragrafla
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(segmentler, etiket)
    if not par:
        return None
    ben = _ben()
    olcu = olculer(segmentler, etiket)
    metin = "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in par)
    olcu_metin = "\n".join(f"- {ad}: %{x['pay']} ({x['sn'] // 60} dk {x['sn'] % 60} sn), {x['soru']} soru, en uzun kesintisiz {x['en_uzun']} sn, "
                           f"~{x['kesme']} kez başkası konuşurken söze girdi" for ad, x in sorted(olcu.items(), key=lambda kv: -kv[1]["sn"]))
    gecmis = [g for g in _gecmis(8) if g.get("baslik") != (veri.get("baslik") or "")][-6:]   # aynı toplantının eski notu 'geçen sefer' sayılmasın
    gecmis_metin = "\n".join(f"- {time.strftime('%d.%m', time.localtime(g['zaman']))} {g['baslik'][:60]}: dersler: {'; '.join(g['dersler'])} | "
                             f"aksiyonlar: {'; '.join(a for a in g['aksiyonlar'] if a)}" for g in gecmis)
    ilk_ad = ben.split()[0] if ben else ""
    istem = (
        f"Sen deneyimli, sıcak ama dürüst bir kariyer danışmanı ve iletişim koçusun. Danışanın {ben or 'kullanıcı'}: "
        f"{__import__('ortak').kimlik()['kimlik'][:300] or 'markalarla çalışan serbest bir yaratıcı (ajans tarafında kreatif, içerik ve strateji işleri yapıyor)'}. Aşağıdaki toplantıyı dinledin.\n\n"
        f"Toplantı: {veri.get('baslik') or ''}\nMüşteri: {veri.get('musteri') or 'belirtilmemiş'}\n"
        f"Konuşmacı etiketleri: {', '.join(sorted({p['ad'] for p in par}))}\n"
        + (f"Danışan transkriptte '{ilk_ad}' adıyla ya da adı konmamış bir 'Konuşmacı N' etiketiyle geçebilir; ona hitap edilmesinden, "
           "üstlendiği işlerden çıkar. Emin değilsen bunu belirt.\n" if ilk_ad else "")
        + f"\nÖLÇÜLER (kodla hesaplandı):\n{olcu_metin}\n"
        + (f"\nÖNCEKİ TOPLANTILARDAKİ NOTLARIN (süreklilik için; ilerleme ya da tekrar eden kalıp varsa söyle):\n{gecmis_metin}\n" if gecmis_metin else "")
        + ("\nTOPLANTI SIRASINDA KULAĞINA FISILDANANLAR (canlı mentör kartları; [dk:sn] ve kart). Uyguladı mı, uygulamadı mı, sonucu ne oldu? Önemliyse "
           "'anlar' ya da 'baglanti' içinde söyle ('Toplantıda sana X dedim, Y'yi yaptın ve Z oldu'); uygulamadıysa yargılamadan nedenini düşün:\n"
           + "\n".join(f"- [{int(k.get('sn', 0)) // 60:02d}:{int(k.get('sn', 0)) % 60:02d}] {k.get('tur')}: "
                        + (f"{k.get('gozlem')} → {k.get('yap')}" if k.get("tur") == "mentor" else (k.get("soyle") or k.get("metin") or ""))
                        for k in (veri.get("canli_kartlar") or [])[-12:]) + "\n" if veri.get("canli_kartlar") else "")
        + "\nGÖREV: Danışana kişisel bir not yaz. Bu not telefonda 60 saniyede okunacak; her kelime iş görmeli.\n"
        "SES: Yıllardır yanında olan, onu çok iyi tanıyan kıdemli bir akıl hocası gibi yaz: sıcak, doğrudan, 'sen' diye. Yargılamadan, "
        "ama lafı dolandırmadan. Klişe yok ('iletişim önemlidir', 'kendine güven', 'harika iş çıkardın'). Kurumsal dil yok. Çeviri kokan kalıp yok "
        "('bu bağlamda', 'göz önünde bulundurarak', 'önem arz ediyor'). Tahmin yürütürken 'galiba', 'bence' gibi insanca yaz.\n"
        "UZUNLUK KURALLARI (kesin):\n"
        "- ozet: EN FAZLA 2 cümle, toplam 35 kelimeyi geçmesin. Toplantının senin için anlamı; özet değil, yorum.\n"
        "- anlar: 2-3 an. ne_oldu: en fazla 25 kelime, içinde kısa birebir alıntı (tırnakla). daha_iyi: O AN söyleyebileceği TEK cümle, "
        "kendi ağzından, tırnaksız, en fazla 25 kelime. neden: en fazla 18 kelime, somut sonuç ('tarihi sen koyarsın, yük sana kalmaz' gibi).\n"
        "- guclu: 1-2 madde, her biri en fazla 20 kelime, alıntılı.\n"
        "- firsatlar: 1-2 fırsat (en değerlileri). baslik: en fazla 6 kelime, isim cümlesi değil eylem ('Kapsam kaymasını fiyatlandır'). "
        "neden: en fazla 22 kelime, toplantıdaki dayanakla. adimlar: tam 2 adım, her biri en fazla 14 kelime, emir kipi.\n"
        "- dersler: 1-2 kısa ders, her biri en fazla 16 kelime; başlık + tek cümle.\n"
        "- aksiyonlar: 2-3 madde, her biri en fazla 12 kelime, emir kipiyle başlasın ('Ayşe'ye cuma teslimini yaz'); ne_zaman varsa kısa ('bugün', 'cuma').\n"
        "- baglanti: önceki notlarla gerçek bir bağ varsa tek cümle (en fazla 22 kelime), yoksa boş.\n"
        "DOĞRULUK: Her gözlem konuşmadaki somut bir ana dayansın; alıntılar birebir transkriptten. [dk:sn] zamanı 'zaman' alanına yazılır, metnin içine yazma. "
        "Danışan neredeyse hiç konuşmadıysa bunu söyle ve dinleyici rolüne göre değerlendir. Kim olduğu belirsizse 'siz' alanına tahminini yaz, 'emin' false.\n"
        'Yalnızca JSON: {"siz": "danışanın etiketi", "emin": true, "ozet": "...", '
        '"anlar": [{"zaman": "12:34", "ne_oldu": "...", "daha_iyi": "...", "neden": "..."}], "guclu": [{"zaman": "03:10", "ne": "..."}], '
        '"firsatlar": [{"baslik": "...", "neden": "...", "adimlar": ["...", "..."]}], "dersler": [{"baslik": "...", "ders": "..."}], '
        '"aksiyonlar": [{"ne": "...", "ne_zaman": "..."}], "baglanti": ""}\n\nTRANSKRİPT:\n' + metin[:230000])
    model = claude_yaz._ayar().get("claude_model_yazi") or "opus"
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            log("      Danışman notu atlandı (Claude kullanılamıyor)"); return None
        c = claude_yaz.json_coz(claude_yaz.sor(istem, "Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun.", zaman_asimi=600, model_adi=model))
    if not c or not (c.get("ozet") or c.get("anlar")):
        log("      Danışman notu üretilemedi"); return None
    for f in c.get("firsatlar") or []:
        if not f.get("adimlar") and f.get("nasil"):
            f["adimlar"] = [x.strip(" .") for x in re.split(r"\d\)\s*|;\s*", f["nasil"]) if x.strip(" .")][:2]
    for a in (c.get("anlar") or []) + (c.get("guclu") or []):
        m = re.match(r"^\s*(\d{1,3}):(\d{2})", str(a.get("zaman") or ""))
        a["sn"] = int(m.group(1)) * 60 + int(m.group(2)) if m else None
    c.update({"zaman": time.time(), "model": f"claude:{model}", "olculer": olcu})
    _gecmise_ekle(veri, c)
    log(f"      Danışman notu hazır ({len(c.get('anlar') or [])} an, {len(c.get('firsatlar') or [])} fırsat, {len(c.get('aksiyonlar') or [])} aksiyon)")
    return c


def metin(d):
    """Düz metin (txt ve kopyalama için)."""
    if not d:
        return ""
    s = ["Kişisel: Kariyer danışmanı notu", "", d.get("ozet", "")]
    if d.get("baglanti"):
        s += ["", "Geçen seferlerden: " + d["baglanti"]]
    if d.get("anlar"):
        s += ["", "Daha iyi olabilirdi"]
        for a in d["anlar"]:
            s += [f"  [{a.get('zaman', '')}] {a.get('ne_oldu', '')}", f"    Şöyle deneyebilirdin: {a.get('daha_iyi', '')}", f"    Neden: {a.get('neden', '')}"]
    if d.get("guclu"):
        s += ["", "İyi giden"] + [f"  [{g.get('zaman', '')}] {g.get('ne', '')}" for g in d["guclu"]]
    if d.get("firsatlar"):
        s += ["", "Fırsatlar"]
        for f in d["firsatlar"]:
            s += [f"  {f.get('baslik', '')}: {f.get('neden', '')}"] + [f"    → {a}" for a in (f.get("adimlar") or ([f["nasil"]] if f.get("nasil") else []))]
    if d.get("dersler"):
        s += ["", "Dersler"] + [f"  {x.get('baslik', '')}: {x.get('ders', '')}" for x in d["dersler"]]
    if d.get("aksiyonlar"):
        s += ["", "Bu hafta yap"] + [f"  ☐ {a.get('ne', '')}" + (f" ({a['ne_zaman']})" if a.get("ne_zaman") else "") for a in d["aksiyonlar"]]
    return "\n".join(s) + "\n"

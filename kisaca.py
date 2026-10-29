"""kisaca.py - Toplantı sayfasının en üstündeki kart (2026-10-20): 1-2 paragraflık özet + kişi kişi yapılacaklar.

Kullanıcı: "Her toplantının sayfasında 1-2 paragraflık özet + her kişi için yapılacaklar listesi görülebilsin." Eski notlardaki yapılacaklar
yerel modelle üretildiği için bazı kayıtlarda alanları karışıktı (iş yerine kişi adı); bu kart her zaman Claude'la, tek çağrıda, transkriptin
tamamından üretilir. `veri["kisaca"] = {ozet: [paragraf], kisiler: [{ad, isler: [{is, ne_zaman, sn, bitti}]}], belirsiz: [...], zaman, model}`.
Toplantı bitince kendiliğinden; eski toplantılarda sayfa ilk açıldığında. İşaretlenen işler `bitti` olarak saklanır.
"""
import json
import re
import time


def _sn(z):
    m = re.match(r"^\s*(?:(\d+):)?(\d{1,3}):(\d{2})\s*$", str(z or ""))
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def uret(veri, segmentler, log=print):
    import claude_yaz
    import ozet as ozet_modulu
    from transkript import paragrafla
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(segmentler, etiket)
    if not par:
        return None
    metin = "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in par)
    kisiler = sorted({p["ad"] for p in par})
    try:
        import notlarim
        ek = notlarim.istem_ek(veri)
    except Exception:  # noqa: BLE001
        ek = ""
    try:
        from pathlib import Path
        import claude_yaz
        m = claude_yaz.MISAFIR.get()                         # davetli: kendi adı (sahibin adı davetlinin toplantısına girmez)
        ben = (m.get("ad") or "").strip() if m else (json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8")).get("benim_adim") or "").strip()
    except Exception:  # noqa: BLE001
        ben = ""
    katilimci = ", ".join(veri.get("katilimcilar") or [])
    istem = (
        f"Toplantı: {veri.get('baslik') or ''}\nKonuşmacı etiketleri: {', '.join(kisiler)}\n"
        + (f"Takvim/toplantı katılımcıları: {katilimci}\n" if katilimci else "")
        + (f"Kullanıcının adı: {ben} (onun işleri ayrıca önemli)\n" if ben else "") + ek
        + "\nBu toplantıyı aşağıdaki parçalara AYIR. Konuşulan, önerilen, kararlaştırılan ve üstlenilen şeyler birbirine KARIŞMASIN (2026-10-23):\n"
        "1) ozet: 1 ya da 2 paragraf (her biri 3-5 cümle). Toplantıyı kaçırmış birine ne konuşuldu, ne karar verildi, nerede kalındı. "
        "Somut, isim ve sayılarla; genel laf yok; çeviri kokan kalıplar yok.\n"
        "2) kararlar: YALNIZCA açıkça kararlaştırılan ya da onaylanan şeyler ('tamam, öyle yapalım', 'bunu çıkarıyoruz'). karar (tek cümle), kim (kararı "
        "veren/onaylayan, söylendiyse; yoksa boş), zaman [dk:sn], alinti (kararın söylendiği BİREBİR söz, ≤20 kelime, transkriptten kopyala).\n"
        "3) kisiler: her kişinin ÜSTLENDİĞİ işler (taahhüt: 'ben yaparım', 'atarım', 'bakarım') ya da kendisinden istenip KABUL ETTİĞİ işler. 'Bunu "
        "yapabiliriz', 'belki', 'şöyle de olabilir' görev DEĞİLDİR (onlar öneri). Kişi adı konuşmacı etiketlerinden ya da katılımcılardan birebir. Her iş: "
        "kısa emir cümlesi, ne_zaman YALNIZCA açıkça söylendiyse (yoksa boş; TAHMİN ETME), zaman [dk:sn], alinti (BİREBİR söz, ≤20 kelime).\n"
        "4) belirsiz: yapılacağı söylenen ama SORUMLUSU söylenmemiş işler (aynı alanlarla). Sorumluyu tahmin etme.\n"
        "5) oneriler: konuşulan ama karara ya da taahhüde dönmemiş fikirler/öneriler: oneri, kim, zaman.\n"
        "6) acik_sorular: cevaplanmadan kalan sorular: soru, kime (söylendiyse), zaman.\n"
        + (f"7) senden_karar: {ben.split()[0]}'in KARAR VERMESİ ya da onaylaması beklenen konular (ona yöneltilmiş ve cevapsız kalan seçimler): konu, zaman, alinti.\n" if ben else "")
        + "Aynı şeyi iki listeye koyma. Uydurma.\n"
        # 2026-10-25 (kullanıcının X yer imlerinden, Karpathy: kontrollü dil, ASD-STE100): karar ve iş metinleri yanlış anlaşılmasın, Asana'ya net gitsin
        "SADE YAZIM (kararlar, işler, belirsiz, öneriler, açık sorular; özet paragrafları HARİÇ, onlar doğal Türkçe kalır): her madde TEK cümle, en çok "
        "20 kelime; etken çatı ve özne açık ('Ayşe sunumu gönderecek'; 'sunum gönderilecek' değil); 'bu', 'şu iş', 'o konu' gibi belirsiz gönderme yok, "
        "neyin kastedildiği adıyla yazılır; kim, ne, ne zaman söylendiyse metinde açık; iş metni emir kipindeki fiille biter. KISALIK BAĞLAMI SİLMEZ: işin "
        "neye dayandığı ve ne için olduğu kalır ('Müşterinin yorumuna göre son akışı gözden geçir', 'Kısa filmin finaline cihazın onarıldığını anlatan süper "
        "ekle'); bir iş birden çok maddeye bölünmez. Toplantıda geçen terim ve kısaltma olduğu gibi kalır, süsleme eklenmez.\n"
        'Yalnızca JSON: {"ozet": ["paragraf"], "kararlar": [{"karar": "...", "kim": "", "zaman": "12:34", "alinti": "..."}], '
        '"kisiler": [{"ad": "...", "isler": [{"is": "...", "ne_zaman": "", "zaman": "12:34", "alinti": "..."}]}], '
        '"belirsiz": [{"is": "...", "ne_zaman": "", "zaman": "12:34", "alinti": "..."}], "oneriler": [{"oneri": "...", "kim": "", "zaman": "12:34"}], '
        '"acik_sorular": [{"soru": "...", "kime": "", "zaman": "12:34"}], "senden_karar": [{"konu": "...", "zaman": "12:34", "alinti": "..."}]}\n\nTRANSKRİPT:\n' + metin[:240000])
    with claude_yaz.toplanti() if veri.get("toplanti") else _bos():
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=16384, zaman_asimi=600)) or {}

    def isler(lst):
        out = []
        for i in lst or []:
            if isinstance(i, dict) and str(i.get("is") or "").strip():
                sn = _sn(i.get("zaman")); al = str(i.get("alinti") or "").strip()[:240]
                out.append({"is": str(i["is"]).strip(), "ne_zaman": str(i.get("ne_zaman") or "").strip(), "sn": sn, "bitti": False,
                            "alinti": al, "alinti_dogru": alinti_var(al, par, sn)})
        return out

    def liste(lst, alan, *ek):
        out = []
        for x in lst or []:
            if isinstance(x, dict) and str(x.get(alan) or "").strip():
                sn = _sn(x.get("zaman")); al = str(x.get("alinti") or "").strip()[:240]
                out.append({alan: str(x[alan]).strip(), **{e: str(x.get(e) or "").strip() for e in ek}, "sn": sn,
                            **({"alinti": al, "alinti_dogru": alinti_var(al, par, sn)} if al else {})})
        return out
    kisi_listesi = [{"ad": str(k.get("ad") or "").strip(), "isler": isler(k.get("isler"))} for k in (c.get("kisiler") or []) if isinstance(k, dict)]
    kisi_listesi = [k for k in kisi_listesi if k["ad"] and k["isler"]]
    if ben:                                                   # kullanıcının işleri en üstte
        ilk = ben.split()[0].lower()
        kisi_listesi.sort(key=lambda k: 0 if k["ad"].lower().split()[0] == ilk else 1)
    paragraflar = [str(p).strip() for p in (c.get("ozet") or []) if str(p).strip()][:2]
    if not paragraflar:
        log("      Kısa özet üretilemedi"); return None
    log(f"      Kısa özet ve kişi kişi işler hazır ({sum(len(k['isler']) for k in kisi_listesi)} iş, {len(kisi_listesi)} kişi)")
    k = {"ozet": paragraflar, "kisiler": kisi_listesi, "belirsiz": isler(c.get("belirsiz")), "kararlar": liste(c.get("kararlar"), "karar", "kim"),
         "oneriler": liste(c.get("oneriler"), "oneri", "kim"), "acik_sorular": liste(c.get("acik_sorular"), "soru", "kime"),
         "senden_karar": liste(c.get("senden_karar"), "konu"), "surum": 2, "zaman": time.time(), "model": ozet_modulu.SON_MODEL}
    try:
        musteri_ata(k, veri, metin, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"      Maddeler müşterilere ayrılamadı ({e})")
    return k


# Çok müşterili toplantı (2026-10-28; kullanıcı: "çok müşterili toplantılarda kararları ve işleri madde madde doğru müşteriye ayır; Asana'ya da her işi
# kendi müşteri projesine gönder"). 26 Ekim haftalık oturumunda 13 kişi, 20 iş ve birkaç müşteri vardı; hepsi toplantının tek müşterisine
# yazılmıştı. Toplantıda en az iki müşterinin adı geçiyorsa tek ek çağrıyla her madde (karar, iş, sorumsuz iş, öneri, açık soru) bir müşteriye bağlanır:
# madde["musteri"]; kisaca["musteriler"] = madde sayısına göre [{ad, adet}]. Müşteri adı yalnız ayarlardaki listeden (şirketin müşterileri);
# emin olunmayan ya da ajansın kendi işi olan madde boş kalır. Davetli toplantısında çalışmaz (sahibin müşteri listesi oraya girmez).
def _musteri_adaylari(veri):
    try:
        import claude_yaz
        if claude_yaz.MISAFIR.get():
            return []
        import ortak
        ay = ortak.ayar()
    except Exception:  # noqa: BLE001
        return []
    S = [s for s in ay.get("sirketler") or [] if isinstance(s, dict)]
    sk = veri.get("sirket") or ""
    secili = [s for s in S if s.get("kod") == sk] or S
    sirket_adlari = {str(s.get("ad") or "").casefold() for s in S} | {str(s.get("kod") or "").casefold() for s in S}
    out = []
    for m in [m for s in secili for m in (s.get("musteriler") or [])] + list(ay.get("musteriler") or []):
        if m and m.casefold() not in sirket_adlari and m.casefold() not in {o.casefold() for o in out}:
            out.append(m)
    return out


def _gecen_musteriler(metin, adaylar):
    t = str(metin or "").casefold()
    return [m for m in adaylar if re.search(r"(?<!\w)" + re.escape(m.casefold()), t)]


def musteri_ata(k, veri, metin, log=print, zorla=False):
    """Kısaca maddelerini müşterilere bağlar (yerinde). Döner: etiketlenen madde sayısı. Toplantıda ≥2 müşteri adı geçmiyorsa (zorla değilse) atlanır."""
    import claude_yaz
    import ozet as ozet_modulu
    adaylar = _musteri_adaylari(veri)
    gecen = _gecen_musteriler(str(veri.get("baslik") or "") + "\n" + metin, adaylar)
    if len(gecen) < 2 and not zorla:
        return 0
    maddeler = []                                          # (kod, sözlük, metin)
    for i, x in enumerate(k.get("kararlar") or []):
        maddeler.append((f"K{i + 1}", x, x.get("karar")))
    for ki, p in enumerate(k.get("kisiler") or []):
        for ii, x in enumerate(p.get("isler") or []):
            maddeler.append((f"I{ki + 1}.{ii + 1}", x, f"{x.get('is')} (sorumlu: {p.get('ad')})"))
    for i, x in enumerate(k.get("belirsiz") or []):
        maddeler.append((f"B{i + 1}", x, x.get("is")))
    for i, x in enumerate(k.get("oneriler") or []):
        maddeler.append((f"O{i + 1}", x, x.get("oneri")))
    for i, x in enumerate(k.get("acik_sorular") or []):
        maddeler.append((f"S{i + 1}", x, x.get("soru")))
    if not maddeler:
        return 0
    zt = lambda sn: f"[{int(sn) // 60:02d}:{int(sn) % 60:02d}] " if sn is not None else ""   # noqa: E731
    istem = (f"Toplantı: {veri.get('baslik') or ''}\nAjansın müşterileri (YALNIZ bu adlar kullanılabilir): {', '.join(adaylar)}\n"
             f"Bu toplantıda adı geçenler: {', '.join(gecen)}\n\n"
             "Bu toplantıda birden çok müşterinin işi konuşuldu. Aşağıdaki her maddenin HANGİ MÜŞTERİNİN işi olduğunu transkripte bakarak bul. "
             "Maddenin zamanındaki ve hemen öncesindeki konuşma hangi müşteriyi konuşuyorsa o. Adı maddede geçmese de bağlamdan belliyse yaz. "
             "Emin değilsen, madde birden çok müşteriyi kapsıyorsa ya da ajansın kendi iç işiyse (ekip düzeni, araç, izin, genel süreç) BOŞ bırak. "
             "Listede olmayan ad yazma, tahmin etme.\n"
             'Yalnızca JSON: {"etiket": {"K1": "<müşteri adı>", "I1.2": "", ...}} (her kod için)\n\nMADDELER:\n'
             + "\n".join(f"{kod} {zt(x.get('sn'))}{t}" for kod, x, t in maddeler) + "\n\nTRANSKRİPT:\n" + metin[:200000])
    with claude_yaz.toplanti() if veri.get("toplanti") else _bos():
        if not claude_yaz.hazir():
            return 0
        c = claude_yaz.sor_json(istem, model_adi="sonnet", zaman_asimi=300) or {}
    E = c.get("etiket") or {}
    kanon = {m.casefold(): m for m in adaylar}
    sayac = {}
    n = 0
    for kod, x, _t in maddeler:
        ad = kanon.get(str(E.get(kod) or "").strip().casefold(), "")
        if ad:
            x["musteri"] = ad; n += 1; sayac[ad] = sayac.get(ad, 0) + 1
        else:
            x.pop("musteri", None)
    k["musteriler"] = [{"ad": a, "adet": s} for a, s in sorted(sayac.items(), key=lambda z: -z[1])]
    if n:
        log("      Maddeler müşterilere ayrıldı: " + ", ".join(f"{a} {s}" for a, s in sorted(sayac.items(), key=lambda z: -z[1])))
    return n


def _norm(t):
    return re.findall(r"[a-zçğıöşü0-9]+", str(t or "").replace("İ", "i").replace("I", "ı").lower())


def alinti_var(alinti, par, sn=None):
    """Alıntı transkriptte geçiyor mu (kodla): kelimelerinin ≥%75'i, verilen zamanın ±90 sn'sindeki paragraflarda (zaman yoksa her yerde)."""
    k = _norm(alinti)
    if len(k) < 3:
        return False
    havuz = set()
    for p in par:
        if sn is None or abs(p["bas"] - sn) <= 90 or (p["bas"] <= sn <= p.get("bit", p["bas"]) + 1):
            havuz |= set(_norm(p["metin"]))
    return sum(1 for w in k if w in havuz) / len(k) >= 0.75


class _bos:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

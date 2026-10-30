"""meet_gelisim.py - Meet'in kendini besleyen gelişim döngüsü (2026-10-24; kullanıcı: "kendi kendini besleyen, sürekli gelişen, sürekli yeni
özellikleri, gelişmeleri, güncellemeleri takip eden bir yapıya kavuştur").

Neden: 7 toplantının 6'sında adsız konuşmacı kalmıştı, biri "Display 3 Backstop" adıyla Drive'a gitmişti; hiçbiri kendiliğinden fark edilmedi.

1) ÖLÇER   `olcum(gun)`: adsız konuşmacı, "Diğer" müşteri, başlık kaynağı, doğrulanamayan alıntı, sizi tanıma oranı, eksik adım, canlı kart,
            uzantıdan gelen ad. Haftalık anlık görüntüler `rapor.gecmis`'te (eğilim).
2) DENETLER `saglik()`: kaydedici, Chrome uzantısı (sürüm, nabız, okuma), takvim + e-posta davetleri, Asana, Drive, disk, Claude, son toplantıların adımları.
3) ONARIR  (site, sunucu/20_meet_gelisim.py): eksik adımı tamamlar, kötü başlığı yeniden adlandırır, yeni öğrenilen sesleri eski toplantılara uygular
            (`geriye_donuk_tani`), katılımcı listesiyle eleyerek ad verir (`eleme`), karşı tarafın gecikmiş sözlerini sonraki toplantılarda arar
            (`soz_kontrol`). Her onarım `olaylar`'a yazılır.
4) ÖĞRENİR `duzeltme_kaydet`: kullanıcının toplantı adı / şirket / müşteri / konuşmacı düzeltmeleri → toplantı adı isteminde örnek (`ad_blogu`).
5) İZLER   `radar()` haftada bir: Google Meet / Teams / Zoom güncellemeleri (sayfa yapısı değişirse uzantı kırılabilir), toplantı notu ürünlerinin
            yenilikleri, kullanılan ses araçlarının yeni sürümleri (PyPI) ve yeni Türkçe ses modelleri → sonnet süzgeci → uyarı ya da öneri.
6) DÜŞÜNÜR `ozdegerlendirme()` haftada bir (opus): ölçüm + düzeltmeler + onarımlar + radar → kısa değerlendirme, dersler (toplantı adı istemine
            girer) ve öneriler. Kod değişikliği gerektiren öneriler kullanıcının onayına gider (Meet → Durum); kabul edilenler sonraki Claude Code
            oturumunun iş listesidir. Kod kendini DEĞİŞTİRMEZ.
"""
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
KAYIT = KLASOR / "kayitlar"
DOSYA = KLASOR / "profil" / "meet_gelisim.json"
ADSIZ = re.compile(r"^Konuşmacı \d+$")
ESIK_GERIYE = 0.72          # geriye dönük tanıma: yeni toplantıdakinden (0,6) sıkı; yanlış ad eskiyi bozar
FARK_GERIYE = 0.10          # en iyi ile ikinci aday arasında en az bu kadar fark
EN_AZ_KONUSMA = 30.0        # sn; bundan az konuşan küme adlandırılmaz (hayalet olabilir)
TURETILMIS = ("kisaca", "notlar", "danisman", "sinyaller", "ozet", "ad_onerileri", "canli_kartlar", "notlarim", "brief", "takip_eposta")
MEVCUT = ("otomatik toplantı kaydı (Zoom/Teams/Google Meet/FaceTime), Chrome uzantısı (katılımcı adları, kim konuşuyor, yan panel), canlı yazıya dökme, "
          "toplantı sırasında fısıltı (hatırlatma, öneri, mentör), konuşmacı ayırma ve ses izinden tanıma, Kısaca (kararlar, kim ne yapacak, alıntı kanıtı), "
          "karar zinciri, toplantı notları e-postası, kariyer danışmanı notu, tarifler, toplantıyla sohbet, sesli özet, şirket/müşteri sınıflama, Drive'a dosyalama, "
          "Asana'ya görev, takvimden hazırlık notu, sinyaller (amaç, kapsam, kırılma, tahmin), kişi profilleri, telefon kaydı yükleme, haftalık müşteri özeti")


# ---------------------------------------------------------------- kayıt
def oku():
    try:
        d = json.loads(DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        d = {}
    for k, v in (("olaylar", []), ("duzeltmeler", []), ("oneriler", []), ("dersler", []), ("radar", {}), ("rapor", {}), ("son", {}), ("soz_bakilan", {})):
        d.setdefault(k, v)
    return d


def yaz(d):
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    d["olaylar"] = d["olaylar"][-300:]; d["duzeltmeler"] = d["duzeltmeler"][-200:]
    tmp = DOSYA.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DOSYA)


def olay(tur, metin, temel="", **ek):
    """Kendiliğinden yapılan bir iş (onarım, öğrenme, uyarı) kayda geçer; arayüz "Kendiliğinden yapılanlar"da gösterir."""
    d = oku()
    d["olaylar"].append({"zaman": time.time(), "tur": tur, "metin": metin, "temel": temel, **ek})
    yaz(d)


def son(ad, zaman=None):
    d = oku()
    if zaman is None:
        return d["son"].get(ad, 0)
    d["son"][ad] = zaman; yaz(d)
    return zaman


def _ayar():
    try:
        return json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------- toplantılar
_TOPLANTI_ONB = {}                 # yol -> (mtime, boyut, d): Meet durumu her açılışta 14 MB'ı baştan ayrıştırıyordu (~1 sn)


def _toplanti_oku(js):
    st = js.stat()
    o = _TOPLANTI_ONB.get(js)
    if o and o[0] == st.st_mtime and o[1] == st.st_size:
        return o[2]
    d = json.loads(js.read_text(encoding="utf-8"))
    _TOPLANTI_ONB[js] = (st.st_mtime, st.st_size, d)
    return d


def toplantilar(gun=30):
    """[(json yolu, veri, segmentler)] son N günün toplantıları (onay bekleyenler hariç), yeniden eskiye. Dosya değişmedikçe bellekten.
    DİKKAT: dönen veri önbellektedir; değiştirecek olan kopyalasın (yazanlar zaten dosyayı yeniden okuyor)."""
    sinir = time.time() - gun * 86400
    out = []
    try:                                                     # önce hafif önbellekle (yalnız `veri`) toplantılar seçilir; tam dosya yalnız onlar için
        import kitaplik_onbellek
        adaylar = [Path(x["yol"]) for x in kitaplik_onbellek.hepsi() if (x.get("veri") or {}).get("toplanti") and (x.get("mtime") or 0) >= sinir]
    except Exception:  # noqa: BLE001
        adaylar = list(KLASOR.glob("transkript_*.json"))
    for js in adaylar:
        try:
            if js.stat().st_mtime < sinir:
                continue
            d = _toplanti_oku(js)
        except Exception:  # noqa: BLE001
            continue
        v = d.get("veri") or {}
        if not v.get("toplanti") or v.get("onay_bekliyor") or v.get("misafir") or (v.get("olusturma") or js.stat().st_mtime) < sinir:   # davetli kayıtları sahibin değil
            continue
        out.append((js, v, d.get("segmentler") or []))
    out.sort(key=lambda x: -(x[1].get("olusturma") or 0))
    return out


def konusma_sureleri(segmentler):
    sure = {}
    for s in segmentler:
        k = str(s.get("k"))
        sure[k] = sure.get(k, 0.0) + max(0.0, float(s.get("bit", 0)) - float(s.get("bas", 0)))
    return sure


def adsizlar(veri, segmentler, en_az=EN_AZ_KONUSMA):
    """Adı konmamış ve yeterince konuşmuş küme anahtarları."""
    sure = konusma_sureleri(segmentler)
    return [k for k, ad in (veri.get("etiket") or {}).items() if ADSIZ.match(str(ad)) and sure.get(str(k), 0) >= en_az]


def etiket_yay(veri, eski, yeni):
    """Konuşmacı adı değişince türetilmiş alanlardaki (Kısaca, notlar, danışman, sinyaller...) eski etiketi de değiştirir.
    isimlendir.py yalnızca etiketi değiştiriyordu; 'Kim ne yapacak' "Konuşmacı 2" adına kalıyor, Asana'ya iş gitmiyordu."""
    desen = re.compile(re.escape(eski) + r"(?!\d)")
    for f in TURETILMIS:
        if veri.get(f):
            try:
                s = json.dumps(veri[f], ensure_ascii=False)
                if eski in s:
                    veri[f] = json.loads(desen.sub(yeni.replace("\\", " ").replace('"', "'"), s))
            except Exception:  # noqa: BLE001
                pass


def _ilk(ad):
    return str(ad or "").strip().split(" ")[0].casefold()


# ---------------------------------------------------------------- konuşmacı adları
def taninani_dogrula(veri, log=print):
    """Sesinden tanınan ad toplantının katılımcı listesinde yoksa geri alınır (2026-10-27: bir toplantıda katılımcılar arasında olmayan
    bir ad sesten verildi). Yalnız liste güvenilirse (≥3 katılımcı): eksik listede doğru tanımayı silmemek için.
    Kullanıcının kendi adına dokunulmaz. Döner: geri alınan adlar."""
    kat = [str(a) for a in (veri.get("katilimcilar") or []) if str(a).strip()]
    kat += [k.get("ad") or "" for k in ((veri.get("takvim") or {}).get("katilimcilar") or []) if isinstance(k, dict)]
    ilkler = {_ilk(a) for a in kat if a}
    if len(ilkler) < 3:
        return []
    ben = _ilk(_ayar().get("benim_adim"))
    geri = []
    for k, ad in list((veri.get("etiket") or {}).items()):
        if ad in (veri.get("taninan") or []) and _ilk(ad) not in ilkler and _ilk(ad) != ben:
            try:
                veri["etiket"][k] = f"Konuşmacı {int(k) + 1}"
            except ValueError:
                veri["etiket"][k] = "Konuşmacı"
            geri.append(ad)
    if geri:
        veri["taninan"] = [a for a in veri.get("taninan") or [] if a not in geri]
        log("      Sesten verilen ad katılımcılarda yok, geri alındı: " + ", ".join(geri))
    return geri


def eleme(veri, segmentler, log=lambda *_: None):
    """Katılımcı listesiyle eleme ve ad önerisi teyidi. Döner: {k: ad}. Yalnızca kesin durumlarda:
    1) adsız TEK küme kaldıysa, adı geçen katılımcılardan eşleşmemiş TEK kişi kaldıysa ve konuşan küme sayısı = katılımcı sayısı ise o kişi;
    2) adlar.py önerisi (güven ≥ 0,75) katılımcı listesindeki biriyle aynı ilk adı taşıyorsa ve o ad başka kümede yoksa."""
    try:
        import kisiler as kisiler_modulu
        ad_mi = kisiler_modulu.ad_mi
    except Exception:  # noqa: BLE001
        def ad_mi(a):
            return bool(str(a).strip())
    etiket = veri.get("etiket") or {}
    sure = konusma_sureleri(segmentler)
    konusan = [k for k in etiket if sure.get(str(k), 0) >= EN_AZ_KONUSMA]
    adlilar = {_ilk(a) for a in etiket.values() if not ADSIZ.match(str(a))}
    katil = []
    for a in veri.get("katilimcilar") or []:
        a = re.sub(r"\s*\(.*?\)\s*$", "", str(a)).strip()
        if a and ad_mi(a) and _ilk(a) not in {_ilk(x) for x in katil}:
            katil.append(a)
    sonuc = {}
    # 2) ad önerisi + katılımcı listesi
    for o in veri.get("ad_onerileri") or []:
        k = next((kk for kk, v in etiket.items() if v == o.get("etiket")), None)
        if k is None or not ADSIZ.match(str(etiket.get(k))) or float(o.get("guven") or 0) < 0.75:
            continue
        kisi = next((a for a in katil if _ilk(a) == _ilk(o.get("ad"))), None)
        if kisi and _ilk(kisi) not in adlilar and kisi not in sonuc.values():
            sonuc[k] = kisi; adlilar.add(_ilk(kisi))
            log(f"      Ad önerisi katılımcı listesiyle doğrulandı: {o.get('etiket')} → {kisi}")
    # 1) eleme
    adsiz = [k for k in konusan if ADSIZ.match(str(etiket.get(k))) and k not in sonuc]
    kalan = [a for a in katil if _ilk(a) not in adlilar]
    if len(adsiz) == 1 and len(kalan) == 1 and katil and len(konusan) == len(katil):
        sonuc[adsiz[0]] = kalan[0]
        log(f"      Katılımcı listesinden eleyerek: {etiket.get(adsiz[0])} → {kalan[0]}")
    return sonuc


def geriye_donuk_tani(gun=60):
    """Kayıtlı ses profilleriyle eski toplantılardaki adsız kümeleri eşleştirir (sıkı eşik + fark şartı). Döner: [(json yolu, {k: ad}, {k: benzerlik})]."""
    import sesler as sesler_modulu
    profiller = sesler_modulu.toplanti_profilleri()          # videolardan öğrenilen sesler toplantılara verilmez
    if not profiller:
        return []
    ben = _ilk(_ayar().get("benim_adim"))                 # kullanıcının adını taşıyan birden çok profil varsa yalnız en çok doğrulanmışı
    benler = sorted((p for p in profiller if ben and _ilk(p) == ben), key=lambda p: -int(profiller[p].get("sayac", 1)))
    for p in benler[1:]:
        profiller.pop(p, None)
    out = []
    for js, v, segs in toplantilar(gun):
        izler = v.get("sesler") or {}
        adsiz = [k for k in adsizlar(v, segs) if k in izler]
        if not adsiz:
            continue
        kullanilan = {_ilk(a) for a in (v.get("etiket") or {}).values() if not ADSIZ.match(str(a))}
        adaylar = []
        for k in adsiz:
            puan = sorted(((sesler_modulu.benzerlik(izler[k], p.get("vektor", [])), ad) for ad, p in profiller.items() if _ilk(ad) not in kullanilan), reverse=True)
            if puan and puan[0][0] >= ESIK_GERIYE and (len(puan) == 1 or puan[0][0] - puan[1][0] >= FARK_GERIYE):
                adaylar.append((puan[0][0], k, puan[0][1]))
        adaylar.sort(reverse=True)
        es, bn, ad_kul = {}, {}, set()
        for s, k, ad in adaylar:
            if _ilk(ad) in ad_kul:
                continue
            es[k] = ad; bn[k] = round(s, 3); ad_kul.add(_ilk(ad))
        if es:
            out.append((js, es, bn))
    return out


def ben_tam_ad():
    """Kullanıcının adı: 'Adınız' ayarıyla aynı ilk adı taşıyan, en çok doğrulanmış ses profili (tam ad); yoksa ayardaki ad."""
    ben = (_ayar().get("benim_adim") or "").strip()
    try:
        import sesler as sesler_modulu
        P = sesler_modulu.oku()
        L = sorted((a for a in P if _ilk(a) == _ilk(ben) and " " in a.strip()), key=lambda a: -int(P[a].get("sayac", 1)))
        return L[0] if L and ben else ben
    except Exception:  # noqa: BLE001
        return ben


def profil_birlestir(log=print):
    """Aynı kişinin iki ses profili (yalnız ilk ad ve tam ad): kısa ad uzun adın ilk sözcüğüyse ve sesler benzerse (≥0,75) uzun ada katılır.
    İki profil, geriye dönük tanımada aynı kişiyi iki kümeye verdirebiliyordu. Döner: [(kısa, uzun, benzerlik)]."""
    import sesler as sesler_modulu
    P = sesler_modulu.oku(); out = []
    for kisa in sorted(P, key=len):
        if " " in kisa.strip() or kisa not in P:
            continue
        uzunlar = [u for u in P if u != kisa and " " in u and _ilk(u) == kisa.strip().casefold()]
        if len(uzunlar) != 1:
            continue
        u = uzunlar[0]; b = sesler_modulu.benzerlik(P[kisa].get("vektor", []), P[u].get("vektor", []))
        if b < 0.75:
            continue
        n1, n2 = int(P[kisa].get("sayac", 1)), int(P[u].get("sayac", 1))
        v = [(x * n1 + y * n2) / (n1 + n2) for x, y in zip(P[kisa]["vektor"], P[u]["vektor"])]
        P[u] = {"vektor": sesler_modulu._norm(v), "sayac": min(n1 + n2, 20)}
        del P[kisa]; out.append((kisa, u, round(b, 3)))
    if out:
        sesler_modulu.yaz(P)
        for k, u, b in out:
            log(f"Ses profili birleştirildi: {k} → {u} (benzerlik {b})")
    return out


# ---------------------------------------------------------------- düzeltmelerden öğrenme
def duzeltme_kaydet(tur, temel, eski, yeni, baglam=""):
    """tur: baslik | sirket | musteri | konusmaci. Kullanıcı elle düzelttiğinde site çağırır."""
    if not yeni or eski == yeni:
        return
    d = oku()
    d["duzeltmeler"].append({"zaman": time.time(), "tur": tur, "temel": temel, "eski": str(eski)[:200], "yeni": str(yeni)[:200], "baglam": str(baglam)[:300]})
    yaz(d)


def _misafir_mi():
    try:
        import claude_yaz
        return bool(claude_yaz.MISAFIR.get())
    except Exception:  # noqa: BLE001
        return False


def ad_blogu():
    """Toplantı adı istemine eklenen öğrenilmiş örnekler ve haftalık dersler (boşsa ''). Davetlinin işinde boş: sahibin düzeltmeleri girmez."""
    if _misafir_mi():
        return ""
    d = oku()
    ornek = [x for x in d["duzeltmeler"] if x["tur"] == "baslik"][-6:]
    ders = [x["ders"] for x in d["dersler"] if x.get("aktif", True) and x.get("yer") in ("baslik", "genel")][:5]
    if not ornek and not ders:
        return ""
    s = "\nKullanıcının daha önce düzelttiği adlar (bunlara benzer yaz):\n" + "\n".join(f"- '{x['eski']}' yerine '{x['yeni']}'" for x in ornek) if ornek else ""
    if ders:
        s += "\nÖğrenilenler:\n" + "\n".join(f"- {x}" for x in ders)
    return s


def musteri_blogu():
    """Müşteri seçimi istemine: kullanıcının müşteri düzeltmeleri ve haftalık dersler ('' olabilir)."""
    if _misafir_mi():
        return ""
    d = oku()
    ornek = [x for x in d["duzeltmeler"] if x["tur"] in ("musteri", "sirket")][-6:]
    ders = [x["ders"] for x in d["dersler"] if x.get("aktif", True) and x.get("yer") == "musteri"][:5]
    s = ""
    if ornek:
        s += "Kullanıcının düzelttiği müşteri seçimleri (aynı hatayı yapma):\n" + "\n".join(f"- '{x['baglam'] or x['temel']}': '{x['eski']}' değil, '{x['yeni']}'" for x in ornek) + "\n"
    if ders:
        s += "Öğrenilenler:\n" + "\n".join(f"- {x}" for x in ders) + "\n"
    return s


# ---------------------------------------------------------------- Couple müşteri dosyası (hazırlık notu için)
def couple_dosyasi(musteri, en_cok=2500):
    """Couple'ın müşteri dosyasının kısa hâli (Kısaca, devam eden işler, açık konular, takvim). Yoksa ''."""
    if not musteri or musteri == "Diğer" or _misafir_mi():
        return ""
    norm = lambda x: re.sub(r"[^a-z0-9]", "", str(x).casefold().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c"))  # noqa: E731
    for f in (KLASOR / "couple" / "musteriler").glob("*/dosya.json"):
        if norm(f.parent.name) != norm(musteri):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return ""
        parca = [d.get("ozet") or ""]
        for ad, alan in (("Devam eden işler", "devam_eden"), ("Açık konular", "acik_konular"), ("Takvim", "takvim")):
            L = d.get(alan) or []
            if L:
                parca.append(ad + ":\n" + "\n".join("- " + (x if isinstance(x, str) else " · ".join(str(v) for v in x.values() if v)) for x in L[:8]))
        return "\n".join(p for p in parca if p)[:en_cok]
    return ""


# ---------------------------------------------------------------- ölçüm
def olcum(gun=30):
    T = toplantilar(gun)
    ben = (_ayar().get("benim_adim") or "").strip()
    n = len(T)
    o = {"gun": gun, "toplanti": n, "adsiz_toplanti": 0, "adsiz_kume": 0, "kume": 0, "diger": 0, "baslik_kaynak": {}, "sizi_tanidi": 0,
         "alinti": 0, "alinti_dogru": 0, "eksik": {}, "canli_kart": 0, "uzanti_ad": 0, "tarayici": 0, "sure_dk": 0}
    for js, v, segs in T:
        sure = konusma_sureleri(segs)
        kumeler = [k for k in (v.get("etiket") or {}) if sure.get(str(k), 0) >= EN_AZ_KONUSMA]
        ads = adsizlar(v, segs)
        o["kume"] += len(kumeler); o["adsiz_kume"] += len(ads); o["adsiz_toplanti"] += bool(ads)
        o["diger"] += (v.get("musteri") or "Diğer") == "Diğer" and (v.get("sirket") or "genel") != "genel"
        bk = v.get("baslik_kaynak") or "?"
        o["baslik_kaynak"][bk] = o["baslik_kaynak"].get(bk, 0) + 1
        o["sizi_tanidi"] += bool(ben) and any(_ilk(a) == _ilk(ben) for a in (v.get("etiket") or {}).values())
        for kisi in (v.get("kisaca") or {}).get("kisiler") or []:
            for x in kisi.get("isler") or []:
                if "alinti_dogru" in x:
                    o["alinti"] += 1; o["alinti_dogru"] += bool(x["alinti_dogru"])
        for adim in ("kisaca", "sinyaller", "danisman", "drive", "sesli_ozet"):
            if not v.get(adim):
                o["eksik"][adim] = o["eksik"].get(adim, 0) + 1
        o["canli_kart"] += len(v.get("canli_kartlar") or [])
        if "chrome" in str(v.get("uygulama") or "").lower() or "safari" in str(v.get("uygulama") or "").lower():
            o["tarayici"] += 1; o["uzanti_ad"] += v.get("adlar_kaynak") == "toplantı"
        o["sure_dk"] += round((v.get("sure") or 0) / 60)
    o["duzeltme"] = len([x for x in oku()["duzeltmeler"] if x["zaman"] > time.time() - gun * 86400])
    return o


# ---------------------------------------------------------------- sağlık
def _launchctl_calisiyor(etiket):
    import os
    import subprocess
    try:
        r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{etiket}"], capture_output=True, text=True, timeout=10)
        return "state = running" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def _manifest_surum():
    try:
        return json.loads((KLASOR / "uzanti" / "manifest.json").read_text(encoding="utf-8")).get("version") or ""
    except Exception:  # noqa: BLE001
        return ""


def saglik():
    """[{kod, ad, durum (ok|uyari|hata), metin, cozum}] — arayüz ve onarım için."""
    import shutil
    ay = _ayar(); S = []

    def ekle(kod, ad, durum, metin, cozum=""):
        S.append({"kod": kod, "ad": ad, "durum": durum, "metin": metin, "cozum": cozum})

    # kaydedici
    kl = KLASOR / "kaydedici" / "kaydedici.log"
    if not ay.get("oto_kayit", True):
        ekle("kaydedici", "Otomatik kayıt", "uyari", "Kapalı; toplantılar kendiliğinden kaydedilmez.", "Ayarlar → Kayıt → Otomatik toplantı kaydı")
    elif not _launchctl_calisiyor("com.yehso.transkript.kaydedici"):
        ekle("kaydedici", "Otomatik kayıt", "hata", "Kayıt yardımcısı çalışmıyor; toplantılar kaydedilmez.", "Bilgisayarı yeniden başlatın ya da bana söyleyin")
    else:
        son_satir = ""
        try:
            son_satir = kl.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
        except Exception:  # noqa: BLE001
            pass
        # 2026-10-30: süreç "çalışıyor" görünürken izleme döngüsü askıda kalabiliyor (nabız) ve izinler sessizce düşebiliyor (toplantı başlamadan görülsün)
        try:
            nabiz_yas = time.time() - (KAYIT / ".kaydedici_nabiz").stat().st_mtime
        except OSError:
            nabiz_yas = None
        try:
            izin = json.loads((KAYIT / ".kaydedici_izin.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            izin = {}
        if nabiz_yas is not None and nabiz_yas > 180:
            ekle("kaydedici", "Otomatik kayıt", "hata", f"Kayıt yardımcısı {int(nabiz_yas // 60)} dakikadır yanıt vermiyor; kendiliğinden yeniden başlatılır.", "Olmazsa Mac’i yeniden başlatın")
        elif izin.get("ekran") is False:
            ekle("kaydedici", "Otomatik kayıt", "hata", "Ekran ve Sistem Sesi Kaydı izni yok; karşı tarafın sesi alınamaz.", "Sistem Ayarları → Gizlilik ve Güvenlik → Ekran ve Sistem Sesi Kaydı → Transkript Kaydedici")
        elif izin.get("mikrofon") == "yok":
            ekle("kaydedici", "Otomatik kayıt", "hata", "Mikrofon izni yok; sizin sesiniz alınamaz.", "Sistem Ayarları → Gizlilik ve Güvenlik → Mikrofon → Transkript Kaydedici")
        elif "başlatılamadı" in son_satir or "izin" in son_satir.lower():
            ekle("kaydedici", "Otomatik kayıt", "hata", "Son kayıt denemesi başarısız: " + son_satir[-120:], "Sistem Ayarları → Gizlilik → Ekran ve Sistem Sesi Kaydı → Transkript Kaydedici")
        else:
            ekle("kaydedici", "Otomatik kayıt", "ok", "Çalışıyor" + (f"; izinler tamam, son kontrol {int(nabiz_yas)} sn önce." if nabiz_yas is not None else "."))
    # Chrome uzantısı
    try:
        u = json.loads((KAYIT / ".uzanti_durum.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        u = {}
    try:
        nabiz = (KAYIT / ".uzanti_nabiz").stat().st_mtime
    except OSError:
        nabiz = 0
    yas = time.time() - max(nabiz, float(u.get("zaman") or 0))
    ms = _manifest_surum()
    try:
        us = (KAYIT / ".uzanti_nabiz").read_text(encoding="utf-8").strip() or str(u.get("surum") or "")
    except OSError:
        us = str(u.get("surum") or "")
    if yas > 3 * 86400:
        ekle("uzanti", "Chrome uzantısı", "uyari", f"{int(yas // 86400)} gündür ses vermiyor; adlar ve kim konuştuğu gelmez.", "Chrome → chrome://extensions → Meet Toplantı Yardımcısı → yenile")
    elif ms and us and us != ms:
        ekle("uzanti", "Chrome uzantısı", "uyari", f"Chrome'daki sürüm {us}, güncel sürüm {ms}; birkaç dakika içinde kendini yeniler.", "Olmazsa chrome://extensions → yenile")
    else:
        try:
            tani = json.loads((KAYIT / ".uzanti_tani.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            tani = {}
        taze = time.time() - float(tani.get("zaman") or 0) < 600
        if taze and tani.get("aramada") and tani.get("altyazi") is False and tani.get("sure", 0) > 300:
            ekle("uzanti", "Chrome uzantısı", "uyari", "Toplantıda altyazı okunamıyor; Google Meet/Teams sayfa yapısı değişmiş olabilir. Kim konuştuğu gelmez.", "Bana söyleyin; uzantıyı güncellerim")
        elif taze and tani.get("aramada") and tani.get("sure", 0) > 600 and (tani.get("son_konusan") is None or tani.get("son_konusan") > 600):
            ekle("uzanti", "Chrome uzantısı", "uyari", "Toplantıda 10 dakikadır konuşmacı adı okunamadı; altyazılar kapalı ya da sayfa yapısı değişmiş olabilir.", "Toplantıda altyazıları açın")
        else:
            ekle("uzanti", "Chrome uzantısı", "ok", f"Sürüm {us or ms}.")
    # takvim + e-posta davetleri
    try:
        import takvim
        tk = takvim.durum()
        bozuk = [t for t in tk if t.get("hata")]
        if bozuk:
            ekle("takvim", "Takvim", "uyari", f"{len(bozuk)} takvim adresi çalışmıyor.", "Ayarlar → Kayıt → Takvim")
        elif not tk:
            ekle("takvim", "Takvim", "uyari", "Takvim bağlı değil; hazırlık notu çıkmaz.", "Ayarlar → Kayıt → Takvim")
        else:
            ekle("takvim", "Takvim", "ok", f"{len(tk)} takvim.")
    except Exception as e:  # noqa: BLE001
        ekle("takvim", "Takvim", "uyari", f"Okunamadı ({str(e)[:60]})")
    try:
        import davetler
        dv = davetler.durum()
        if dv.get("hata"):
            ekle("davet", "E-posta davetleri", "uyari", "Okunamadı: " + dv["hata"][:100], "Mail uygulaması açık mı, hesaplar ekli mi?")
        elif dv.get("zaman") and dv.get("etkinlik"):
            ekle("davet", "E-posta davetleri", "ok", f"{dv.get('etkinlik', 0)} toplantı daveti okundu (son 45 gün).")
        elif dv.get("zaman") and not ay.get("meet_davetler", False):           # bilerek kapalı: sorun değil, bilgi
            ekle("davet", "E-posta davetleri", "ok", "Kapalı. İş e-postanızı Mail’e ekleyip aşağıdan açarsanız iş toplantılarında hazırlık notu ve doğru toplantı adı gelir.")
        elif dv.get("zaman"):
            ekle("davet", "E-posta davetleri", "uyari", f"Mail'de davet bulunmadı (hesaplar: {', '.join(dv.get('hesaplar') or []) or '—'}). İş e-postanızı Mail uygulamasına "
                 "eklerseniz iş davetleri okunur; iş toplantılarında hazırlık notu ve doğru toplantı adı gelir.", "Mail → Ayarlar → Hesaplar → +")
        else:
            ekle("davet", "E-posta davetleri", "uyari", "Henüz okunmadı.")
    except Exception:  # noqa: BLE001
        pass
    # Asana
    try:
        import gizli
        tok = gizli.birlestir(ay).get("asana_token")
    except Exception:  # noqa: BLE001
        tok = ay.get("asana_token")
    ekle("asana", "Asana", "ok" if tok else "uyari", "Bağlı." if tok else "Bağlı değil; işleriniz görev olarak eklenmez.", "" if tok else "Ayarlar → Notlar → Asana")
    # Drive, disk
    yol = Path(ay.get("drive_yol") or "").expanduser()
    if ay.get("drive", True):
        ekle("drive", "Drive", "ok" if yol.is_dir() else "hata", "Klasör yerinde." if yol.is_dir() else "Drive klasörü bulunamadı; notlar Drive'a gitmez.", "" if yol.is_dir() else "Google Drive uygulaması açık mı?")
    bos = shutil.disk_usage(str(KLASOR)).free / 1e9
    ekle("disk", "Disk", "ok" if bos >= 10 else "uyari" if bos >= 4 else "hata", f"{bos:.0f} GB boş.")
    # Claude
    try:
        import claude_yaz
        with claude_yaz.toplanti():
            hz = claude_yaz.hazir()
        if claude_yaz.sinir_durumu():
            ekle("claude", "Claude", "uyari", "Abonelik sınırında; bir süre bilgisayardaki modelle yazılır.")
        else:
            ekle("claude", "Claude", "ok" if hz else "uyari", "Hazır." if hz else "Toplantılarda kullanılamıyor; notlar daha zayıf olur.", "" if hz else "Ayarlar → Genel → Claude")
    except Exception:  # noqa: BLE001
        pass
    # ses profilleri ve son toplantılar
    try:
        import sesler as sesler_modulu
        pr = sesler_modulu.oku(); ben = (ay.get("benim_adim") or "").strip()
        if ben and not any(_ilk(a) == _ilk(ben) for a in pr):
            ekle("ses", "Sesiniz", "uyari", "Sesiniz henüz tanınmıyor; işleriniz ayıklanamaz.", "Bir toplantıda kendi adınızı verin")
        else:
            ekle("ses", "Tanınan sesler", "ok", f"{len(pr)} kişi.")
        ayni = {}
        for a in pr:
            ayni.setdefault(_ilk(a), []).append(a)
        for ilk, L in ayni.items():
            if len(L) > 1:
                b = min(sesler_modulu.benzerlik(pr[x].get("vektor", []), pr[y].get("vektor", [])) for x in L for y in L if x < y)
                if b < 0.5:
                    ekle("ses_cift", "Tanınan sesler", "uyari", f"{' ve '.join(L)} farklı seslere ait (benzerlik {b:.2f}); biri yanlış kişiye verilmiş olabilir.",
                         "Ayarlar → Kayıt → Tanınan sesler → yanlış olanı Unut")
    except Exception:  # noqa: BLE001
        pass
    try:                                                      # örnek toplantı testi (duman_testi.py meet / meet_kisaca; her gece)
        dm = json.loads((KAYIT / ".duman.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        dm = {}
    ok_ = [dm[k] for k in ("meet", "meet_kisaca") if k in dm]
    if not ok_:
        ekle("ornek", "Örnek toplantı", "uyari", "Henüz çalışmadı; her gece kendiliğinden çalışır.")
    else:
        hatalar = [h for x in ok_ for h in x.get("hatalar") or []]
        z = max(x.get("zaman") or 0 for x in ok_)
        if hatalar:
            ekle("ornek", "Örnek toplantı", "hata", "İki kişilik örnek toplantı yanlış işlendi: " + hatalar[0][:160], "Bana söyleyin; son değişikliği düzeltirim")
        else:
            ekle("ornek", "Örnek toplantı", "ok", f"İki kişilik örnek toplantı doğru işlendi ({time.strftime('%d.%m %H.%M', time.localtime(z))}): konuşmacılar, karar ve işler.")
    T = toplantilar(10)[:8]
    eksik = [(js.stem, [a for a in ("kisaca", "sinyaller") if not v.get(a)]) for js, v, _s in T]
    eksik = [(t, a) for t, a in eksik if a]
    if eksik:
        ekle("adimlar", "Son toplantılar", "uyari", f"{len(eksik)} toplantıda adım eksik; kendiliğinden tamamlanır.")
    elif T:
        ekle("adimlar", "Son toplantılar", "ok", f"Son {len(T)} toplantının adımları tamam.")
    if T:
        js, v, segs = T[0]
        ads = adsizlar(v, segs)
        if ads:
            ekle("adlar", "Konuşmacı adları", "uyari", f"Son toplantıda {len(ads)} kişi adsız.", "Toplantıyı açıp ▶ ile sesi dinleyip ad verin")
        kayit = Path(v.get("kayit") or "")
        cj = KAYIT / ".canli" / (kayit.stem + ".json")
        if kayit.name and not cj.exists() and (v.get("sure") or 0) > 300:
            ekle("canli", "Canlı yazıya dökme", "uyari", "Son toplantıda canlı yazıya dökme çalışmamış; fısıltı kartları gelmedi.")
        elif kayit.name and cj.exists():
            try:
                c = json.loads(cj.read_text(encoding="utf-8"))
                kapsam = (c.get("segmentler") or [{}])[-1].get("bit", 0) if c.get("segmentler") else 0
                if (v.get("sure") or 0) > 300 and kapsam < 0.5 * (v.get("sure") or 0) - (c.get("atlanan_sn") or 0):
                    ekle("canli", "Canlı yazıya dökme", "uyari", f"Son toplantıda canlı yazıya dökme toplantının yalnız {int(kapsam // 60)} dakikasını yetiştirebildi; fısıltı kartları eksik kaldı.")
                elif (c.get("atlanan_sn") or 0) > 60:
                    ekle("canli", "Canlı yazıya dökme", "ok", f"Mac yoğundu; canlı yazıya dökme {int(c['atlanan_sn'] // 60)} dakikayı atlayıp güncel kaldı.")
            except Exception:  # noqa: BLE001
                pass
    return S


# ---------------------------------------------------------------- karşı tarafın sözleri
def _kok(s):
    return {w[:5] for w in re.findall(r"[a-zçğıöşü0-9]{4,}", str(s).casefold())}


def soz_kontrol(log=print, en_cok=8):
    """Başkalarının gecikmiş sözleri: aynı şirket/müşteriyle SONRAKİ toplantılarda teslim edildiğine dair kanıt aranır (Claude, toplantı izniyle).
    Kanıt varsa iş 'bitti' işaretlenir ve `teslim` {temel, sn, alinti} yazılır. Döner: [(temel, k, i, teslim)]."""
    import claude_yaz
    import sozler
    d = oku(); bakilan = d["soz_bakilan"]; bugun = date.today().isoformat()
    hafta_once = date.fromordinal(date.today().toordinal() - 7).isoformat()
    L = [o for o in sozler.liste(90)["bekledigin"] if (o["durum"] == "gecikti" or o["durum"] == "tarihsiz" and o["toplanti_gunu"] <= hafta_once)
         and bakilan.get(f"{o['temel']}|{o['k']}|{o['i']}") != bugun][:en_cok]
    if not L:
        return []
    T = toplantilar(90)
    sonuc = []
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return []
        for o in L:
            bakilan[f"{o['temel']}|{o['k']}|{o['i']}"] = bugun
            sonraki = [(js, v, s) for js, v, s in T if js.stem != o["temel"] and str(date.fromtimestamp(v.get("olusturma") or 0)) > o["toplanti_gunu"]
                       and ((v.get("musteri") and v.get("musteri") == o.get("musteri") and o.get("musteri") != "Diğer") or (v.get("sirket") or "") == (o.get("sirket") or "x"))]
            if not sonraki:
                continue
            kok = _kok(o["is"]) | _kok(o["kim"])
            parca = []
            for js, v, segs in sonraki[:4]:
                puanli = sorted(((len(_kok(s.get("metin")) & kok), s) for s in segs), key=lambda x: -x[0])[:6]
                for p, s in puanli:
                    if p >= 2:
                        parca.append(f"[{js.stem} | {int(s.get('bas', 0))} sn | {(v.get('etiket') or {}).get(str(s.get('k')), '')}] {s.get('metin', '')[:300]}")
            if not parca:
                continue
            try:
                c = claude_yaz.sor_json(
                    f"{o['toplanti_gunu']} tarihli toplantıda {o['kim']} şu işi üstlenmişti: \"{o['is']}\" (söz: {o.get('ne_zaman') or 'tarihsiz'}). "
                    "Aşağıda aynı müşteriyle SONRAKİ toplantılardan ilgili parçalar var. Bu işin teslim edildiği ya da yapıldığı açıkça söyleniyor mu? "
                    "Yalnızca açık kanıt varsa evet de; konuşulması, ertelenmesi ya da 'yapacağım' denmesi teslim DEĞİLDİR.\n"
                    'JSON: {"teslim": "evet"|"hayir"|"belirsiz", "kaynak": "<köşeli parantezdeki dosya adı>", "sn": <sn>, "alinti": "<birebir, ≤20 kelime>"}\n\n'
                    + "\n".join(parca[:18]), model_adi="sonnet", zaman_asimi=120)
            except Exception as e:  # noqa: BLE001
                log(f"Söz kontrolü yapılamadı ({e})"); continue
            if c.get("teslim") == "evet" and c.get("kaynak"):
                sonuc.append((o["temel"], o["k"], o["i"], {"temel": str(c["kaynak"]).strip(), "sn": c.get("sn"), "alinti": str(c.get("alinti") or "")[:200], "zaman": time.time()}))
    d = oku(); d["soz_bakilan"] = {k: v for k, v in bakilan.items() if v >= (date.fromordinal(date.today().toordinal() - 30)).isoformat()}; yaz(d)
    return sonuc


def hatirlatma_yaz(o, veri):
    """Karşı tarafın gecikmiş sözü için kısa, nazik takip mesajı taslağı (gönderilmez; kullanıcı kopyalar ya da Mail taslağı açar)."""
    import claude_yaz
    ben = (_ayar().get("benim_adim") or "").strip()
    istem = (f"{ben or 'Kullanıcı'} adına {o['kim']}'e kısa bir takip mesajı yaz. {o['toplanti_gunu']} tarihli '{o['konu']}' toplantısında {o['kim']} "
             f"şunu üstlenmişti: \"{o['is']}\"" + (f" (söz: {o['ne_zaman']})" if o.get("ne_zaman") else "") + ". "
             "Nazik, doğal Türkçe, 2-4 cümle; suçlama ya da baskı yok; işi ve toplantıyı kısaca hatırlat, bir sonraki adımı sor. Selamla başla, imza atma. "
             "Yalnızca mesaj metnini yaz.")
    with claude_yaz.toplanti():
        if claude_yaz.hazir():
            try:
                return claude_yaz.sor(istem, "Kısa ve nazik iş mesajları yazarsın.", zaman_asimi=120, model_adi="sonnet").strip()
            except Exception:  # noqa: BLE001
                pass
    return f"Merhaba {o['kim'].split()[0]}, {o['toplanti_gunu']} toplantısında konuştuğumuz \"{o['is']}\" konusunda durum nedir? Bir sonraki adımı birlikte netleştirelim."


def eposta_bul(ad, veri):
    """Takvim katılımcılarından ada uyan e-posta (yoksa '')."""
    ilk = _ilk(ad)
    for k in (veri.get("takvim") or {}).get("katilimcilar") or []:
        if isinstance(k, dict) and k.get("eposta") and (_ilk(k.get("ad")) == ilk or k["eposta"].split("@")[0].casefold().startswith(ilk)):
            return k["eposta"]
    return ""


# ---------------------------------------------------------------- yenilik radarı
def _getir(url, zaman_asimi=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VideoHub Meet radar)"})
    with urllib.request.urlopen(req, timeout=zaman_asimi) as r:
        return r.read().decode("utf-8", "replace")


def _rss(url, kaynak, en_cok=15):
    """RSS/Atom → [{id, baslik, ozet, link, tarih, kaynak}]"""
    import html
    import xml.etree.ElementTree as ET
    m = _getir(url)
    m = re.sub(r"^\s+", "", m)
    kok = ET.fromstring(m)
    out = []
    for it in list(kok.iter("item")) + list(kok.iter("{http://www.w3.org/2005/Atom}entry")):
        g = lambda ad: (it.findtext(ad) or it.findtext("{http://www.w3.org/2005/Atom}" + ad) or "").strip()  # noqa: E731
        link = g("link")
        if not link:
            le = it.find("{http://www.w3.org/2005/Atom}link")
            link = le.get("href") if le is not None else ""
        oz = re.sub(r"<[^>]+>", " ", html.unescape(g("description") or g("summary") or g("content")))
        out.append({"id": link or g("title"), "baslik": html.unescape(g("title"))[:200], "ozet": re.sub(r"\s+", " ", oz).strip()[:500], "link": link,
                    "tarih": g("pubDate") or g("updated") or g("published"), "kaynak": kaynak})
        if len(out) >= en_cok:
            break
    return out


def _gn(q, kaynak, dil="en"):
    bolge = {"en": ("en-US", "US", "US:en"), "tr": ("tr", "TR", "TR:tr")}[dil]
    return _rss(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}+when:14d&hl={bolge[0]}&gl={bolge[1]}&ceid={bolge[2]}", kaynak, 8)


def _hn(q, kaynak):
    j = json.loads(_getir("https://hn.algolia.com/api/v1/search?tags=story&numericFilters=" + urllib.parse.quote(f"created_at_i>{int(time.time()) - 14 * 86400},points>30")
                          + "&query=" + urllib.parse.quote(q)))
    return [{"id": "hn:" + h["objectID"], "baslik": h.get("title") or "", "ozet": f"{h.get('points')} puan", "link": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
             "tarih": h.get("created_at") or "", "kaynak": kaynak} for h in j.get("hits", [])[:8]]


def _hf(q, kaynak):
    j = json.loads(_getir("https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=15&search=" + urllib.parse.quote(q)))
    sinir = time.time() - 30 * 86400
    out = []
    for m in j:
        t = m.get("lastModified") or m.get("createdAt") or ""
        try:
            if datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() < sinir:
                continue
        except Exception:  # noqa: BLE001
            pass
        if (m.get("downloads") or 0) < 200 and (m.get("likes") or 0) < 5:
            continue
        out.append({"id": "hf:" + m["id"], "baslik": m["id"], "ozet": f"{m.get('downloads', 0)} indirme, {m.get('likes', 0)} beğeni", "link": "https://huggingface.co/" + m["id"],
                    "tarih": t, "kaynak": kaynak})
    return out


PAKETLER = ["mlx-whisper", "sherpa-onnx", "faster-whisper", "mlx", "yt-dlp"]


def _surumler():
    """Kullanılan ses paketlerinin kurulu ve PyPI'daki en yeni sürümü: [{paket, kurulu, yeni}] (yalnız farklı olanlar)."""
    import importlib.metadata as md
    out = []
    for p in PAKETLER:
        try:
            kurulu = md.version(p)
        except Exception:  # noqa: BLE001
            continue
        try:
            yeni = json.loads(_getir(f"https://pypi.org/pypi/{p}/json"))["info"]["version"]
        except Exception:  # noqa: BLE001
            continue
        if yeni != kurulu:
            out.append({"paket": p, "kurulu": kurulu, "yeni": yeni})
    return out


KAYNAKLAR = [
    ("Google Meet güncellemeleri", lambda: _rss("https://workspaceupdates.googleblog.com/feeds/posts/default/-/Google%20Meet", "Google Workspace Updates", 12)),
    ("Microsoft Teams", lambda: _gn('"Microsoft Teams" new feature OR update OR captions', "Google Haberler · Teams")),
    ("Zoom", lambda: _gn('"Zoom Workplace" OR "Zoom AI Companion" new feature', "Google Haberler · Zoom")),
    ("Toplantı notu ürünleri", lambda: _gn('Granola OR Fathom OR "Otter.ai" OR "Fireflies.ai" OR "tl;dv" OR "Read AI" OR "Krisp" meeting notes feature', "Google Haberler · rakipler")),
    ("Hacker News", lambda: _hn("meeting notes", "Hacker News") + _hn("speaker diarization", "Hacker News") + _hn("whisper transcription", "Hacker News")),
    ("Türkçe ses modelleri", lambda: _hf("whisper turkish", "Hugging Face") + _hf("diarization", "Hugging Face")),
]


def radar(log=print):
    """Haftada bir: kaynaklardaki YENİ maddeler (daha önce görülmemiş) → sonnet süzgeci → uyarılar ve öneriler. Döner: {yeni, uyari, oneri}."""
    import claude_yaz
    d = oku(); R = d["radar"]; gorulen = set(R.get("gorulen") or []); saglik_ = {}
    yeni = []
    for ad, f in KAYNAKLAR:
        try:
            L = f(); saglik_[ad] = len(L)
            yeni += [x for x in L if x["id"] and x["id"] not in gorulen]
        except Exception as e:  # noqa: BLE001
            saglik_[ad] = f"hata: {str(e)[:60]}"
    try:
        surum = _surumler()
    except Exception:  # noqa: BLE001
        surum = []
    R["kaynak_saglik"] = saglik_; R["surumler"] = surum
    if not yeni and not surum:
        R["son"] = time.time(); d["radar"] = R; d["son"]["radar"] = time.time(); yaz(d)
        return {"yeni": 0, "uyari": 0, "oneri": 0}
    onceki = [o["baslik"] for o in d["oneriler"]][-40:]
    istem = ("Sen kişisel bir toplantı asistanının (adı Meet) ürün sorumlususun. Meet bir Mac'te yerel çalışıyor, kullanıcı Berlin'de bir ajans "
             "danışmanı; Google Meet (Chrome), Teams (çoğu tarayıcıda) ve Zoom toplantıları kaydediliyor.\nMEVCUT ÖZELLİKLER: " + MEVCUT + "\n"
             "Chrome uzantısı Google Meet ve Teams sayfasını okur (altyazı bölgesi: role=region aria-label=Captions; Teams data-tid=closed-caption-*).\n\n"
             "Aşağıda bu hafta çıkan haberler/sürümler var. Yalnızca Meet için GERÇEKTEN önemli olanları seç; çoğu önemsizdir, boş liste normaldir.\n"
             "1) uyarilar: Meet'i BOZABİLECEK değişiklikler (Google Meet/Teams altyazı, katılımcı paneli, arayüz, Chrome uzantı izinleri, macOS ekran kaydı).\n"
             "2) oneriler: kullanıcıya gerçek fayda verecek, uygulanabilir yeni özellik ya da iyileştirme (rakiplerde görülen, yeni model/araç). Mevcutları önerme. "
             "Her öneri: baslik (≤8 kelime, sade Türkçe, teknik terim yok), neden (tek cümle, kullanıcıya faydası), nasil (tek cümle, nasıl yapılır), "
             "buyukluk (kucuk|buyuk), kaynak (link).\n"
             "3) guncellemeler: paket sürümlerinden hangisine geçmek denenmeli (yalnız ses kalitesi/hız/hata düzeltmesi vaat edenler).\n"
             f"Daha önce önerilenler (tekrar etme): {json.dumps(onceki, ensure_ascii=False)}\n"
             'JSON: {"uyarilar": [{"baslik","neden","kaynak"}], "oneriler": [{"baslik","neden","nasil","buyukluk","kaynak"}], "guncellemeler": [{"paket","neden"}]}\n\n'
             "HABERLER:\n" + "\n".join(f"- [{x['kaynak']}] {x['baslik']} — {x['ozet'][:220]} ({x['link']})" for x in yeni[:80])
             + ("\n\nPAKET SÜRÜMLERİ:\n" + "\n".join(f"- {s['paket']}: kurulu {s['kurulu']}, en yeni {s['yeni']}" for s in surum) if surum else ""))
    c = {}
    if claude_yaz.arka_plan_uygun() and claude_yaz.hazir(toplanti_icerik=False):
        try:
            c = claude_yaz.sor_json(istem, model_adi="sonnet", zaman_asimi=300)
        except Exception as e:  # noqa: BLE001
            log(f"Meet radarı yorumlanamadı ({e})"); return {"yeni": len(yeni), "uyari": 0, "oneri": 0, "hata": str(e)[:100]}
    else:
        return {"yeni": len(yeni), "uyari": 0, "oneri": 0, "hata": "Claude şu an kullanılamıyor"}
    d = oku(); R = d["radar"]
    R["gorulen"] = (list(gorulen) + [x["id"] for x in yeni])[-1500:]
    R["kaynak_saglik"] = saglik_; R["surumler"] = surum
    R["uyarilar"] = [dict(u, zaman=time.time()) for u in c.get("uyarilar") or [] if isinstance(u, dict) and u.get("baslik")] + \
                    [u for u in R.get("uyarilar") or [] if time.time() - u.get("zaman", 0) < 21 * 86400]
    R["guncellemeler"] = [g for g in c.get("guncellemeler") or [] if isinstance(g, dict) and g.get("paket")]
    R["son"] = time.time()
    n = 0
    for o in c.get("oneriler") or []:
        if isinstance(o, dict) and o.get("baslik") and o["baslik"] not in onceki:
            d["oneriler"].append({"id": uuid.uuid4().hex[:6], "baslik": o["baslik"][:90], "neden": str(o.get("neden") or "")[:300], "nasil": str(o.get("nasil") or "")[:300],
                                  "buyukluk": o.get("buyukluk") if o.get("buyukluk") in ("kucuk", "buyuk") else "kucuk", "kaynak": str(o.get("kaynak") or "")[:300],
                                  "nereden": "radar", "durum": "bekliyor", "zaman": time.time()}); n += 1
    d["radar"] = R; d["son"]["radar"] = time.time(); yaz(d)
    if R["uyarilar"][:len(c.get("uyarilar") or [])]:
        olay("uyari", "Yenilik radarı: " + "; ".join(u["baslik"] for u in c.get("uyarilar") or [])[:200])
    log(f"Meet radarı: {len(yeni)} yeni madde, {len(c.get('uyarilar') or [])} uyarı, {n} öneri")
    return {"yeni": len(yeni), "uyari": len(c.get("uyarilar") or []), "oneri": n}


# ---------------------------------------------------------------- haftalık öz değerlendirme
def ozdegerlendirme(log=print):
    import claude_yaz
    d = oku()
    olcu = olcum(30); olcu7 = olcum(7)
    gecmis = (d["rapor"].get("gecmis") or [])[:6]
    duz = d["duzeltmeler"][-40:]
    olaylar = [o for o in d["olaylar"] if o["zaman"] > time.time() - 14 * 86400][-60:]
    karar = [{"baslik": o["baslik"], "durum": o["durum"]} for o in d["oneriler"] if o["durum"] in ("kabul", "red")][-30:]
    S = [s for s in saglik() if s["durum"] != "ok"]
    istem = ("Sen kişisel toplantı asistanı Meet'in ürün sorumlususun. Haftalık değerlendirme yap. Kullanıcı programcı değil; sade Türkçe.\n"
             f"MEVCUT ÖZELLİKLER: {MEVCUT}\n\nSON 30 GÜN ÖLÇÜM: {json.dumps(olcu, ensure_ascii=False)}\nSON 7 GÜN: {json.dumps(olcu7, ensure_ascii=False)}\n"
             f"ÖNCEKİ HAFTALAR: {json.dumps([{'zaman': time.strftime('%d.%m', time.localtime(g.get('zaman', 0))), 'olcu': g.get('olcu')} for g in gecmis], ensure_ascii=False)[:4000]}\n"
             f"KULLANICININ ELLE DÜZELTMELERİ (sistemin yanlışları): {json.dumps(duz, ensure_ascii=False)[:5000]}\n"
             f"KENDİLİĞİNDEN YAPILANLAR: {json.dumps([o['metin'] for o in olaylar], ensure_ascii=False)[:4000]}\n"
             f"SAĞLIK SORUNLARI: {json.dumps(S, ensure_ascii=False)[:2000]}\n"
             f"YENİLİK RADARI UYARILARI: {json.dumps((d['radar'].get('uyarilar') or [])[:6], ensure_ascii=False)[:2000]}\n"
             f"KULLANICININ ÖNCEKİ ÖNERİ KARARLARI: {json.dumps(karar, ensure_ascii=False)}\n\n"
             "Yaz: ozet (2-3 cümle: ne iyi gidiyor, en büyük sorun ne), dersler (≤5; düzeltmelerden çıkan, bir sonraki toplantı adı/şirket/müşteri seçiminde "
             "uygulanacak kısa kurallar; her biri yer: baslik|musteri|genel), oneriler (≤4; ölçümün gösterdiği en büyük sorunları çözecek somut iyileştirmeler; "
             "baslik ≤8 kelime, neden tek cümle, nasil tek cümle, buyukluk kucuk|buyuk). Reddedilmiş öneriyi tekrar etme.\n"
             'JSON: {"ozet": "...", "dersler": [{"ders","yer"}], "oneriler": [{"baslik","neden","nasil","buyukluk"}]}')
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return {"hata": "Claude kullanılamıyor"}
        c = claude_yaz.sor_json(istem, model_adi="opus", zaman_asimi=400)
    d = oku()
    d["dersler"] = [{"ders": str(x.get("ders"))[:200], "yer": x.get("yer") if x.get("yer") in ("baslik", "musteri", "genel") else "genel", "zaman": time.time(), "aktif": True}
                    for x in c.get("dersler") or [] if isinstance(x, dict) and x.get("ders")][:5]
    onceki = {o["baslik"] for o in d["oneriler"]}
    for o in c.get("oneriler") or []:
        if isinstance(o, dict) and o.get("baslik") and o["baslik"] not in onceki:
            d["oneriler"].append({"id": uuid.uuid4().hex[:6], "baslik": o["baslik"][:90], "neden": str(o.get("neden") or "")[:300], "nasil": str(o.get("nasil") or "")[:300],
                                  "buyukluk": o.get("buyukluk") if o.get("buyukluk") in ("kucuk", "buyuk") else "kucuk", "kaynak": "", "nereden": "ölçüm",
                                  "durum": "bekliyor", "zaman": time.time()})
    eski = d["rapor"]
    d["rapor"] = {"zaman": time.time(), "ozet": str(c.get("ozet") or "")[:800], "olcu": olcu,
                  "gecmis": ([{"zaman": eski["zaman"], "ozet": eski.get("ozet"), "olcu": eski.get("olcu")}] if eski.get("zaman") else []) + (eski.get("gecmis") or [])[:11]}
    d["son"]["ozdegerlendirme"] = time.time()
    yaz(d)
    log(f"Meet öz değerlendirme: {len(d['dersler'])} ders, {len(c.get('oneriler') or [])} öneri")
    return d["rapor"]


def oneri_karar(oid, durum):
    d = oku()
    for o in d["oneriler"]:
        if o["id"] == oid:
            o["durum"] = durum; o["karar_zaman"] = time.time()
            yaz(d)
            return True
    return False


# ---------------------------------------------------------------- gelişiminiz (2026-10-27)
# Kullanıcı: "toplantılardaki konuşma payımın haftalık eğilimini ve danışman notlarındaki tekrar eden dersleri tek bir 'gelişimim' kartında göster".
# Pay yalnız kullanıcının tam adıyla etiketlendiği toplantılardan (ilk adı taşıyan başka profil başka biri olabilir); beklenen pay = konuşan kişi
# sayısına göre eşit pay. Temalar danışman notlarının derslerinden tek Claude çağrısıyla gruplanır, girdi değişmedikçe önbellekten.
GELISIMIM = KLASOR / "profil" / "meet_gelisimim.json"


def _benim_etiket(veri, olcu, ben):
    """Kullanıcının bu toplantıdaki adı (yalnız emin olunanlar): tam adla etiket, yoksa danışmanın emin olduğu 'siz'."""
    if ben:
        for a in olcu:
            if a.strip().casefold() == ben.casefold():
                return a
    dn = veri.get("danisman") or {}
    return dn.get("siz") if dn.get("emin") and dn.get("siz") in olcu else None


def konusma_haftalari(hafta=8):
    """Son N haftanın konuşma payı: [{hafta, bas, pay, beklenen, toplanti, dk, soru}] eskiden yeniye + toplantı toplantı ayrıntı."""
    import danisman
    ben = ben_tam_ad()
    H = {}
    for js, v, segs in toplantilar(hafta * 7 + 7):
        o = danisman.olculer(segs, v.get("etiket") or {})
        toplam = sum(x["sn"] for x in o.values())
        a = _benim_etiket(v, o, ben)
        if toplam < 300 or not a:
            continue
        kisi = max(2, sum(1 for x in o.values() if x["sn"] >= EN_AZ_KONUSMA))
        z = datetime.fromtimestamp(v.get("olusturma") or js.stat().st_mtime)
        y, w, _ = z.isocalendar()
        h = H.setdefault(f"{y}-{w:02d}", {"hafta": f"{y}-{w:02d}", "bas": date.fromisocalendar(y, w, 1).isoformat(), "ben": 0, "toplam": 0,
                                          "beklenen_sn": 0.0, "toplanti": 0, "soru": 0, "liste": []})
        h["ben"] += o[a]["sn"]; h["toplam"] += toplam; h["beklenen_sn"] += toplam / kisi; h["toplanti"] += 1; h["soru"] += o[a]["soru"]
        h["liste"].append({"temel": js.stem, "baslik": v.get("baslik") or js.stem, "tarih": z.strftime("%Y-%m-%d %H.%M"), "pay": o[a]["pay"],
                           "beklenen": round(100 / kisi), "kisi": kisi, "dk": round(toplam / 60)})
    out = []
    for k in sorted(H)[-hafta:]:
        h = H[k]
        out.append({"hafta": k, "bas": h["bas"], "pay": round(100 * h["ben"] / h["toplam"]), "beklenen": round(100 * h["beklenen_sn"] / h["toplam"]),
                    "toplanti": h["toplanti"], "dk": round(h["toplam"] / 60), "soru": h["soru"], "liste": h["liste"]})
    return out


def _pay_cumlesi(H):
    """Kodla kurulan tek cümle (yorum yok): son hafta, beklenen, öncekilere göre yön."""
    if not H:
        return ""
    s = H[-1]
    fark = s["pay"] - s["beklenen"]
    cumle = f"Son haftada toplantılarda %{s['pay']} konuştunuz; kişi sayısına göre eşit pay %{s['beklenen']}."
    if abs(fark) < 5:
        cumle = f"Son haftada toplantılarda %{s['pay']} konuştunuz; kişi sayısına göre eşit paya (%{s['beklenen']}) yakın."
    if len(H) >= 2:
        once = round(sum(x["pay"] for x in H[:-1]) / len(H[:-1]))
        if abs(s["pay"] - once) >= 4:
            cumle += f" Önceki haftaların ortalaması %{once}."
    return cumle


def _ders_girdisi(gun=60):
    """Danışman notlarının dersleri: [{i, temel, baslik, tarih, emin, ders, aksiyonlar}] yeniden eskiye."""
    out = []
    for js, v, _ in toplantilar(gun):
        dn = v.get("danisman") or {}
        if not dn.get("dersler") or not dn.get("emin"):     # danışman sizi kesin tanımadıysa ders başkasının davranışı olabilir (16 Ekim: Mami'yi siz sandı)
            continue
        z = datetime.fromtimestamp(v.get("olusturma") or js.stat().st_mtime)
        baslik = v.get("baslik") or js.stem
        grup = z.strftime("%Y-%m-%d") + "|" + re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", baslik).casefold()   # aynı gün, aynı konu: bir toplantının kayıt parçaları
        for x in dn["dersler"]:
            out.append({"temel": js.stem, "grup": grup, "baslik": baslik, "tarih": z.strftime("%Y-%m-%d"), "emin": bool(dn.get("emin")),
                        "ders": f"{x.get('baslik') or ''}: {x.get('ders') or ''}".strip(": "),
                        "aksiyonlar": [a.get("ne") for a in dn.get("aksiyonlar") or [] if a.get("ne")][:3]})
    for i, x in enumerate(out, 1):
        x["i"] = i
    return out


def tema_imzasi(D):
    import hashlib
    return hashlib.sha1(json.dumps([(x["temel"], x["grup"], x["ders"]) for x in D], ensure_ascii=False).encode()).hexdigest()[:16]


def temalari_kur(D, log=print):
    """Derslerden tekrar eden temalar (≥2 ayrı toplantı), Claude sonnet tek çağrı. Döner: [{tema, aciklama, ilerleme, kaynaklar[{temel,baslik,tarih}], son}]"""
    import claude_yaz
    if len({x["grup"] for x in D}) < 2:
        return []
    satirlar = "\n".join(f"[{x['i']}] {x['tarih']} · {x['baslik'][:70]}{'' if x['emin'] else ' (kişi seçimi kesin değil)'} · {x['ders']}"
                         + (f" | aksiyonlar: {'; '.join(x['aksiyonlar'])}" if x["aksiyonlar"] else "") for x in D)
    istem = ("Aşağıda bir kişinin toplantılarından sonra yazılmış kariyer danışmanı notlarındaki dersler var (yeniden eskiye). Birden çok AYRI toplantıda "
             "tekrar eden davranış kalıplarını bul. Aynı sözcükler değil, aynı davranış sayılır (ör. 'tarih sorulunca cevap ver' ile 'toplantıyı tarihle kapat' "
             "aynı tema). Yalnız tek toplantıda geçeni tema yapma. '(kişi seçimi kesin değil)' işaretli satırlar tek başına tema kurmaz. En çok 4 tema, en sık "
             "olan önce.\n- tema: ≤6 kelime, eylem olarak ('Teslim tarihini net söyleyin').\n- aciklama: tek cümle, ≤22 kelime, 'siz' diliyle, notlardaki "
             "gözleme dayanır; övgü ve genel öğüt yok.\n- kaynaklar: köşeli parantezdeki numaralar.\n- ilerleme: en yeni toplantılarda hâlâ geçiyorsa "
             "'suruyor', yalnız eski toplantılarda geçip son toplantılarda geçmiyorsa 'azaliyor', yalnız son iki toplantıdaysa 'yeni'.\n"
             'JSON: {"temalar": [{"tema": "", "aciklama": "", "kaynaklar": [1, 2], "ilerleme": "suruyor|azaliyor|yeni"}]}\n\n' + satirlar)
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return None
        c = claude_yaz.sor_json(istem, model_adi="sonnet", zaman_asimi=180)
    I = {x["i"]: x for x in D}
    out = []
    for t in (c.get("temalar") or [])[:4]:
        ks = [I[int(n)] for n in t.get("kaynaklar") or [] if str(n).isdigit() and int(n) in I]
        tekil = {}
        for x in ks:                                         # bir toplantının iki kayıt parçası tek toplantı sayılır
            tekil.setdefault(x["grup"], {"temel": x["temel"], "baslik": x["baslik"], "tarih": x["tarih"], "ders": x["ders"]})
        if len(tekil) < 2 or not str(t.get("tema") or "").strip():
            continue
        L = sorted(tekil.values(), key=lambda x: x["tarih"], reverse=True)
        out.append({"tema": str(t["tema"]).strip()[:80], "aciklama": str(t.get("aciklama") or "").strip()[:240],
                    "ilerleme": t.get("ilerleme") if t.get("ilerleme") in ("suruyor", "azaliyor", "yeni") else "suruyor",
                    "kaynaklar": L, "son": L[0]["tarih"]})
    out.sort(key=lambda t: -len(t["kaynaklar"]))
    log(f"Gelişiminiz: {len(out)} tekrar eden tema")
    return out


def gelisimim_oku():
    try:
        return json.loads(GELISIMIM.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def gelisimim_tazele(log=print):
    """Temaları girdi değiştiyse yeniden kurar ve yazar. Döner: yazılan kayıt."""
    D = _ders_girdisi()
    imza = tema_imzasi(D)
    k = gelisimim_oku()
    if k.get("imza") == imza:
        return k
    t = temalari_kur(D, log)
    if t is None:                                            # Claude yok ya da toplantı izni kapalı: eski kayıt kalır
        return k
    k = {"imza": imza, "zaman": time.time(), "temalar": t, "toplanti": len({x["grup"] for x in D})}
    GELISIMIM.parent.mkdir(parents=True, exist_ok=True)
    tmp = GELISIMIM.with_suffix(".tmp"); tmp.write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(GELISIMIM)
    return k


def gelisimim(hafta=8):
    """Kart verisi: haftalık pay, cümle, temalar (önbellekten) ve temaların güncel olup olmadığı."""
    H = konusma_haftalari(hafta)
    D = _ders_girdisi()
    k = gelisimim_oku()
    return {"haftalar": H, "cumle": _pay_cumlesi(H), "temalar": k.get("temalar") or [], "tema_zaman": k.get("zaman", 0),
            "guncel": k.get("imza") == tema_imzasi(D), "ders_toplanti": len({x["grup"] for x in D})}


def ozet_durum():
    """Arayüz için: sağlık, ölçüm, olaylar, öneriler, radar, rapor, dersler."""
    d = oku()
    return {"saglik": d.get("saglik_son") or [], "saglik_zaman": d["son"].get("saglik", 0), "olcu": olcum(30), "olaylar": d["olaylar"][-40:][::-1],
            "oneriler": [o for o in d["oneriler"] if o["durum"] in ("bekliyor", "kabul")][::-1][:20], "radar": {k: d["radar"].get(k) for k in ("son", "uyarilar", "guncellemeler", "kaynak_saglik", "surumler")},
            "rapor": {k: d["rapor"].get(k) for k in ("zaman", "ozet")}, "dersler": d["dersler"], "duzeltme": len(d["duzeltmeler"]), "son": d["son"]}


if __name__ == "__main__":
    import sys
    komut = sys.argv[1] if len(sys.argv) > 1 else "olcum"
    if komut == "olcum":
        print(json.dumps(olcum(int(sys.argv[2]) if len(sys.argv) > 2 else 30), ensure_ascii=False, indent=1))
    elif komut == "saglik":
        for s in saglik():
            print(f"{s['durum']:6} {s['ad']}: {s['metin']}")
    elif komut == "geriye":
        for js, es, bn in geriye_donuk_tani():
            print(js.stem, es, bn)
    elif komut == "radar":
        print(radar())
    elif komut == "ozdeg":
        print(ozdegerlendirme())


# ---------------------------------------------------------------------------- toplantı sağlık özeti
# 2026-10-28 (kullanıcı onayladı: "acil paket"). Her toplantıdan sonra kaydın ve notların sağlığı tek bakışta; sorun varsa toplantı biter bitmez
# bildirim. 27 Ekim'de kayıt 12.05'te kesilmiş, uzantı iki gün hiçbir görüşmeyi görmemiş, altyazı hiç gelmemişti; hiçbiri kimseye söylenmedi.
# veri["saglik"] = {durum: ok|uyari|hata, maddeler: [{seviye, kod, metin}], zaman}.
TARAYICI = ("chrome", "brave", "edge", "arc", "safari", "firefox", "browser")


def _saat(ts):
    return time.strftime("%H.%M", time.localtime(ts))


def kayit_sonrasi_konusma(bas, bit, baska_kayitlar=()):
    """Kayıt bittikten sonra altyazının sürdüğü süre (sn): kayıt sonundan başlayan, aralarında ≤3 dk boşluk olan altyazı satırları.
    Başka bir kaydın başladığı anda kesilir (sonraki toplantının altyazısı sayılmasın). Uzantı altyazı vermediyse 0."""
    try:
        import meet_altyazi
        S = [x["t"] + bas for x in meet_altyazi.aralik(bas, bit + 3 * 3600)]
    except Exception:  # noqa: BLE001
        return 0.0, 0
    sinir = min([b for b in baska_kayitlar if b > bit] or [bit + 3 * 3600])
    S = sorted(t for t in S if bit + 60 < t < sinir)
    son, n = bit, 0
    for t in S:
        if t - son > 180:
            break
        son, n = t, n + 1
    return (son - bit if n >= 5 else 0.0), n


def toplanti_saglik(veri, segmentler, is_, ayar=None, baska_kayitlar=()):
    M = []
    ekle = lambda seviye, kod, metin: M.append({"seviye": seviye, "kod": kod, "metin": metin})   # noqa: E731
    ayar = ayar or {}
    sure = float(veri.get("sure") or (segmentler[-1]["bit"] if segmentler else 0) or 0)
    bas = float(is_.get("kayit_baslangic") or 0)
    bit = float(is_.get("kayit_bitis") or 0) or (bas + sure if bas else 0)
    konusma = sum(max(0.0, s["bit"] - s["bas"]) for s in segmentler or [])
    if sure > 300 and konusma / sure < 0.15:
        ekle("hata", "ses", f"Kayıtta {int(sure // 60)} dakikada yalnız {int(konusma // 60)} dakika konuşma var; karşı tarafın sesi alınmamış olabilir.")
    for b in veri.get("kayit_bosluklari") or []:
        if bas:
            ekle("uyari", "bosluk", f"Bağlantı koptuğu için {_saat(bas + b['bas'])}–{_saat(bas + b['bit'])} arası kayıtta yok.")
    if bas and bit:
        ek, _n = kayit_sonrasi_konusma(bas, bit, baska_kayitlar)
        if ek >= 120:
            ekle("hata", "erken", f"Kayıt {_saat(bit)}'de bitti ama altyazıya göre toplantı yaklaşık {int(round(ek / 60))} dakika daha sürdü; bu kısım kaydedilmedi.")
    uyg = str(veri.get("uygulama") or is_.get("uygulama") or "").casefold()
    tarayici = any(t in uyg for t in TARAYICI)
    satir = int((veri.get("altyazi") or {}).get("satir") or 0)
    olay = len(is_.get("konusmaci_olaylari") or [])
    if tarayici and sure > 180:
        if not satir and not olay:
            ekle("uyari", "uzanti", "Chrome uzantısı bu görüşmeyi görmedi; konuşanların adları ve altyazı gelmedi.")
        elif not satir:
            ekle("uyari", "altyazi", "Görüşmede altyazı kapalıydı; konuşanların adları yalnız sesten tahmin edildi.")
    et = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    pay = {}
    for s in segmentler or []:
        pay[str(s.get("k"))] = pay.get(str(s.get("k")), 0) + s["bit"] - s["bas"]
    adsiz = [k for k, sn in pay.items() if sn >= 30 and str(et.get(k, "Konuşmacı")).startswith("Konuşmacı")]
    if adsiz:
        ekle("bilgi", "adsiz", f"{len(adsiz)} kişi adsız; toplantı sayfasında sesini dinleyip ad verebilirsiniz.")
    if sure >= 120:
        k = veri.get("kisaca")
        if not k:
            ekle("hata", "kisaca", "Kısaca hazırlanamadı.")
        elif not str(k.get("model") or "").startswith("claude"):
            ekle("uyari", "model", "Notlar Claude yerine bilgisayardaki modelle yazıldı; kalite düşük olabilir (Claude o an kullanılamadı).")
    if ayar.get("drive", True) and not veri.get("drive") and not veri.get("onay_bekliyor"):
        ekle("uyari", "drive", "Notlar Drive'a eklenemedi.")
    g = veri.get("notlar_gonderim") or {}
    if g.get("hata"):
        ekle("uyari", "eposta", f"Notlar e-postası gönderilemedi: {str(g['hata'])[:120]}")
    h = (veri.get("gorev_atama") or {}).get("_hata")
    if h:
        ekle("uyari", "asana", f"İşleriniz Asana'ya eklenemedi: {str(h.get('metin') or '')[:120]}")
    durum = "hata" if any(m["seviye"] == "hata" for m in M) else "uyari" if any(m["seviye"] == "uyari" for m in M) else "ok"
    return {"durum": durum, "maddeler": M, "zaman": time.time()}

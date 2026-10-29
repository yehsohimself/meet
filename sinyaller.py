"""sinyaller.py - Toplantıdan "ne kazandırdı / ne kaybettirdi" sinyalleri (2026-10-21; kategoriyi zorlayan fikirler araştırmasından, kullanıcı "en güçlü
6 fikri ekle" dedi). Tek Claude çağrısıyla:

1. Amaç kapısı: toplantıdan önce kullanıcının yazdığı amaç (`amaclar`) tuttu mu (evet/kısmen/hayır + kanıt + eksik).
2. Kapsam kayması: "şunu da hızlıca yapar mısın" türü ek istekler, tahmini saat, kapsam dışı mı → aylık şirket toplamı, gün ücretiyle fiyat.
3. "Önceden şöyle demiştiniz": aynı şirket/müşteriyle önceki toplantıların kararları ve özetleriyle ÇELİŞEN sözler (bütçe, tarih, kapsam, onay).
4. Kırılma ve onarma: karşı tarafın geri çekildiği anlar (kısa cevaplar, "nasıl isterseniz", resmileşme, bırakılan konu) + önceki toplantılardan
   açık kalan kırılmalardan bu toplantıda onarılanlar; her açık kırılmaya önerilen onarma cümlesi (terapi araştırmasındaki "rupture & repair").
5. Tahmin defteri: kullanıcının toplantıda yaptığı tahminler (güven, ne zaman bakılır) + önceki açık tahminler için bu toplantıdaki kanıt.

Sonuç `veri["sinyaller"]`; tahminler ayrıca `profil/tahminler.json` defterine (sonuç kullanıcıdan ya da sonraki toplantıların kanıtından).
Kişi profilleri (`kisiler.py`) ve şirket sayfası bu verileri toplar. Toplantı içeriği yalnızca "Toplantılarda da Claude" açıksa.
"""
import json
import re
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
AMAC = KLASOR / "kayitlar" / "amaclar.json"
TAHMIN = KLASOR / "profil" / "tahminler.json"
SURUM = 1


def _oku(yol, bos):
    try:
        return json.loads(Path(yol).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return bos


def _yaz(yol, veri):
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    Path(yol).write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")


def _ben():
    return (_oku(KLASOR / "ayarlar.json", {}).get("benim_adim") or "").strip()


# ---------------------------------------------------------------- amaç kapısı
def amac_kaydet(anahtar, metin, ad="", bas=0.0):
    """anahtar: takvim etkinliği (uid|bas) ya da 'elle'. Toplantı bitince kayıt aralığına göre eşlenir."""
    d = _oku(AMAC, {})
    d[anahtar] = {"metin": str(metin or "").strip()[:400], "ad": ad, "bas": float(bas or time.time()), "zaman": time.time()}
    if not d[anahtar]["metin"]:
        d.pop(anahtar)
    sinir = time.time() - 30 * 86400
    _yaz(AMAC, {k: v for k, v in d.items() if v.get("zaman", 0) > sinir})


def amac_bul(bas, bit):
    """Kayıt aralığına (±20 dk) denk gelen amaç; yoksa son 90 dk içinde yazılmış 'elle' amaç."""
    d = _oku(AMAC, {})
    adaylar = [v for k, v in d.items() if k != "elle" and bas - 1200 <= v.get("bas", 0) <= bit + 600]
    if adaylar:
        return min(adaylar, key=lambda v: abs(v["bas"] - bas))["metin"]
    e = d.get("elle")
    if e and bas - 5400 <= e.get("zaman", 0) <= bit:
        return e["metin"]
    return ""


def amac_oku(anahtar):
    return (_oku(AMAC, {}).get(anahtar) or {}).get("metin", "")


# ---------------------------------------------------------------- geçmiş bağlam
def _gecmis(veri, temel, gun=120, en_cok=6):
    """Aynı müşteri (yoksa aynı şirket) ile önceki toplantılar: kısa özet + kararlar + kişiler; açık kırılmalar ve açık tahminler."""
    simdi = veri.get("olusturma") or time.time()
    mus = veri.get("musteri") if (veri.get("musteri") or "Diğer") != "Diğer" else ""
    sir = veri.get("sirket") or ""
    out = []
    for js in KLASOR.glob("transkript_*.json"):
        if js.stem == temel:
            continue
        v = _oku(js, {}).get("veri") or {}
        if not v.get("toplanti") or (v.get("olusturma") or 0) >= simdi or (v.get("olusturma") or 0) < simdi - gun * 86400:
            continue
        if not ((mus and v.get("musteri") == mus) or (not mus and sir and sir != "genel" and v.get("sirket") == sir)):
            continue
        out.append((js.stem, v))
    out.sort(key=lambda t: -(t[1].get("olusturma") or 0))
    return out[:en_cok]


def _gecmis_metni(gecmis):
    satir = []
    for temel, v in gecmis:
        ks = v.get("kisaca") or {}
        ozet = " ".join(ks.get("ozet") or []) or ((v.get("ozet") or {}).get("ozet") if isinstance(v.get("ozet"), dict) else "") or ""
        kararlar = (v.get("notlar") or {}).get("kararlar") or (v.get("ozet") or {}).get("kararlar") or []
        satir.append(f"### {v.get('baslik')}\nÖzet: {ozet[:1200]}\nKararlar: {'; '.join(kararlar)[:800]}")
    return "\n\n".join(satir)


def _acik_kirilmalar(gecmis):
    onarilan = set()
    for _t, v in gecmis:
        onarilan |= set((v.get("sinyaller") or {}).get("onarilan") or [])
    out = []
    for temel, v in gecmis:
        for k in (v.get("sinyaller") or {}).get("kirilmalar") or []:
            if k.get("id") and k["id"] not in onarilan:
                out.append({**k, "toplanti": v.get("baslik"), "temel": temel})
    return out


def acik_tahminler(sirket="", musteri=""):
    return [t for t in _oku(TAHMIN, []) if not t.get("sonuc") and (not sirket or t.get("sirket") == sirket) and (not musteri or t.get("musteri") == musteri)]


# ---------------------------------------------------------------- çözümleme
def uret(veri, segmentler, temel, log=print):
    import claude_yaz
    import ozet as ozet_modulu
    from transkript import paragrafla
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(segmentler, etiket)
    if not par:
        return None
    metin = "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in par)
    bas = float(veri.get("kayit_baslangic") or 0) or (veri.get("olusturma") or time.time()) - (veri.get("sure") or 0)
    amac = veri.get("amac") or amac_bul(bas, bas + (veri.get("sure") or 0))
    gecmis = _gecmis(veri, temel)
    kir = _acik_kirilmalar(gecmis)
    tah = acik_tahminler(veri.get("sirket") or "", (veri.get("musteri") or "") if (veri.get("musteri") or "Diğer") != "Diğer" else "")
    ben = _ben() or "kullanıcı"
    istem = (
        f"Toplantı: {veri.get('baslik')}\nŞirket: {veri.get('sirket') or '-'} · Müşteri: {veri.get('musteri') or '-'}\nKullanıcı (serbest kreatif): {ben}\n"
        + (f"KULLANICININ TOPLANTIDAN ÖNCEKİ AMACI: \"{amac}\"\n" if amac else "")
        + ("\nÖNCEKİ TOPLANTILAR (aynı müşteri/şirket):\n" + _gecmis_metni(gecmis) + "\n" if gecmis else "")
        + ("\nÖNCEKİ TOPLANTILARDAN AÇIK KALAN KIRILMALAR:\n" + "\n".join(f"- id={k['id']} · {k.get('kim')}: {k.get('sinyal')}" for k in kir) + "\n" if kir else "")
        + ("\nKULLANICININ AÇIK TAHMİNLERİ:\n" + "\n".join(f"- id={t['id']} · \"{t['tahmin']}\" ({t.get('tarih')})" for t in tah[:15]) + "\n" if tah else "")
        + "\nGÖREV: Bu toplantıyı aşağıdaki beş açıdan oku. Yalnızca konuşmada açıkça dayanağı olanları yaz; yoksa boş liste. Türkçe, kısa, somut. "
        "Alıntılar transkriptten birebir ve kısa. Zaman [dk:sn] biçiminde 'zaman' alanına.\n"
        "1) amac_sonuc (amaç verildiyse): {karsilandi: evet|kismen|hayir, kanit: en fazla 25 kelime, eksik: ne kaldı (kısa), sonraki: tek cümlelik öneri}.\n"
        "2) kapsam: anlaşılan işin DIŞINDA kalan ya da ek iş yükü yaratan istekler ('şunu da yapar mısın', 'bir de şu', yön değişikliği, ek revizyon "
        "turu). Her biri: {istek: kısa emir cümlesi, kim, zaman, saat: tahmini iş saati (0.5-40), kapsam_disi: true|false, neden: kısa}. Kullanıcıdan "
        "istenenler önemli; ekip içi rutin işleri yazma.\n"
        "3) celiskiler: ÖNCEKİ TOPLANTILAR verildiyse, bu toplantıda öncekilerle çelişen sözler/kararlar (bütçe, tarih, kapsam, onay, yön, rakam). Her "
        "biri: {konu, simdi: alıntı, once: önceki toplantıda ne kararlaştırılmış/söylenmişti (kısa), once_toplanti: başlığı, zaman, tur: butce|tarih|"
        "kapsam|karar|yon|diger, onem: yuksek|orta}. Emin değilsen yazma.\n"
        "4) kirilmalar: karşı tarafın (müşteri ya da ekip arkadaşı) GERİ ÇEKİLDİĞİ anlar: cevapların birden kısalması, 'nasıl isterseniz/tamam olur' "
        "gibi geri çekilme, birden resmileşme, itirazın yarıda bırakılması, konunun kapatılması, alınganlık, sabırsızlık. Kullanıcının kendi kırılmalarını "
        "değil, ilişkiyi zedeleyen anları yaz. Her biri: {kim, zaman, sinyal: ne oldu (kısa), alinti, onarildi: aynı toplantıda onarıldı mı, "
        "onarim: bir sonraki görüşmede kullanıcının söyleyebileceği tek cümle}. Ayrıca onarilan: AÇIK KALAN KIRILMALAR'dan bu toplantıda onarılanların "
        "id listesi (ilişki düzeldiyse, konu kapandıysa).\n"
        "5) tahminler: KULLANICININ (" + ben + ") ileriye dönük tahminleri ve bahisleri ('bu kanca tutar', 'müşteri B'yi seçer', 'cumaya yetişir'). "
        "Her biri: {tahmin: tek cümle, zaman, guven: 0.5-0.95 (söyleyişindeki kesinliğe göre), bakilacak: kaç gün sonra sonucu belli olur (3-60)}. "
        "Ayrıca tahmin_kanitlari: AÇIK TAHMİNLER'den bu toplantıda sonucu belli olanlar: {id, sonuc: dogru|yanlis|kismen, kanit: kısa alıntı}.\n"
        'Yalnızca JSON: {"amac_sonuc": null, "kapsam": [], "celiskiler": [], "kirilmalar": [], "onarilan": [], "tahminler": [], "tahmin_kanitlari": []}\n\n'
        "TRANSKRİPT:\n" + metin[:220000])
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            log("      Sinyaller atlandı (Claude kullanılamıyor)"); return None
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, zaman_asimi=600)) or {}
    if not isinstance(c, dict):
        return None

    def sn(z):
        m = re.match(r"^\s*\[?\s*(?:(\d+):)?(\d{1,3}):(\d{2})", str(z or ""))
        return (int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))) if m else None
    for alan in ("kapsam", "celiskiler", "kirilmalar", "tahminler"):
        c[alan] = [x for x in (c.get(alan) or []) if isinstance(x, dict)]
        for x in c[alan]:
            x["sn"] = sn(x.get("zaman"))
            if alan in ("kirilmalar", "tahminler"):
                x["id"] = uuid.uuid4().hex[:8]
    for x in c["kapsam"]:
        try:
            x["saat"] = max(0.25, min(40.0, float(x.get("saat") or 1)))
        except (TypeError, ValueError):
            x["saat"] = 1.0
    c["onarilan"] = [str(i) for i in (c.get("onarilan") or []) if i]
    if amac:
        c["amac"] = amac
    c.update({"zaman": time.time(), "surum": SURUM, "model": ozet_modulu.SON_MODEL})
    _defter_guncelle(veri, temel, c)
    log(f"      Sinyaller: {len(c['kapsam'])} ek istek, {len(c['celiskiler'])} çelişki, {len(c['kirilmalar'])} kırılma, {len(c['tahminler'])} tahmin"
        + (f", amaç: {(c.get('amac_sonuc') or {}).get('karsilandi', '?')}" if amac else ""))
    return c


def _defter_guncelle(veri, temel, c):
    """Tahmin defteri: yeni tahminler eklenir; açık tahminlere bu toplantıdan gelen kanıt öneri olarak yazılır (kullanıcı onaylar)."""
    d = _oku(TAHMIN, [])
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", veri.get("baslik") or "")   # süre toplantı gününden sayılır (eski toplantı sonradan taransa da)
    g = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else date.fromtimestamp(veri.get("olusturma") or time.time())
    for t in c.get("tahminler") or []:
        try:
            gun = int(t.get("bakilacak") or 42)
        except (TypeError, ValueError):
            gun = 42
        d.append({"id": t["id"], "tahmin": t.get("tahmin"), "guven": t.get("guven"), "tarih": g.isoformat(), "temel": temel, "sn": t.get("sn"),
                  "toplanti": veri.get("baslik"), "sirket": veri.get("sirket") or "", "musteri": veri.get("musteri") or "",
                  "bakilacak": (g + timedelta(days=max(3, min(90, gun)))).isoformat(), "sonuc": None})
    kanit = {k.get("id"): k for k in c.get("tahmin_kanitlari") or [] if isinstance(k, dict)}
    for t in d:
        if t["id"] in kanit and not t.get("sonuc"):
            t["oneri"] = {"sonuc": kanit[t["id"]].get("sonuc"), "kanit": kanit[t["id"]].get("kanit"), "toplanti": veri.get("baslik"), "temel": temel}
    _yaz(TAHMIN, d[-500:])


def tahmin_sonuc(tid, sonuc):
    d = _oku(TAHMIN, [])
    for t in d:
        if t["id"] == tid:
            t["sonuc"] = sonuc if sonuc in ("dogru", "yanlis", "kismen") else None
            t["sonuc_zaman"] = time.time()
    _yaz(TAHMIN, d)


def defter():
    """Tahmin defteri + şirket/müşteri bazında isabet (doğru=1, kısmen=0,5)."""
    d = _oku(TAHMIN, [])
    bugun = date.today().isoformat()
    isabet = {}
    for t in d:
        if t.get("sonuc"):
            anahtar = t.get("musteri") or t.get("sirket") or "Genel"
            a = isabet.setdefault(anahtar, [0.0, 0])
            a[0] += {"dogru": 1, "kismen": 0.5}.get(t["sonuc"], 0); a[1] += 1
    return {"tahminler": d, "zamani_gelen": [t for t in d if not t.get("sonuc") and (t.get("bakilacak") or "9") <= bugun or (not t.get("sonuc") and t.get("oneri"))],
            "isabet": {k: {"oran": round(v[0] / v[1], 2), "adet": v[1]} for k, v in isabet.items()}}


def kapsam_ozeti(gun=31):
    """Şirket şirket son N günün kapsam dışı istekleri (saat toplamı + liste)."""
    sinir = time.time() - gun * 86400; out = {}
    for js in KLASOR.glob("transkript_*.json"):
        v = _oku(js, {}).get("veri") or {}
        if not v.get("toplanti") or (v.get("olusturma") or 0) < sinir:
            continue
        for x in (v.get("sinyaller") or {}).get("kapsam") or []:
            if not x.get("kapsam_disi"):
                continue
            s = out.setdefault(v.get("sirket") or "genel", {"saat": 0.0, "istekler": []})
            s["saat"] += x.get("saat") or 0
            s["istekler"].append({**x, "temel": js.stem, "toplanti": v.get("baslik"), "musteri": v.get("musteri") or ""})
    return out

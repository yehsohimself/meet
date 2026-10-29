"""Yayın paketi: her video için yayına hazırlık (Studio, 2026-10-24).

Marka serisi paketinin (marka.py) genel hali: herhangi bir video ve (isteğe bağlı) Couple/Atölye marka profili için tek Claude
çağrısıyla YouTube başlıkları, açıklama, bölümler (YouTube'un zaman damgalı bölüm listesi), etiketler, kapak yazıları, Shorts/Reels
kesitleri, Instagram açıklaması ve LinkedIn gönderisi. Kaynak video varsa kapak görselleri (kapak.py'nin kare seçimi) de çizilir.

Kendini besleme: kullanıcı paketteki önerileri beğenir/beğenmez (nedeniyle) → profil/yayin_tercihleri.json → sonraki her paketin
istemine "geçmiş tercihler" olarak girer (aynı kanal ve aynı marka önce). Kullanılan (kopyalanan) öğe de "beğenildi" sayılır.

Kullanım: python yayin.py X.json [marka_kodu]
"""
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
TERCIH = KLASOR / "profil" / "yayin_tercihleri.json"
PARCALAR = ("youtube", "bolumler", "kapak", "shorts", "instagram", "linkedin")
DIL_ADI = {"tr": "Türkçe", "en": "İngilizce", "de": "Almanca", "fr": "Fransızca", "es": "İspanyolca", "it": "İtalyanca"}


def _zaman(sn):
    import ortak                                           # tek sürüm: bir saatin üstünde h:mm:ss (2026-10-25)
    return ortak.zaman(sn)


def markalar():
    try:
        d = json.loads((KLASOR / "atolye" / "markalar.json").read_text(encoding="utf-8"))
        return {k: v for k, v in (d.get("markalar") or {}).items()}, d.get("ortak") or {}
    except Exception:  # noqa: BLE001
        return {}, {}


def marka_sec(veri):
    """Videonun markası: elle seçilen > toplantı/couple müşterisi > başlıkta/kanalda geçen marka adı."""
    m, _ = markalar()
    for anahtar in (veri.get("yayin_marka"), veri.get("musteri")):
        if anahtar:
            for kod, p in m.items():
                if kod == anahtar or (p.get("ad") or "").lower() == str(anahtar).lower():
                    return kod
    metin = f"{veri.get('baslik') or ''} {veri.get('kanal') or ''}".lower()
    for kod, p in m.items():
        if p.get("ad") and re.search(r"(?<!\w)" + re.escape(p["ad"].lower()) + r"(?!\w)", metin):
            return kod
    return ""


# ----------------------------------------------------------------------------- tercihler (kendini besleme)
def tercihler_oku():
    try:
        return json.loads(TERCIH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"kayitlar": []}


def tercih_ekle(kayit):
    d = tercihler_oku()
    kayit["t"] = time.time()
    d["kayitlar"] = (d.get("kayitlar") or [])[-400:] + [kayit]
    TERCIH.parent.mkdir(exist_ok=True)
    tmp = TERCIH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(TERCIH)


def _tercih_blogu(kanal, marka):
    k = tercihler_oku().get("kayitlar") or []
    k.sort(key=lambda x: (-(x.get("kanal") == kanal and bool(kanal)) - (x.get("marka") == marka and bool(marka)), -x.get("t", 0)))
    iyi = [x for x in k if x.get("iyi")][:10]
    kotu = [x for x in k if x.get("iyi") is False][:10]
    if not iyi and not kotu:
        return ""
    s = "KULLANICININ GEÇMİŞ TERCİHLERİ (bunlardan öğren; örnekleri kopyalama):\n"
    s += "".join(f"+ [{x.get('parca')}] {x.get('metin', '')[:180]}" + (f" (neden: {x['not']})" if x.get("not") else "") + "\n" for x in iyi)
    s += "".join(f"- [{x.get('parca')}] {x.get('metin', '')[:180]}" + (f" (neden: {x['not']})" if x.get("not") else "") + "\n" for x in kotu)
    return s


# ----------------------------------------------------------------------------- üretim
def _bolumleri_temizle(liste, sure):
    """YouTube bölüm kuralları: ilk 00:00, en az 3 bölüm, aralar ≥10 sn, sıralı, süre içinde."""
    out = []
    for b in liste or []:
        try:
            import klipler
            sn = klipler._sn(str(b.get("zaman") or "")) if isinstance(b, dict) else None
        except Exception:  # noqa: BLE001
            sn = None
        baslik = str((b or {}).get("baslik") or "").strip()[:80] if isinstance(b, dict) else ""
        if sn is None or not baslik or (sure and sn >= sure - 5):
            continue
        out.append({"sn": int(sn), "baslik": baslik})
    out.sort(key=lambda x: x["sn"])
    temiz = []
    for b in out:
        if temiz and b["sn"] - temiz[-1]["sn"] < 10:
            continue
        temiz.append(b)
    if temiz:
        temiz[0]["sn"] = 0
    return temiz if len(temiz) >= 3 else []


def uret(json_yolu, marka="", log=print):
    import claude_yaz
    import marka as marka_modulu
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8"))
    veri, seg = d["veri"], d["segmentler"]
    if not claude_yaz.hazir(bool(veri.get("toplanti"))):
        raise SystemExit("Claude şu an kullanılamıyor; yayın paketi Claude ile yazılır. Biraz sonra yeniden deneyin.")
    misafir = bool(claude_yaz.misafir())             # Studio davetlisi: sahibin müşteri markaları ve tercihleri kullanılmaz
    marka = "" if misafir else (marka or marka_sec(veri))
    m, ortak = ({}, {}) if misafir else markalar()
    profil = m.get(marka) or {}
    ozet, metin = marka_modulu._baglam(veri, seg, en_cok_kelime=40000)
    dil = veri.get("dil") or "tr"
    dil_ad = DIL_ADI.get(dil, dil)
    sure = float(veri.get("sure") or (seg[-1]["bit"] if seg else 0))
    marka_blogu = ""
    if profil:
        marka_blogu = (f"MARKA: {profil.get('ad')} ({profil.get('sektor', '')}). Hedef kitle: {profil.get('hedef', '')}. Ton: {profil.get('ton', '')}.\n"
                       f"Zorunlular: {'; '.join((profil.get('zorunlular') or []) + (ortak.get('zorunlular') or []))}\n"
                       f"Yasaklar (mevzuat dahil): {'; '.join((profil.get('yasaklar') or []) + (ortak.get('yasaklar') or []))}\n")
    sema = {
        "youtube": {"basliklar": ["3 başlık"], "aciklama": "120-220 kelime", "etiketler": ["8-12 etiket"]},
        "bolumler": [{"zaman": "mm:ss", "baslik": "..."}],
        "kapak": [{"satir1": "...", "satir2": "...", "tur": "soru|karsitlik|sayi|sonuc", "neden": "tek cümle"}],
        "shorts": [{"bas": "mm:ss", "bit": "mm:ss", "neden": "...", "shorts_baslik": "... / ...", "aciklama": "...", "etiketler": ["#..."]}],
        "instagram": {"aciklama": "...", "etiketler": ["#..."]},
        "linkedin": {"metin": "...", "etiketler": ["..."]},
    }
    sistem = ("Sen deneyimli bir video yayın editörüsün (YouTube, Shorts/Reels, Instagram, LinkedIn). Görevin bu videoyu yayına hazırlamak. "
              f"Bütün metinleri videonun dilinde ({dil_ad}) yaz. Yalnızca transkripte dayan: kişi adı, unvan, sayı, iddia uydurma. "
              "Abartılı tıklama tuzağı (ŞOK, İNANILMAZ, 'herkes şaşırdı') yok; vaat edilen şey videoda gerçekten olmalı. "
              f"Bugünün tarihi {time.strftime('%d.%m.%Y')} (metne tarih yazma).\n" + (marka_modulu.TURKCE_ILKELER if dil == "tr" else ""))
    istem = ("Şu parçaları hazırla:\n"
             "1) YOUTUBE: 3 farklı başlık (≤70 karakter; biri merak, biri net fayda, biri en çarpıcı söz), 1 açıklama (ilk iki cümle aramada görünür: "
             "videonun ne verdiğini söyler; düz paragraf, hashtag/bağlantı/bölüm listesi YOK), 8-12 etiket (arama terimi, # işaretsiz).\n"
             "2) BÖLÜMLER: YouTube bölüm listesi. İlk bölüm 00:00, en az 3, en çok 12; konu gerçekten değişen yerlerde; zamanlar transkriptteki "
             "damgalardan; başlıklar 2-6 kelime.\n"
             "3) KAPAK: 4 kapak yazısı (2 satır, satır başına ≤4 kelime, büyük harf); farklı kanca türleri.\n"
             "4) SHORTS: en güçlü 3 kesit (20-60 sn, cümle sınırında başlayıp biten, tek başına anlaşılır). shorts_baslik 2 satır '/' ile ≤6 kelime; "
             "aciklama 1 cümle; 3 hashtag.\n"
             "5) INSTAGRAM: Reels açıklaması 60-120 kelime, ilk satır kanca; 5 hashtag ayrı.\n"
             "6) LINKEDIN: 700-1300 karakter gönderi; ilk iki satır kanca, videodaki 2-3 somut fikir; hashtag metne değil 'etiketler'e (3).\n\n"
             + marka_blogu + ("" if misafir else _tercih_blogu(veri.get("kanal") or "", marka)) +
             "\nYanıt biçimi (yalnızca JSON): " + json.dumps(sema, ensure_ascii=False) +
             f"\n\nVİDEO: {veri.get('baslik') or ''} · Kanal: {veri.get('kanal') or '-'} · Süre: {_zaman(sure)}\n{ozet}\nTRANSKRİPT (zaman damgalı):\n{metin}")
    model = marka_modulu._yazi_modeli()
    log(f"Yayın paketi yazılıyor ({model})...")
    t0 = time.time()
    try:
        c = claude_yaz.sor_json(istem, sistem, zaman_asimi=1200, model_adi=model)
    except Exception as e:  # noqa: BLE001
        log(f"{model} yanıt vermedi ({str(e)[:80]}); {claude_yaz.model()} ile deneniyor")
        model = claude_yaz.model()
        c = claude_yaz.sor_json(istem, sistem, zaman_asimi=900)
    paket = {"zaman": time.time(), "model": model, "marka": marka, "marka_ad": profil.get("ad", ""), "sn": int(time.time() - t0)}
    y = c.get("youtube") if isinstance(c.get("youtube"), dict) else {}
    if y:
        aciklama = re.sub(r"\*\*", "", str(y.get("aciklama") or "").strip())
        aciklama = re.split(r"\n\s*(?:#|Bölümler:|Chapters:)", aciklama)[0].strip()
        paket["youtube"] = {"basliklar": [str(b).strip()[:100] for b in (y.get("basliklar") or []) if str(b).strip()][:3],
                            "aciklama": aciklama, "etiketler": [str(e).strip().lstrip("#")[:40] for e in (y.get("etiketler") or []) if str(e).strip()][:12]}
    paket["bolumler"] = _bolumleri_temizle(c.get("bolumler"), sure)
    import harfler
    paket["kapak"] = [{"satir1": harfler.ust(str(k.get("satir1") or "").strip())[:40], "satir2": harfler.ust(str(k.get("satir2") or "").strip())[:40],
                       "tur": str(k.get("tur") or "")[:20], "neden": str(k.get("neden") or "")[:200]}
                      for k in (c.get("kapak") or []) if isinstance(k, dict) and (k.get("satir1") or k.get("satir2"))][:4]
    paket["shorts"] = marka_modulu._shorts_temizle(c.get("shorts"), seg)
    ig = c.get("instagram") if isinstance(c.get("instagram"), dict) else {}
    if ig.get("aciklama"):
        paket["instagram"] = {"aciklama": str(ig["aciklama"]).strip(), "etiketler": ["#" + str(e).strip().lstrip("#") for e in (ig.get("etiketler") or [])][:6]}
    li = c.get("linkedin") if isinstance(c.get("linkedin"), dict) else {}
    if li.get("metin"):
        paket["linkedin"] = {"metin": re.sub(r"(?<!\w)#\w+", "", str(li["metin"])).strip(), "etiketler": ["#" + str(e).strip().lstrip("#") for e in (li.get("etiketler") or [])][:3]}
    log(f"Yayın paketi {paket['sn']} sn'de yazıldı")
    kaydet(json_yolu, paket)
    return paket


def kaydet(json_yolu, paket):
    """Yalnızca veri['yayin'] alanını yazar (dosya yeniden okunur: aynı anda çalışan çeviri/paylaşım işleri ezilmesin)."""
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8"))
    eski = d["veri"].get("yayin") or {}
    if eski.get("kapak_gorsel") and "kapak_gorsel" not in paket:
        paket["kapak_gorsel"] = eski["kapak_gorsel"]
    for k in ("shorts_video",):
        if eski.get(k) and k not in paket:
            paket[k] = eski[k]
    d["veri"]["yayin"] = paket
    tmp = json_yolu.with_suffix(".yayin_tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(json_yolu)
    belge_yaz(json_yolu.with_suffix(""), d["veri"], paket)


def youtube_aciklama(paket):
    """YouTube'a yapıştırılacak tam açıklama: paragraf + bölümler + etiketler."""
    y = paket.get("youtube") or {}
    s = (y.get("aciklama") or "").strip()
    if paket.get("bolumler"):
        s += "\n\n" + "\n".join(f"{_zaman(b['sn'])} {b['baslik']}" for b in paket["bolumler"])
    return s.strip()


def metin(veri, paket):
    s = [f"YAYIN PAKETİ · {veri.get('baslik') or ''}", ""]
    y = paket.get("youtube") or {}
    if y:
        s += ["YOUTUBE BAŞLIKLARI"] + [f"{i}. {b}" for i, b in enumerate(y.get("basliklar") or [], 1)] + ["", "YOUTUBE AÇIKLAMASI", youtube_aciklama(paket), ""]
        if y.get("etiketler"):
            s += ["ETİKETLER", ", ".join(y["etiketler"]), ""]
    if paket.get("kapak"):
        s += ["KAPAK YAZILARI"] + [f"{i}. {k['satir1']} / {k['satir2']}" for i, k in enumerate(paket["kapak"], 1)] + [""]
    if paket.get("shorts"):
        s += ["SHORTS / REELS KESİTLERİ"]
        for i, k in enumerate(paket["shorts"], 1):
            s += [f"{i}. {_zaman(k['bas'])}-{_zaman(k['bit'])} · {k.get('shorts_baslik', '')}", f"   {k.get('aciklama', '')} {' '.join(k.get('etiketler') or [])}"]
        s += [""]
    if paket.get("instagram"):
        s += ["INSTAGRAM", paket["instagram"]["aciklama"], " ".join(paket["instagram"].get("etiketler") or []), ""]
    if paket.get("linkedin"):
        s += ["LINKEDIN", paket["linkedin"]["metin"], " ".join(paket["linkedin"].get("etiketler") or []), ""]
    return "\n".join(s).strip() + "\n"


def belge_yaz(temel, veri, paket):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    temel = Path(temel)
    Path(f"{temel}.yayin.txt").write_text(metin(veri, paket), encoding="utf-8")
    doc = Document()
    for sec in doc.sections:
        sec.page_width, sec.page_height = Cm(21), Cm(29.7); sec.left_margin = sec.right_margin = Cm(2.2)
    st = doc.styles["Normal"]; st.font.name = "Helvetica Neue"; st.font.size = Pt(10.5)
    GRI = RGBColor(0x6E, 0x6E, 0x73)
    doc.add_heading("Yayın paketi", level=0)
    r = doc.add_paragraph().add_run(veri.get("baslik") or ""); r.font.color.rgb = GRI
    y = paket.get("youtube") or {}
    if y:
        doc.add_heading("YouTube başlıkları", level=1)
        for b in y.get("basliklar") or []:
            doc.add_paragraph(b, style="List Number")
        doc.add_heading("YouTube açıklaması", level=1)
        for par in youtube_aciklama(paket).split("\n\n"):
            doc.add_paragraph(par)
        if y.get("etiketler"):
            doc.add_heading("Etiketler", level=2); doc.add_paragraph(", ".join(y["etiketler"]))
    if paket.get("kapak"):
        doc.add_heading("Kapak", level=1)
        for ad in paket.get("kapak_gorsel") or []:
            if (temel.parent / ad).exists():
                doc.add_picture(str(temel.parent / ad), width=Cm(12))
        for k in paket["kapak"]:
            p = doc.add_paragraph(style="List Number"); p.add_run(f"{k['satir1']} / {k['satir2']}").bold = True
            if k.get("neden"):
                r = p.add_run(f"  — {k['neden']}"); r.font.color.rgb = GRI; r.font.size = Pt(9.5)
    if paket.get("shorts"):
        doc.add_heading("Shorts / Reels kesitleri", level=1)
        for k in paket["shorts"]:
            p = doc.add_paragraph(style="List Number")
            p.add_run(f"{_zaman(k['bas'])}-{_zaman(k['bit'])}  {k.get('shorts_baslik', '')}").bold = True
            r = p.add_run(f"\n{k.get('aciklama', '')} {' '.join(k.get('etiketler') or [])}"); r.font.color.rgb = GRI
    if paket.get("instagram"):
        doc.add_heading("Instagram", level=1); doc.add_paragraph(paket["instagram"]["aciklama"]); doc.add_paragraph(" ".join(paket["instagram"].get("etiketler") or []))
    if paket.get("linkedin"):
        doc.add_heading("LinkedIn", level=1)
        for par in paket["linkedin"]["metin"].split("\n\n"):
            doc.add_paragraph(par)
        doc.add_paragraph(" ".join(paket["linkedin"].get("etiketler") or []))
    doc.save(f"{temel}.yayin.docx")


def kapak_gorselleri(json_yolu, video, log=print):
    """Paketteki kapak yazılarıyla kaynak videodan en iyi yüz karelerine kapak taslakları (1280×720)."""
    import kapak
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8"))
    paket = d["veri"].get("yayin") or {}
    yazilar = [[k["satir1"], k["satir2"]] for k in (paket.get("kapak") or [])][:3]
    if not yazilar:
        raise SystemExit("Önce yayın paketini hazırlayın (kapak yazıları yok).")
    gecici = Path(tempfile.mkdtemp(prefix="yayin_kapak_"))
    try:
        sure = kapak._sure(video)
        kareler = kapak._kareler(video, gecici, sure)
        adaylar = [(t, p, k) for (t, k) in kareler for p in [kapak._puanla(k)] if p]
        if not adaylar:                                       # yüz yoksa eşit aralıklı kareler
            adaylar = [(t, (0.5, 0.5, 0.5, 0.2, 0.2), k) for (t, k) in kareler]
        secilen = kapak._sec([(t, p) for t, p, _k in adaylar], len(yazilar), sure)
        harita = {t: k for t, _p, k in adaylar}
        temel = json_yolu.with_suffix("")
        adlar = []
        for i, ((t, yuz), yazi) in enumerate(zip(secilen, yazilar), 1):
            cikti = Path(f"{temel}.yayin_kapak{i}.png")
            kapak._ciz(harita[t], yuz, yazi, cikti, "sade")
            adlar.append(cikti.name)
        paket["kapak_gorsel"] = adlar
        kaydet(json_yolu, paket)
        log(f"{len(adlar)} kapak görseli hazır")
        return adlar
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    p = uret(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
    print(json.dumps(p, ensure_ascii=False, indent=1)[:3000])

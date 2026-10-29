#!/usr/bin/env python3
"""
ceviri.py - Transkripti (ve varsa özetini) başka dile çevirir; bilgisayardaki Ollama modeliyle, dışarı veri gitmez.

Kullanım: .venv/bin/python ceviri.py transkript_x.json en|de|fr|...
Çıktılar: transkript_x.en.srt (YouTube biçimi altyazı), transkript_x.en.txt, transkript_x.en.docx (iki dilli Word)
JSON'a: veri["ceviriler"][dil] = {"segmentler": [...çevrilmiş metinler, segment sırasıyla], "ozet": {...}|null}
Son satır: "Bitti. Dosya: transkript_x.en.docx"
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
import ozet as ozet_modulu  # noqa: E402
from ozet import DIL_ADI, _json_coz, _sor  # noqa: E402

PARCA = 30            # bir seferde çevrilen satır sayısı
# Çeviriye özel model (Google TranslateGemma): kuruluysa satır satır onunla çevrilir; yoksa genel model toplu JSON ile.
CEVIRI_MODEL = os.environ.get("CEVIRI_MODEL", "translategemma:4b")
DIL_ADI_EN = {"tr": "Turkish", "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
              "pt": "Portuguese", "ru": "Russian", "ar": "Arabic", "fa": "Persian", "nl": "Dutch", "ja": "Japanese",
              "ko": "Korean", "zh": "Chinese", "az": "Azerbaijani", "el": "Greek", "pl": "Polish", "uk": "Ukrainian",
              "sv": "Swedish", "hi": "Hindi", "id": "Indonesian"}


def _ceviri_modeli():
    """TranslateGemma kuruluysa adı, değilse None (genel özet modeline düşülür)."""
    try:
        return CEVIRI_MODEL if ozet_modulu.hazir(CEVIRI_MODEL) else None
    except Exception:  # noqa: BLE001
        return None


def _sor_model(model, istem, num_predict=400, zaman_asimi=300):
    govde = {"model": model, "prompt": istem, "stream": False,
             "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": num_predict}}
    req = urllib.request.Request(ozet_modulu.OLLAMA + "/api/generate", data=json.dumps(govde).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=zaman_asimi) as r:
        return json.load(r).get("response", "")


def _satir_satir_cevir(metinler, kaynak, hedef, model, log=print):
    """TranslateGemma ile her satır tek başına çevrilir (model toplu/JSON biçimini desteklemez)."""
    k_ad, h_ad = DIL_ADI_EN.get(kaynak, kaynak), DIL_ADI_EN.get(hedef, hedef)
    sonuc = list(metinler)
    for i, m in enumerate(metinler):
        if i % 25 == 0:
            log(f"      Çeviri: {i + 1}/{len(metinler)}")
        if not m.strip() or not re.search(r"\w", m):
            continue
        istem = f"Translate the following text from {k_ad} to {h_ad}. Output only the translation.\n\n{m.strip()}"
        for _ in range(2):
            try:
                c = _sor_model(model, istem, num_predict=max(60, len(m.split()) * 6)).strip()
            except Exception as e:  # noqa: BLE001
                log(f"      Model hatası: {e}"); c = ""
            c = re.sub(r"^\s*(Translation|Çeviri)\s*:\s*", "", c, flags=re.I).strip().strip('"')
            if c and len(c) < len(m) * 4 + 40:
                sonuc[i] = c; break
    return sonuc


def log(m):
    print(m, flush=True)


def _parcala(metinler, en_cok=PARCA, en_cok_kelime=550):
    gruplar, simdiki, k = [], [], 0
    for i, m in enumerate(metinler):
        n = len(m.split())
        if simdiki and (len(simdiki) >= en_cok or k + n > en_cok_kelime):
            gruplar.append(simdiki); simdiki, k = [], 0
        simdiki.append(i); k += n
    if simdiki:
        gruplar.append(simdiki)
    return gruplar


def _claude_cevir(metinler, kaynak_adi, hedef_adi, log=log, baglam=""):
    """Claude ile 150 satırlık parçalar halinde, 3 parça aynı anda; satır sayısı ve sırası korunur."""
    import claude_yaz
    from concurrent.futures import ThreadPoolExecutor
    sonuc = list(metinler)
    gruplar = [list(range(i, min(i + 150, len(metinler)))) for i in range(0, len(metinler), 150)]
    sistem = (f"Sen profesyonel bir altyazı çevirmenisin ({kaynak_adi} → {hedef_adi}). Konuşma dilini doğal ve akıcı çevir; "
              "terimleri baştan sona tutarlı kullan; özel adları ve sayıları koru; her satırı ayrı çevir, satır birleştirme ya da atlama; "
              "çeviri kaynak satırdan belirgin uzun olmasın (altyazı). Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun.")
    bitti = [0]

    def _tek(grup):
        satirlar = "\n".join(f"{n + 1}. {metinler[i]}" for n, i in enumerate(grup))
        istem = ((f"Bağlam (yalnızca anlamak için, çevirme): {baglam}\n\n" if baglam else "") +
                 f"Aşağıdaki satırların HER BİRİNİ {hedef_adi} diline çevir (toplam {len(grup)} satır; 1'den {len(grup)}'e kadar hepsi yanıtta olmalı). "
                 f"Biçim: {{\"1\": \"çeviri\", \"2\": \"çeviri\", ..., \"{len(grup)}\": \"çeviri\"}}\n\n" + satirlar)
        for _ in range(2):
            try:
                c = claude_yaz.sor_json(istem, sistem, zaman_asimi=900)
            except Exception as e:  # noqa: BLE001
                log(f"      Claude hatası: {str(e)[:100]}"); c = {}
            alinan = {n: str(c.get(str(n + 1))).strip() for n in range(len(grup)) if isinstance(c.get(str(n + 1)), str) and str(c.get(str(n + 1))).strip()}
            if len(alinan) >= len(grup) * 0.9:
                break
        for n, i in enumerate(grup):
            if n in alinan:
                sonuc[i] = alinan[n]
        bitti[0] += 1
        log(f"      Çeviri: {bitti[0]}/{len(gruplar)}")
        return len(alinan)

    with ThreadPoolExecutor(max_workers=3) as ex:
        alinan = sum(ex.map(_tek, gruplar))
    if alinan < len([m for m in metinler if m.strip()]) * 0.9:
        raise RuntimeError("Claude çevirisi eksik kaldı")
    return sonuc


def _satirlari_cevir(metinler, kaynak_adi, hedef_adi, log=log, kaynak=None, hedef=None, baglam=""):
    """metinler listesini sırayla çevirir; sayı/sıra korunur. Boş/çevrilemeyen satır orijinal kalır."""
    if ozet_modulu.claude_hazir():
        try:
            return _claude_cevir(metinler, kaynak_adi, hedef_adi, log, baglam)
        except Exception as e:  # noqa: BLE001
            log(f"      Claude ile çevrilemedi ({str(e)[:100]}); bilgisayardaki modelle devam ediliyor")
    model = _ceviri_modeli()
    if model and kaynak and hedef:
        return _satir_satir_cevir(metinler, kaynak, hedef, model, log)
    sonuc = list(metinler)
    gruplar = _parcala(metinler)
    for gi, grup in enumerate(gruplar, 1):
        log(f"      Çeviri: {gi}/{len(gruplar)}")
        satirlar = "\n".join(f"{n + 1}. {metinler[i]}" for n, i in enumerate(grup))
        istem = (f"Aşağıdaki numaralı satırlar bir videonun {kaynak_adi} transkriptinden alınmış konuşma cümleleridir. "
                 f"Her satırı {hedef_adi} diline çevir. Kurallar: anlamı koru, doğal ve akıcı konuşma dili kullan, "
                 "hiçbir satırı atlama ya da birleştirme, açıklama ekleme, özel adları ve sayıları olduğu gibi bırak. "
                 'Yanıtı yalnızca şu JSON yapısında ver: {"1": "çeviri", "2": "çeviri", ...}\n\n' + satirlar)
        for deneme in range(2):
            try:
                cevap = _json_coz(_sor(istem, json_bekle=True, num_ctx=8192))
            except Exception as e:  # noqa: BLE001
                log(f"      Model hatası: {e}"); cevap = {}
            alinan = 0
            for n, i in enumerate(grup):
                v = cevap.get(str(n + 1))
                if isinstance(v, str) and v.strip():
                    sonuc[i] = v.strip(); alinan += 1
            if alinan >= len(grup) * 0.8:
                break
            log("      Eksik satır var, bu parça tekrar deneniyor...")
    return sonuc


def _ozet_cevir(o, kaynak_adi, hedef_adi, log=log, kaynak=None, hedef=None):
    """Özet, maddeler ve bölüm başlıkları satır çeviriciyle çevrilir (yapı korunur)."""
    if not o or not o.get("ozet"):
        return None
    maddeler = [str(m) for m in o.get("maddeler", [])]
    bolumler = o.get("bolumler", [])
    satirlar = [str(o["ozet"])] + maddeler + [b["baslik"] for b in bolumler]
    c = _satirlari_cevir(satirlar, kaynak_adi, hedef_adi, log, kaynak, hedef)
    n = 1 + len(maddeler)
    return {"ozet": c[0], "maddeler": c[1:n],
            "bolumler": [{"sn": b["sn"], "baslik": t} for b, t in zip(bolumler, c[n:])]}


def _yaz_docx(yol, veri, paragraflar, ceviri_paragraflar, dil):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from transkript import zaman_uzun
    doc = Document()
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.left_margin = s.right_margin = Cm(2.2); s.top_margin = s.bottom_margin = Cm(2)
    st = doc.styles["Normal"]; st.font.name = "Helvetica Neue"; st.font.size = Pt(10.5)
    GRI = RGBColor(0x6E, 0x6E, 0x73)
    p = doc.add_paragraph(); r = p.add_run(veri.get("baslik") or ""); r.bold = True; r.font.size = Pt(16)
    bilgi = [veri.get("kanal"), f"{DIL_ADI.get(veri.get('dil'), veri.get('dil'))} → {DIL_ADI.get(dil, dil)}", veri.get("link")]
    p = doc.add_paragraph(); r = p.add_run("  ·  ".join(b for b in bilgi if b)); r.font.size = Pt(9); r.font.color.rgb = GRI
    o = (veri.get("ceviriler") or {}).get(dil, {}).get("ozet")
    if o:
        p = doc.add_paragraph(); r = p.add_run({"en": "Summary", "de": "Zusammenfassung", "fr": "Résumé", "es": "Resumen"}.get(dil, "Özet")); r.bold = True; r.font.size = Pt(12)
        doc.add_paragraph(o["ozet"])
        for m in o.get("maddeler", []):
            doc.add_paragraph(m, style="List Bullet")
    saatli = any(pp["bas"] >= 3600 for pp in paragraflar)
    for pa, ce in zip(paragraflar, ceviri_paragraflar):
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(f"[{zaman_uzun(pa['bas'], saatli)}] {pa['ad']}"); r.bold = True; r.font.size = Pt(9.5)
        p = doc.add_paragraph(ce); p.paragraph_format.space_after = Pt(1)
        p = doc.add_paragraph(); r = p.add_run(pa["metin"]); r.font.size = Pt(9); r.font.color.rgb = GRI; r.italic = True
    doc.save(yol)


def paragraf_ceviri(segmentler, etiket, ceviri_segmentler):
    """Çevrilmiş segmentleri paragrafla() ile aynı kurala göre paragraflara toplar."""
    from transkript import paragrafla
    orijinal = paragrafla(segmentler, etiket)
    sonuc, i = [], 0
    for pa in orijinal:
        parca = []
        while i < len(segmentler) and segmentler[i]["bit"] <= pa["bit"] + 1e-6 and segmentler[i]["bas"] >= pa["bas"] - 1e-6:
            parca.append(ceviri_segmentler[i]); i += 1
        sonuc.append(" ".join(parca).strip())
    return orijinal, sonuc


def cevir(json_yolu, dil, log=log):
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8"))
    veri, seg = d["veri"], d["segmentler"]
    if veri.get("toplanti"):
        os.environ["VH_TOPLANTI"] = "1"          # toplantı içeriği: Claude yalnızca toplantı izni açıksa
    kaynak = veri.get("dil") or "tr"
    kaynak_adi, hedef_adi = DIL_ADI.get(kaynak, kaynak), DIL_ADI.get(dil, dil)
    if not ozet_modulu.hazir():
        raise SystemExit("HATA: Çeviri modeli hazır değil (Ollama çalışmıyor ya da model inmemiş).")
    if ozet_modulu.claude_hazir():
        import claude_yaz
        model = claude_yaz.etiket()
    else:
        model = _ceviri_modeli() or ozet_modulu.MODEL
    log(f"[1/3] {kaynak_adi} → {hedef_adi} çeviri başlıyor ({len(seg)} cümle, {model})")
    metinler = [s["metin"] for s in seg]
    baglam = f"{veri.get('baslik') or ''}. " + str((veri.get("ozet") or {}).get("ozet") or "")[:800]
    cevrilmis = _satirlari_cevir(metinler, kaynak_adi, hedef_adi, log, kaynak, dil, baglam=baglam)
    log("[2/3] Özet çevriliyor" if veri.get("ozet") else "[2/3] Özet yok, atlandı")
    oz = _ozet_cevir(veri.get("ozet"), kaynak_adi, hedef_adi, log, kaynak, dil) if veri.get("ozet") else None
    veri.setdefault("ceviriler", {})[dil] = {"segmentler": cevrilmis, "ozet": oz, "model": model, "tarih": time.time()}
    log("[3/3] Dosyalar yazılıyor")
    temel = json_yolu.with_suffix("")
    from transkript import yaz_srt, zaman_uzun
    cseg = [{**s, "metin": m, "kelimeler": None} for s, m in zip(seg, cevrilmis)]
    yaz_srt(f"{temel}.{dil}.srt", veri, cseg)
    paragraflar, cpar = paragraf_ceviri(seg, veri["etiket"], cevrilmis)
    saatli = any(p["bas"] >= 3600 for p in paragraflar)
    with open(f"{temel}.{dil}.txt", "w", encoding="utf-8") as f:
        f.write(f"{veri.get('baslik', '')}\n{kaynak_adi} → {hedef_adi}\n\n")
        if oz:
            f.write(oz["ozet"] + "\n" + "".join(f"  • {m}\n" for m in oz.get("maddeler", [])) + "\n")
        for pa, ce in zip(paragraflar, cpar):
            f.write(f"[{zaman_uzun(pa['bas'], saatli)}] {pa['ad']}: {ce}\n\n")
    _yaz_docx(f"{temel}.{dil}.docx", veri, paragraflar, cpar, dil)
    import kayit_json                                        # 2026-10-25: dosya yeniden okunur, yalnız ceviriler[dil] yazılır (aradaki ad/paylaşım/kurgu değişiklikleri silinmez)
    def _yaz(d):
        d["veri"].setdefault("ceviriler", {})[dil] = veri["ceviriler"][dil]
    kayit_json.guncelle(json_yolu, _yaz)
    log(f"Bitti. Dosya: {temel}.{dil}.docx")
    return veri["ceviriler"][dil]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(1)
    cevir(sys.argv[1], sys.argv[2].lower())

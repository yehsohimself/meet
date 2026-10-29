#!/usr/bin/env python3
"""
sor.py - Kitaplıktaki transkriptlerde arama ve soru-cevap (yerel Ollama modeliyle; dışarı veri gitmez).

  ara("fiyat")                 → eşleşen paragraflar (transkript, zaman, metin)
  sor("X hakkında ne dedi?", temel=None|"transkript_tr_...") → {"cevap": "...", "kaynaklar": [...]}
Yöntem: anahtar kelime eşleşmesiyle en ilgili 12 paragraf seçilir, modele kaynak numaralarıyla verilir;
model yalnızca bu kaynaklara dayanarak yanıtlar ve [n] ile kaynak gösterir.
"""
import json
import re
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
from ozet import _sor  # noqa: E402

DURAK = set("""ve veya ama fakat ile için gibi daha çok az bir bu şu o ki de da mi mı mu mü ne nasıl neden niçin hangi kim
nerede ben sen biz siz onlar var yok evet hayır şey şeyi şeyler olan olarak oldu olur olacak etti eder yapıyor yapmış
the a an and or but of to in on for with is are was were be been this that it its as at by from about what how why
which who where when then than there here""".split())
_bellek = {}


def _belirtec(metin):
    m = metin.replace("İ", "i").replace("I", "ı").lower()
    kelimeler = re.findall(r"[0-9a-zçğıöşüâîû]+", m)
    return {k[:5] for k in kelimeler if len(k) >= 3 and k not in DURAK}


def dizin():
    """Tüm transkriptlerin paragrafları (dosya değişmediyse bellekten)."""
    from transkript import paragrafla
    sonuc = []
    for js in KLASOR.glob("transkript_*.json"):
        try:
            mt = js.stat().st_mtime
            if _bellek.get(js.name, {}).get("mt") == mt:
                sonuc += _bellek[js.name]["p"]; continue
            d = json.loads(js.read_text(encoding="utf-8"))
            v = d["veri"]
            temel = js.stem
            pl = []
            if v.get("onay_bekliyor"):              # toplantıya benzemediği için kullanıcının onayını bekleyen kayıt: aramaya girmez
                _bellek[js.name] = {"mt": mt, "p": []}; continue
            ortak = {"temel": temel, "baslik": v.get("baslik") or temel, "toplanti": bool(v.get("toplanti")), "misafir": v.get("misafir") or "",
                     "musteri": v.get("musteri") or "", "sirket": v.get("sirket") or "", "tarih": v.get("olusturma") or mt}
            o = v.get("ozet")
            if o and o.get("ozet"):
                m = o["ozet"] + " " + " ".join(o.get("maddeler", []))
                if o.get("kararlar"):
                    m += " Kararlar: " + "; ".join(o["kararlar"])
                if o.get("yapilacaklar"):
                    m += " Yapılacaklar: " + "; ".join(o["yapilacaklar"])
                pl.append({**ortak, "sn": 0, "bit": 0, "ad": "Özet", "metin": m, "b": _belirtec(m), "ozet": True})
            for p in paragrafla(d["segmentler"], v["etiket"]):
                pl.append({**ortak, "sn": int(p["bas"]), "bit": p["bit"], "ad": p["ad"], "metin": p["metin"], "b": _belirtec(p["metin"])})
            _bellek[js.name] = {"mt": mt, "p": pl}
            sonuc += pl
        except Exception:  # noqa: BLE001
            continue
    try:                                          # Studio davetlileri (2026-10-24): sahip misafirlerin kayıtlarını, misafir yalnız kendininkini görür
        import claude_yaz
        m = (claude_yaz.misafir() or {}).get("id") or ""
    except Exception:  # noqa: BLE001
        m = ""
    return [p for p in sonuc if (p.get("misafir") or "") == m]


def _puan(p, b, ham):
    if not b:
        return 0
    ortak = len(b & p["b"])
    if not ortak:
        return 0
    puan = ortak / len(b)
    if ham and ham in p["metin"].replace("İ", "i").replace("I", "ı").lower():
        puan += 0.6
    if p.get("ozet"):
        puan *= 0.9
    return puan


def ara(q, limit=80, temel=None):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    b = _belirtec(q); ham = q.replace("İ", "i").replace("I", "ı").lower()
    hits = []
    for p in dizin():
        if temel and p["temel"] != temel:
            continue
        if p.get("ozet"):
            continue
        s = _puan(p, b, ham)
        if s > 0:
            hits.append((s, p))
    hits.sort(key=lambda x: (-x[0], x[1]["temel"], x[1]["sn"]))
    return [{"temel": p["temel"], "baslik": p["baslik"], "sn": p["sn"], "ad": p["ad"], "metin": p["metin"], "puan": round(s, 2)} for s, p in hits[:limit]]


def _zaman(sn):
    import ortak                                           # tek sürüm: bir saatin üstünde h:mm:ss (2026-10-25)
    return ortak.zaman(sn)


def _kapsamda(p, temel, kapsam):
    if temel:
        return p["temel"] == temel
    if kapsam == "toplanti":
        return p.get("toplanti")
    if kapsam and kapsam.startswith("m:"):
        return (p.get("musteri") or "Diğer") == kapsam[2:]
    if kapsam and kapsam.startswith("s:"):
        return p.get("toplanti") and p.get("sirket") == kapsam[2:]
    return True


def _claude_sor(soru, adaylar, temel, kapsam, log):
    """Claude ile: tek transkriptte metnin tamamı; kitaplıkta/müşteride en ilgili 70 paragraf + ilgili özetler; sentez."""
    import claude_yaz
    b = _belirtec(soru); ham = soru.replace("İ", "i").replace("I", "ı").lower()
    if temel and sum(len(p["metin"].split()) for p in adaylar) < 45000:
        secili = list(range(len(adaylar)))
    else:
        puanli = sorted(((_puan(p, b, ham), i) for i, p in enumerate(adaylar)), key=lambda x: -x[0])
        secili = [i for sc, i in puanli if sc > 0][:70]
        ilgili = {adaylar[i]["temel"] for i in secili}
        musteri_kapsami = bool(kapsam and kapsam.startswith(("m:", "s:")))
        # özetler: eşleşen transkriptlerin ve müşteri kapsamında hepsinin (en yeniden eskiye, en çok 25)
        ozetler = sorted((i for i, p in enumerate(adaylar) if p.get("ozet") and (musteri_kapsami or p["temel"] in ilgili)),
                         key=lambda i: -(adaylar[i].get("tarih") or 0))[:25]
        secili = sorted(set(secili) | set(ozetler), key=lambda i: (adaylar[i]["temel"], adaylar[i]["sn"]))
    if not secili:
        return None
    kaynaklar = [adaylar[i] for i in secili]
    metin = "\n".join(f"[{n + 1}] ({k['baslik'][:70]} · {time.strftime('%d.%m.%Y', time.localtime(k.get('tarih') or 0))} · {_zaman(k['sn'])} · {k['ad']}) {k['metin']}"
                      for n, k in enumerate(kaynaklar))
    kapsam_ad = "bu transkript" if temel else ("toplantılar" if kapsam == "toplanti" else (f"{kapsam[2:]} müşterisiyle yapılan toplantılar" if kapsam and kapsam.startswith("m:") else (f"{kapsam[2:]} şirketinin toplantıları" if kapsam and kapsam.startswith("s:") else "tüm kitaplık")))
    istem = (f"Aşağıda video ve toplantı transkriptlerinden numaralı kaynak parçaları var (kapsam: {kapsam_ad}). Soruyu YALNIZCA bu kaynaklara "
             "dayanarak, doğal ve sade Türkçeyle yanıtla. Kullandığın her bilginin sonuna kaynak numarasını köşeli parantezle ekle, örn. [3]. "
             "Birden fazla video ya da toplantı ilgiliyse sentez yap: kim nerede ne dedi, görüşler nerede ayrışıyor, zaman içinde ne değişti "
             "(tarih belirt). Kaynaklarda yanıt yoksa açıkça söyle; uydurma. Gerekirse kısa maddeler kullan; en fazla 12 cümle.\n\n"
             f"SORU: {soru}\n\nKAYNAKLAR:\n{metin}")
    log("      Soru Claude'a gönderiliyor...")
    toplanti_var = any(k.get("toplanti") for k in kaynaklar)
    if toplanti_var and not claude_yaz.hazir(toplanti_icerik=True):
        return None
    cevap = claude_yaz.sor(istem, "Sen kullanıcının video ve toplantı arşivini bilen titiz bir araştırma asistanısın.", zaman_asimi=300).strip()
    return cevap, kaynaklar


def sor(soru, temel=None, log=lambda *_: None, kapsam=None):
    soru = (soru or "").strip()
    if not soru:
        return {"cevap": "", "kaynaklar": []}
    b = _belirtec(soru); ham = soru.replace("İ", "i").replace("I", "ı").lower()
    adaylar = [p for p in dizin() if _kapsamda(p, temel, kapsam)]
    if temel:
        adaylar.sort(key=lambda p: (not p.get("ozet"), p["sn"]))
    try:
        import claude_yaz
        sonuc = _claude_sor(soru, adaylar, temel, kapsam, log) if claude_yaz.hazir() else None
    except Exception as e:  # noqa: BLE001
        log(f"      Claude yanıt vermedi ({e})"); sonuc = None
    if sonuc:
        cevap, kaynaklar = sonuc
        return _kaynakli(cevap, kaynaklar)
    puanli = sorted(((_puan(p, b, ham), i) for i, p in enumerate(adaylar)), key=lambda x: -x[0])
    secili = [i for s, i in puanli if s > 0][:12]
    if temel:
        # tek transkriptte: özet her zaman dahil, komşu paragraflar bağlam için
        ek = set(secili)
        for i in list(secili):
            ek.update(j for j in (i - 1, i + 1) if 0 <= j < len(adaylar))
        ek.update(i for i, p in enumerate(adaylar) if p.get("ozet"))
        if not secili:
            ek.update(range(min(len(adaylar), 14)))
        secili = sorted(ek)[:24]
    if not secili:
        return {"cevap": "Bu konuda kitaplıktaki transkriptlerde bir şey bulamadım.", "kaynaklar": []}
    kaynaklar = [adaylar[i] for i in secili]
    metin = "\n".join(f"[{n + 1}] ({k['baslik'][:60]} · {_zaman(k['sn'])} · {k['ad']}) {k['metin']}" for n, k in enumerate(kaynaklar))
    istem = ("Aşağıda video transkriptlerinden alınmış numaralı kaynak parçaları var. Soruyu YALNIZCA bu kaynaklara dayanarak, "
             "Türkçe ve sade bir dille yanıtla. Kullandığın her bilginin sonuna kaynak numarasını köşeli parantezle ekle, örn. [3]. "
             "Kaynaklarda yanıt yoksa açıkça 'Bu bilgi transkriptlerde geçmiyor' de; uydurma. En fazla 6 cümle.\n\n"
             f"SORU: {soru}\n\nKAYNAKLAR:\n{metin}")
    log("      Soru modele gönderiliyor...")
    import claude_yaz
    from contextlib import nullcontext
    with (claude_yaz.toplanti() if any(k.get("toplanti") for k in kaynaklar) else nullcontext()):
        cevap = _sor(istem, json_bekle=False, num_ctx=8192, zaman_asimi=300).strip()
    return _kaynakli(cevap, kaynaklar)


def _kaynakli(cevap, kaynaklar):
    kullanilan = []
    for m in re.findall(r"\[(\d+)\]", cevap):
        n = int(m) - 1
        if 0 <= n < len(kaynaklar) and n not in kullanilan:
            kullanilan.append(n)
    if not kullanilan:
        kullanilan = list(range(min(3, len(kaynaklar))))
    return {"cevap": cevap, "kaynaklar": [{"no": n + 1, "temel": kaynaklar[n]["temel"], "baslik": kaynaklar[n]["baslik"], "sn": kaynaklar[n]["sn"],
                                           "zaman": _zaman(kaynaklar[n]["sn"]), "ad": kaynaklar[n]["ad"], "metin": kaynaklar[n]["metin"][:220]} for n in kullanilan]}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    t0 = time.time()
    r = sor(" ".join(sys.argv[1:]))
    print(r["cevap"]); print()
    for k in r["kaynaklar"]:
        print(f"[{k['no']}] {k['baslik']} · {k['zaman']} · {k['ad']}: {k['metin'][:100]}")
    print(f"({time.time() - t0:.0f} sn)")

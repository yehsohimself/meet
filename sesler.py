#!/usr/bin/env python3
"""
sesler.py - Konuşmacı tanıma: bir kez adlandırılan kişinin ses izi saklanır, sonraki videolarda kendiliğinden tanınır.

Ses izi: konuşmacı ayırma modelinin (3D-Speaker CAM++) 192 boyutlu vektörü; her konuşmacı için en uzun
parçalardan (toplam ≤ 60 sn) ortalama alınır. Profiller `sesler.json`'da: {"Ali": {"vektor": [...], "sayac": n}}.
Yeni transkriptte her konuşmacı kümesi profillerle kosinüs benzerliğiyle karşılaştırılır; eşik üstü ve tekil
eşleşmeler ad olarak yazılır (kullanıcı --isimler verdiyse onlar önceliklidir).

Ölçüm (kalibrasyon): python sesler.py --olc ses1.m4a ses2.m4a
"""
import json
import math
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
DOSYA = KLASOR / "sesler.json"
ESIK = 0.6             # ölçüm: aynı kişi iki videoda 0.94, farklı kişiler 0.29-0.46
EN_COK_SN = 60.0


def oku():
    try:
        return json.loads(DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def yaz(d):
    DOSYA.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def benzerlik(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    a, b = _norm(a), _norm(b)
    return sum(x * y for x, y in zip(a, b))


def izleri_cikar(ornekler, parcalar, model_yolu, num_threads=4, log=lambda *_: None):
    """ornekler: 16 kHz float32 numpy; parcalar: [(bas, bit, k)] -> {k: vektor}"""
    import numpy as np
    import sherpa_onnx
    ex = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model_yolu), num_threads=num_threads))
    kisiler = sorted({p[2] for p in parcalar})
    izler = {}
    for k in kisiler:
        secili = sorted([p for p in parcalar if p[2] == k], key=lambda p: -(p[1] - p[0]))
        vektorler, toplam = [], 0.0
        for bas, bit, _ in secili:
            if bit - bas < 1.0:
                continue
            a, b = int(bas * 16000), int(bit * 16000)
            if b - a < 16000:
                continue
            st = ex.create_stream()
            st.accept_waveform(16000, ornekler[a:b])
            st.input_finished()
            if not ex.is_ready(st):
                continue
            v = ex.compute(st)
            v = np.asarray(v, dtype=np.float32)
            v = v / (np.linalg.norm(v) or 1.0)
            agirlik = bit - bas
            vektorler.append(v * agirlik); toplam += agirlik
            if toplam >= EN_COK_SN:
                break
        if vektorler and toplam > 0:
            orta = np.sum(vektorler, axis=0) / toplam
            izler[k] = [float(x) for x in orta / (np.linalg.norm(orta) or 1.0)]
    log(f"      Ses izi çıkarıldı: {len(izler)} konuşmacı")
    return izler


def toplanti_sayilarini_kur():
    """Her profilin 'toplanti' sayısını kayıtlardan yeniden kurar: adın bir toplantıda sesten tanınmadan (elle, uzantıyla, mikrofondan)
    verildiği toplantı sayısı. Davetli kayıtları sayılmaz. Döner: {ad: sayı}."""
    import glob
    P = oku(); say = {a: 0 for a in P}
    for f in glob.glob(str(KLASOR / "transkript_*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                v = json.loads(fh.read()).get("veri") or {}
        except Exception:  # noqa: BLE001
            continue
        if not v.get("toplanti") or v.get("misafir") or v.get("onay_bekliyor"):
            continue
        tan = set(v.get("taninan") or [])
        for ad in set((v.get("etiket") or {}).values()):
            if ad in say and ad not in tan:
                say[ad] += 1
    for a, n in say.items():
        if n:
            P[a]["toplanti"] = n
        else:
            P[a].pop("toplanti", None)
    yaz(P)
    return say


def toplanti_profilleri(profiller=None):
    """Toplantılarda kullanılabilen profiller: en az bir toplantıda elle (sesten tanınmadan) adı verilmiş olanlar. 2026-10-27: YouTube
    videolarından öğrenilen 'Umut' ve 'Aysan' sesleri toplantılarda başka kişilere verilmişti; video sesleri toplantıya taşınmaz."""
    profiller = oku() if profiller is None else profiller
    return {a: p for a, p in profiller.items() if int(p.get("toplanti", 0)) > 0}


def tani(izler, esik=ESIK, toplanti=False):
    """{k: vektor} -> {k: ad}; her ad en çok bir kümeye, her küme en çok bir ada (en yüksek benzerlik önce).
    toplanti=True: yalnız toplantılarda öğrenilmiş profiller (toplanti_profilleri)."""
    profiller = toplanti_profilleri() if toplanti else oku()
    if not profiller or not izler:
        return {}
    adaylar = []
    for k, v in izler.items():
        for ad, p in profiller.items():
            s = benzerlik(v, p.get("vektor", []))
            if s >= esik:
                adaylar.append((s, k, ad))
    adaylar.sort(reverse=True)
    sonuc, kullanilan_ad = {}, set()
    for s, k, ad in adaylar:
        if k in sonuc or ad in kullanilan_ad:
            continue
        sonuc[k] = ad; kullanilan_ad.add(ad)
    return sonuc


def ogren(veri, log=lambda *_: None):
    """Adlandırılmış konuşmacıların izlerini profillere katar (ağırlıklı ortalama). Döner: öğrenilen adlar."""
    izler = veri.get("sesler") or {}
    if not izler:
        return []
    profiller = oku()
    ogrenilen = []
    taninan = set(veri.get("taninan") or [])
    for k, ad in (veri.get("etiket") or {}).items():
        ad = (ad or "").strip()
        if not ad or ad.lower().startswith("konuşmacı ") or k not in izler:
            continue
        v = izler[k]
        p = profiller.get(ad)
        toplanti = int((p or {}).get("toplanti", 0)) + (1 if veri.get("toplanti") and ad not in taninan else 0)   # sesten tanınan ad toplantı sayılmaz
        if p and p.get("vektor"):
            n = int(p.get("sayac", 1))
            if benzerlik(v, p["vektor"]) < 0.3:       # bambaşka bir ses: aynı ad farklı kişiye verilmiş olabilir, üzerine yazma
                continue
            yeni = [(x * n + y) / (n + 1) for x, y in zip(p["vektor"], v)]
            profiller[ad] = {"vektor": _norm(yeni), "sayac": min(n + 1, 20)}
        else:
            profiller[ad] = {"vektor": _norm(v), "sayac": 1}
        if toplanti:
            profiller[ad]["toplanti"] = min(toplanti, 50)
        ogrenilen.append(ad)
    if ogrenilen:
        yaz(profiller)
        log("      Ses izi öğrenildi: " + ", ".join(ogrenilen))
    return ogrenilen


def sil(ad):
    p = oku()
    if ad in p:
        del p[ad]; yaz(p); return True
    return False


def _olc(dosyalar):
    """Kalibrasyon: her dosyayı konuşmacılara ayır, izleri çıkar, dosyalar arası benzerlikleri yazdır."""
    import numpy as np
    from faster_whisper.audio import decode_audio
    sys.path.insert(0, str(KLASOR))
    import transkript as T
    T.modelleri_hazirla()
    tum = {}
    for d in dosyalar:
        parcalar = T.konusmacilari_ayir(d, None)
        ornekler = decode_audio(str(d), sampling_rate=16000).astype(np.float32)
        izler = izleri_cikar(ornekler, parcalar, T.EMB_MODEL, log=print)
        sure = {}
        for b, e, k in parcalar:
            sure[k] = sure.get(k, 0) + e - b
        for k, v in izler.items():
            tum[f"{Path(d).stem}#{k} ({sure[k]:.0f}sn)"] = v
    adlar = list(tum)
    print("\nBenzerlik matrisi (kosinüs):")
    print(" " * 34 + "".join(f"{i:>8}" for i in range(len(adlar))))
    for i, a in enumerate(adlar):
        print(f"{i:>2} {a[:30]:<31}" + "".join(f"{benzerlik(tum[a], tum[b]):8.2f}" for b in adlar))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--olc":
        _olc(sys.argv[2:])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--toplanti-say":
        print(toplanti_sayilarini_kur())
    elif len(sys.argv) >= 3 and sys.argv[1] == "--sil":
        print("silindi" if sil(sys.argv[2]) else "yok")
    else:
        p = oku()
        print(f"{len(p)} ses profili: " + ", ".join(f"{a} ({v.get('sayac', 1)} kayıt)" for a, v in p.items()) if p else "Henüz ses profili yok.")

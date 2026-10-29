"""anlam.py - Kitaplıkta anlam üzerinden arama (kelime birebir geçmese de): bilgisayarda çalışan çok dilli küçük model
(multilingual-e5-small, MLX, ~470 MB, `~/.cache/huggingface`).

Ölçüm (2026-10-20, M4): 4.306 paragraf ilk dizinleme 256 sn (bir kez), sorgu 15-45 ms (ilk sorguda ~3 sn model yükleme).
Dizin: `.onbellek/anlam/<temel>.npz` (paragraf başlangıç saniyeleri + float16 vektörler); transkript değişince yenilenir.
Dizinleme site içinde DEĞİL, düşük öncelikli alt süreçte (`nice -n 15 python anlam.py --guncelle`), yalnız sırada iş yokken.
6 kelimeden kısa paragraflar dizine girmez ("You owe me." gibi parçalar sonuçları bozuyordu). Özet paragrafları da girer (sn=-1).
Elle: python anlam.py --guncelle | python anlam.py "aranan şey"
"""
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

KLASOR = Path(__file__).resolve().parent
DIZIN = KLASOR / ".onbellek" / "anlam"
MODEL = "mlx-community/multilingual-e5-small-mlx"
EN_AZ_KELIME = 6
_kilit = threading.Lock()
_m = {"model": None, "tok": None}
_bellek = {}          # temel -> (mtime, sn dizisi, vektörler)


def _yukle():
    with _kilit:
        if _m["model"] is None:
            from mlx_embeddings.utils import load
            _m["model"], _m["tok"] = load(MODEL)
    return _m["model"], _m["tok"]


def kodla(metinler, toplu=32):
    import mlx.core as mx
    model, tok = _yukle()
    cikti = []
    for i in range(0, len(metinler), toplu):
        b = tok._tokenizer(metinler[i:i + toplu], return_tensors="np", padding=True, truncation=True, max_length=256)
        o = model(mx.array(b["input_ids"]), attention_mask=mx.array(b["attention_mask"]))
        cikti.append(np.array(o.text_embeds.astype(mx.float32)))
    return np.concatenate(cikti) if cikti else np.zeros((0, 384), dtype=np.float32)


def _paragraflar(js):
    from transkript import paragrafla
    d = json.loads(js.read_text(encoding="utf-8"))
    v = d["veri"]
    L = []
    o = v.get("ozet") or {}
    if o.get("ozet"):
        L.append((-1, o["ozet"] + " " + " ".join(o.get("maddeler", []))))
    for p in paragrafla(d["segmentler"], v["etiket"]):
        if len(p["metin"].split()) >= EN_AZ_KELIME:
            L.append((int(p["bas"]), p["metin"]))
    return L


def guncelle(log=print):
    """Eksik ya da eskimiş dizinleri yazar; dönen: güncellenen transkript sayısı."""
    DIZIN.mkdir(parents=True, exist_ok=True)
    n = 0
    for js in sorted(KLASOR.glob("transkript_*.json"), key=lambda p: -p.stat().st_mtime):
        hedef = DIZIN / f"{js.stem}.npz"
        if hedef.exists() and hedef.stat().st_mtime >= js.stat().st_mtime:
            continue
        try:
            L = _paragraflar(js)
            E = kodla(["passage: " + m for _, m in L]) if L else np.zeros((0, 384))
            np.savez(hedef, sn=np.array([s for s, _ in L], dtype=np.int32), e=E.astype(np.float16))
            n += 1
        except Exception as e:  # noqa: BLE001
            log(f"{js.name}: {e}")
    for eski in DIZIN.glob("*.npz"):                     # silinen transkriptlerin dizinleri
        if not (KLASOR / f"{eski.stem}.json").exists():
            eski.unlink(missing_ok=True)
    return n


def _dizinler():
    for f in DIZIN.glob("*.npz"):
        mt = f.stat().st_mtime
        b = _bellek.get(f.stem)
        if not b or b[0] != mt:
            try:
                z = np.load(f)
                e = z["e"].astype(np.float32)
                e /= np.linalg.norm(e, axis=1, keepdims=True) + 1e-9
                _bellek[f.stem] = (mt, z["sn"], e)
            except Exception:  # noqa: BLE001
                continue
    for k in [k for k in _bellek if not (DIZIN / f"{k}.npz").exists()]:
        _bellek.pop(k, None)
    return _bellek


def ara(q, limit=12, temel=None, esik=0.86):
    """[(puan, temel, sn)] en yakın paragraflar (sn=-1 özet). Dizin yoksa boş."""
    D = _dizinler()
    if not D or len((q or "").strip()) < 3:
        return []
    qe = kodla(["query: " + q.strip()])[0]
    qe /= np.linalg.norm(qe) + 1e-9
    sonuc = []
    for t, (_mt, sn, e) in D.items():
        if temel and t != temel:
            continue
        if not len(sn):
            continue
        s = e @ qe
        for i in np.argsort(-s)[:3]:
            if s[i] >= esik:
                sonuc.append((float(s[i]), t, int(sn[i])))
    sonuc.sort(key=lambda x: -x[0])
    return sonuc[:limit]


def durum():
    toplam = len(list(KLASOR.glob("transkript_*.json")))
    hazir = sum(1 for js in KLASOR.glob("transkript_*.json") if (DIZIN / f"{js.stem}.npz").exists()
                and (DIZIN / f"{js.stem}.npz").stat().st_mtime >= js.stat().st_mtime)
    return {"toplam": toplam, "hazir": hazir}


if __name__ == "__main__":
    sys.path.insert(0, str(KLASOR))
    if sys.argv[1:] == ["--guncelle"]:
        t = time.time()
        print(f"{guncelle()} transkript dizinlendi ({time.time() - t:.0f} sn)", flush=True)
    else:
        for p, t, sn in ara(" ".join(sys.argv[1:])):
            print(round(p, 3), t, sn)

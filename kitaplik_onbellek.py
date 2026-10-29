"""kitaplik_onbellek.py - Kitaplık JSON'larının `veri` bölümü için mtime anahtarlı bellek önbelleği (2026-10-25 backend gözden geçirmesi).

Neden: 46 ayrı yer `transkript_*.json` dosyalarını her çağrıda baştan okuyup ayrıştırıyordu (14 MB, ~190 ms; /api/paylasimlar 367 ms, sozler 150 ms...).
Çoğunun yalnız `veri`ye ihtiyacı var; `segmentler` dizisi dosyanın %90'ı. Burada dosya metninin başındaki `"veri": {...}` nesnesi
`raw_decode` ile tek başına çözülür (segmentler hiç ayrıştırılmaz), sonuç dosyanın (mtime, boyut) anahtarıyla bellekte tutulur.

hepsi(ghost=False)  -> [{"yol", "temel", "veri", "mtime"}]  (yalnız değişen dosyalar yeniden okunur; silinenler düşer)
veri(temel)         -> dict | None
segmentler(temel)   -> list  (önbelleksiz; tam dosya)
"""
import json
import threading
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
_bellek = {}                     # yol -> (mtime, boyut, veri)
_kilit = threading.Lock()
_coz = json.JSONDecoder()


def _veri_coz(metin):
    """Dosyadaki `"veri": {...}` nesnesini segmentleri ayrıştırmadan çıkarır; biçim beklenmedikse tam ayrıştırmaya düşer."""
    i = metin.find('"veri"')
    if 0 <= i < 40:
        j = metin.find("{", i + 6)
        if j > 0:
            try:
                v, _son = _coz.raw_decode(metin, j)
                if isinstance(v, dict):
                    return v
            except ValueError:
                pass
    return json.loads(metin)["veri"]


def _oku(yol):
    try:
        st = yol.stat()
    except OSError:
        return None
    anahtar = (st.st_mtime, st.st_size)
    with _kilit:
        k = _bellek.get(yol)
    if k and (k[0], k[1]) == anahtar:
        return k[2]
    try:
        v = _veri_coz(yol.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    with _kilit:
        _bellek[yol] = (st.st_mtime, st.st_size, v)
    return v


def hepsi(ghost=False, klasor=None):
    klasor = Path(klasor) if klasor else KLASOR
    yollar = list(klasor.glob("transkript_*.json"))
    if ghost:
        yollar += list((klasor / "ghost").glob("*.json"))
    out = []
    gorulen = set()
    for yol in yollar:
        gorulen.add(yol)
        v = _oku(yol)
        if v is not None:
            out.append({"yol": yol, "temel": yol.stem, "veri": v, "mtime": _bellek[yol][0]})
    with _kilit:
        for eski in [k for k in _bellek if k.parent in (klasor, klasor / "ghost") and k not in gorulen]:
            _bellek.pop(eski, None)
    return out


def veri(temel, klasor=None):
    klasor = Path(klasor) if klasor else KLASOR
    yol = klasor / f"{temel}.json"
    return _oku(yol) if yol.exists() else None


def segmentler(temel, klasor=None):
    klasor = Path(klasor) if klasor else KLASOR
    try:
        return json.loads((klasor / f"{temel}.json").read_text(encoding="utf-8")).get("segmentler") or []
    except Exception:  # noqa: BLE001
        return []


def durum():
    with _kilit:
        return {"dosya": len(_bellek)}


if __name__ == "__main__":
    t0 = time.perf_counter(); n = len(hepsi(ghost=True)); t1 = time.perf_counter(); hepsi(ghost=True); t2 = time.perf_counter()
    print(f"{n} dosya: soğuk {1000 * (t1 - t0):.0f} ms, sıcak {1000 * (t2 - t1):.0f} ms")

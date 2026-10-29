"""dil.py - Sunucu tarafında arayüz dili (2026-10-25). Belge başlıkları (Word/metin/SRT) ve dosyaya yazılan sabit metinler için.

`t(s)`: ayarlar.json `dil` == "en" ise static/dil/en.json sözlüğündeki (dil_cevir.py üretir; tarayıcıdaki dil.js ile aynı dosya) birebir
karşılık; yoksa ya da dil Türkçe ise metin olduğu gibi. Kalıplar (`{n}`) için önce `t` sonra `.format`. Sözlük dosya değişince yeniden okunur.
"""
import json
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
_onb = {"zaman": 0, "mtime": 0, "exact": {}, "dil": "tr"}


def secili():
    """Kullanıcının arayüz dili: ayarlar.json `dil` (tr | en); yoksa tr. 30 sn önbellek."""
    if time.time() - _onb["zaman"] > 30:
        try:
            import ortak
            _onb["dil"] = str(ortak.ayar().get("dil") or "tr")
        except Exception:  # noqa: BLE001
            _onb["dil"] = "tr"
        _onb["zaman"] = time.time()
    return _onb["dil"] if _onb["dil"] in ("tr", "en") else "tr"


def _sozluk():
    y = KLASOR / "static" / "dil" / "en.json"
    try:
        m = y.stat().st_mtime
        if m != _onb["mtime"]:
            _onb["exact"] = json.loads(y.read_text(encoding="utf-8")).get("exact") or {}
            _onb["mtime"] = m
    except OSError:
        _onb["exact"] = {}
    return _onb["exact"]


def t(s, dil=None):
    dil = dil or secili()
    if dil == "tr" or not s:
        return s
    return _sozluk().get(s, s)

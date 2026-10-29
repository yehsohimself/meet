"""kalite.py - Ölçerek kalite: üretim çalışmalarının kalite sinyalleri ve kullanıcı kararları tek bir kayıtta.

Neden (2026-10-19 teknik değerlendirme): istemler gözle ayarlanıyordu; bir değişikliğin iyileştirip iyileştirmediği sayıyla bilinmiyordu.
Her kayıt `surum` taşır (paylaşım 3, atölye vb.) ki istem değişikliklerinden önce ve sonra karşılaştırılabilsin.
Kaynaklar: paylaşım üretimi (taslak sayısı, okur puanları), paylaşım kararları (paylaşıldı / kaldırıldı + neden), atölye çalışması
(süre, hakem puanı, kural notu, kart kullanımı), atölye beğeni kararları, bilgi kartı kurulumu, transkript işleri (süre oranı).
Kayıt: kayitlar/.kalite.jsonl. Özet: `ozet(gun)` → gözlem paneli (Ayarlar → Sistem).
"""
import json
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
KAYIT = KLASOR / "kayitlar" / ".kalite.jsonl"


def kaydet(ozellik, **olcu):
    try:
        KAYIT.parent.mkdir(exist_ok=True)
        with KAYIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "ozellik": ozellik, **olcu}, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _oku(gun):
    sinir = time.time() - gun * 86400
    try:
        return [x for x in (json.loads(s) for s in KAYIT.read_text(encoding="utf-8").splitlines() if s.strip()) if x.get("t", 0) > sinir]
    except Exception:  # noqa: BLE001
        return []


def _ort(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 2) if xs else None


def ozet(gun=30):
    L = _oku(gun)
    by = {}
    for x in L:
        by.setdefault(x["ozellik"], []).append(x)
    p = by.get("paylasim", []); k = by.get("paylasim_karar", [])
    a = by.get("atolye", []); ak = by.get("atolye_karar", []); t = by.get("transkript", [])
    return {
        "paylasim": {"video": len(p), "taslak": sum(x.get("taslak", 0) for x in p), "ort_deger": _ort([x.get("ort_deger") for x in p]),
                     "ort_ses": _ort([x.get("ort_ses") for x in p]), "paylasilan": sum(1 for x in k if x.get("karar") == "paylasildi"),
                     "kaldirilan": sum(1 for x in k if x.get("karar") == "kaldirildi"), "duzenlenen": sum(1 for x in k if x.get("duzenlendi")),
                     "nedenler": {n: sum(1 for x in k if x.get("neden") == n) for n in {x.get("neden") for x in k if x.get("neden")}}},
        "atolye": {"calisma": len(a), "ort_dk": _ort([x.get("sure_dk") for x in a]), "ort_hakem": _ort([x.get("hakem_ort") for x in a]),
                   "kural_notu": sum(x.get("kural_notu", 0) for x in a), "begeni": sum(1 for x in ak if x.get("puan") == "iyi"),
                   "begenmeme": sum(1 for x in ak if x.get("puan") == "kotu")},
        "bilgi_karti": {"kurulum": len(by.get("bilgi_karti", [])), "video": sum(x.get("yeni", 0) for x in by.get("bilgi_karti", []))},
        "transkript": {"is": len(t), "ort_oran": _ort([x.get("oran") for x in t])},
    }


if __name__ == "__main__":
    print(json.dumps(ozet(), ensure_ascii=False, indent=1))

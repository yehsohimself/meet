"""adlar.py - Konuşmacı adlarını konuşmanın kendisinden çıkarır (öneri olarak).

"Konuşmacı 2" diye kalan kişiler için metindeki ipuçlarına bakılır: kendini tanıtma ("ben Ayşe"), hitap
("Ali, sen ne dersin?" dendikten hemen sonra konuşan kişi Ali'dir), üçüncü kişinin söylediği ad.
Ollama (gemma3:4b) ile tek sorgu; sonuç kesin değil, ÖNERİ olarak saklanır: veri["ad_onerileri"] =
[{"etiket": "Konuşmacı 2", "ad": "Ayşe", "kanit": "...", "guven": 0.8}]. Arayüzde "Uygula" ile isimlendirilir.

Elle: python adlar.py transkript_x.json
"""
import json
import re
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))


def _adaylar(metin):
    """Metinde geçen, ad olabilecek büyük harfli kelimeler (hitap/tanıtma kalıplarından)."""
    adlar = set()
    for m in re.finditer(r"\b[Bb]en ([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\b", metin):
        adlar.add(m.group(1))
    for m in re.finditer(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})(?:'[a-zçğıöşü]+)?,? (?:sen|siz|abi|hocam|bey|hanım|kanka|ne dersin|sana|size)\b", metin):
        adlar.add(m.group(1))
    return adlar


def oner(segmentler, etiket, log=print, model=None):
    """Döner: öneri listesi (boş olabilir)."""
    import ozet as ozet_modulu
    from transkript import paragrafla
    bilinmeyen = [a for a in dict.fromkeys(etiket.values()) if str(a).startswith("Konuşmacı ")]
    if not bilinmeyen or not ozet_modulu.hazir():
        return []
    par = paragrafla(segmentler, {str(k): v for k, v in etiket.items()})
    tam = " ".join(p["metin"] for p in par)
    adaylar = _adaylar(tam)
    if not adaylar:
        return []
    # Modele yalnızca ad adaylarının geçtiği paragraflar ve komşuları verilir (kısa ve odaklı)
    secili = set()
    for i, p in enumerate(par):
        if any(re.search(r"\b" + re.escape(a) + r"\b", p["metin"]) for a in adaylar):
            secili.update({i - 1, i, i + 1})
    satirlar = []
    for i in sorted(x for x in secili if 0 <= x < len(par)):
        satirlar.append(f"[{i}] {par[i]['ad']}: {par[i]['metin'][:400]}")
    metin = "\n".join(satirlar)[:12000]
    istem = (
        "Aşağıda bir toplantı transkriptinden seçilmiş paragraflar var. Konuşmacılar 'Konuşmacı 1', 'Konuşmacı 2' gibi etiketli. "
        "Metindeki ipuçlarından bu etiketlerin GERÇEK ADLARINI bulmaya çalış. Kurallar:\n"
        "- 'ben Ayşe' diyen kişi Ayşe'dır.\n"
        "- Biri 'Ali, sen ne dersin?' deyip hemen ardından BAŞKA bir konuşmacı yanıt veriyorsa, yanıt veren Ali'dir; soran değil.\n"
        "- Bir ad hakkında konuşulması (üçüncü kişi) o konuşmacının adı olduğunu göstermez.\n"
        "- Aynı adı iki etikete verme. Emin değilsen önerme. Aday adlar: " + ", ".join(sorted(adaylar)) + ".\n"
        "Yalnızca JSON: {\"oneriler\": [{\"etiket\": \"Konuşmacı 2\", \"ad\": \"Ayşe\", \"kanit\": \"[12] ...\", \"guven\": 0.9}]}\n\n" + metin
    )
    try:
        cevap = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=8192, zaman_asimi=300)) or {}
    except Exception as e:  # noqa: BLE001
        log(f"      Ad çıkarımı yapılamadı ({e})."); return []
    sonuc, kullanilan = [], set()
    for o in cevap.get("oneriler") or []:
        if not isinstance(o, dict):
            continue
        et, ad = str(o.get("etiket") or "").strip(), str(o.get("ad") or "").strip()
        try:
            guven = float(o.get("guven") or 0)
        except (TypeError, ValueError):
            guven = 0.0
        if et not in bilinmeyen or ad not in adaylar or ad in kullanilan or ad in etiket.values() or guven < 0.6:
            continue
        kullanilan.add(ad)
        sonuc.append({"etiket": et, "ad": ad, "kanit": str(o.get("kanit") or "")[:200], "guven": round(guven, 2)})
    return sonuc


def main():
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    yol = Path(sys.argv[1])
    d = json.loads(yol.read_text(encoding="utf-8"))
    oneriler = oner(d["segmentler"], d["veri"].get("etiket", {}))
    d["veri"]["ad_onerileri"] = oneriler
    yol.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if not oneriler:
        print("Ad önerisi bulunamadı.")
    for o in oneriler:
        print(f"{o['etiket']} → {o['ad']}  (güven {o['guven']}; {o['kanit']})")


if __name__ == "__main__":
    main()

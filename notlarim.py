"""notlarim.py - Toplantı sırasında kullanıcının kendi notları ve işaretlediği anlar (2026-10-20; Granola ve Tactiq/Fathom'dan esinle).

Toplantı sürerken (Transcript sayfasındaki canlı kart ya da Chrome yan paneli) iki şey yapılabilir:
- İşaretle: "bu an önemli" (metinsiz ya da kısa etiketle).
- Not: kısa, dağınık not ("bütçe 2 hafta", "Ayşe → yeni brief").
Kayıtlar mutlak zamanla `kayitlar/canli_notlar.jsonl`'a yazılır; toplantı yazıya dökülünce kayıt aralığına düşenler göreli saniyeye
çevrilip `veri["notlarim"]`'a girer ve Claude her birini o andaki konuşmayla zenginleştirir (kısa not → bağlamı olan tam cümle).
Toplantı notları istemine "kullanıcının önemsedikleri" olarak verilir; okuma görünümünde "Sizin notlarınız" bölümü.
"""
import json
import time
import uuid
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
DOSYA = KLASOR / "kayitlar" / "canli_notlar.jsonl"


def ekle(tur, metin="", ts=None):
    DOSYA.parent.mkdir(exist_ok=True)
    k = {"id": uuid.uuid4().hex[:10], "ts": float(ts or time.time()), "tur": "isaret" if tur == "isaret" else "not", "metin": str(metin or "").strip()[:500]}
    with open(DOSYA, "a", encoding="utf-8") as f:
        f.write(json.dumps(k, ensure_ascii=False) + "\n")
    return k


def _hepsi():
    if not DOSYA.exists():
        return []
    out, silinen = [], set()
    for satir in DOSYA.read_text(encoding="utf-8").splitlines():
        try:
            k = json.loads(satir)
        except ValueError:
            continue
        if k.get("sil"):
            silinen.add(k["sil"])
        else:
            out.append(k)
    return [k for k in out if k.get("id") not in silinen]


def sil(nid):
    with open(DOSYA, "a", encoding="utf-8") as f:
        f.write(json.dumps({"sil": str(nid)}) + "\n")


def son(saat=4):
    sinir = time.time() - saat * 3600
    return [k for k in _hepsi() if k["ts"] >= sinir]


def aralik(bas, bit, pay=120):
    """Kayıt aralığına düşen notlar, göreli saniyeyle: [{t, tur, metin, id}]."""
    return [{"t": max(0.0, round(k["ts"] - bas, 1)), "tur": k["tur"], "metin": k["metin"], "id": k["id"]}
            for k in _hepsi() if bas - pay <= k["ts"] <= bit + pay]


def _pencere(segmentler, etiket, t, once=100, sonra=25):
    sat = []
    for s in segmentler:
        if s["bit"] >= t - once and s["bas"] <= t + sonra:
            ad = etiket.get(str(s.get("k")), "") if s.get("k") is not None else ""
            sat.append(f"[{int(s['bas']) // 60:02d}:{int(s['bas']) % 60:02d}] {ad + ': ' if ad else ''}{s['metin'].strip()}")
    return "\n".join(sat)[-2500:]


def zenginlestir(veri, segmentler, notlar, log=print):
    """Her not/işaret için o andaki konuşmayla bağlamı olan 1-3 cümle (Claude; toplantı izniyle). notlar yerinde güncellenir."""
    if not notlar:
        return notlar
    import ozet as ozet_modulu
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    parcalar = []
    for i, n in enumerate(notlar):
        ne = f'KULLANICININ NOTU: "{n["metin"]}"' if n["tur"] == "not" and n["metin"] else ("KULLANICI BU ANI İŞARETLEDİ" + (f' (etiket: "{n["metin"]}")' if n["metin"] else ""))
        parcalar.append(f"### {i}\nZaman: {int(n['t']) // 60:02d}:{int(n['t']) % 60:02d}\n{ne}\nO sırada konuşulanlar:\n{_pencere(segmentler, etiket, n['t'])}")
    istem = (
        f"Toplantı: {veri.get('baslik') or ''}\nKullanıcı toplantı sırasında kendi kısa notlarını aldı ve bazı anları 'önemli' diye işaretledi. "
        "Her biri için, o andaki konuşmaya dayanarak, notu bağlamıyla tamamlayan 1-3 cümle yaz (Granola gibi: kısa not → anlaşılır, eksiksiz not). "
        "Kurallar: Türkçe; kim ne dedi, hangi sayı/tarih/karar geçtiyse koru; konuşmada olmayan bilgi EKLEME; kullanıcının notundaki konu "
        "o anki konuşmada geçmiyorsa bunu tek kısa cümleyle belirt, uydurma. İşaretlenen anlarda 'O anda ...' diye "
        "başlama; doğrudan ne konuşulduğunu söyle. Kısa ve net.\n"
        'Yalnızca JSON: {"notlar": [{"i": 0, "zengin": "...", "baslik": "en çok 6 kelimelik başlık"}]}\n\n' + "\n\n".join(parcalar)
    )
    try:
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=16384, zaman_asimi=300)) or {}
        for x in c.get("notlar") or []:
            try:
                n = notlar[int(x.get("i"))]
            except (TypeError, ValueError, IndexError):
                continue
            n["zengin"] = str(x.get("zengin") or "").strip()
            n["baslik"] = str(x.get("baslik") or "").strip()[:80]
        log(f"      Notlarınız zenginleştirildi: {sum(1 for n in notlar if n.get('zengin'))}/{len(notlar)}")
    except Exception as e:  # noqa: BLE001
        log(f"      Notlarınız zenginleştirilemedi ({e})")
    return notlar


def istem_ek(veri):
    """Toplantı notları istemine eklenecek blok: kullanıcının önemsedikleri."""
    n = veri.get("notlarim") or []
    if not n:
        return ""
    satir = [f"- [{int(x['t']) // 60:02d}:{int(x['t']) % 60:02d}] " + ("İŞARETLİ AN" if x["tur"] == "isaret" else "NOT")
             + (f": {x['metin']}" if x.get("metin") else "") + (f" → {x['zengin']}" if x.get("zengin") else "") for x in n]
    return ("\nKullanıcının toplantı sırasında kendi aldığı notlar ve 'önemli' diye işaretlediği anlar (ÖNCELİKLİ: bunlar notta mutlaka "
            "yer alsın, ilgili konunun içinde öne çıkarılsın):\n" + "\n".join(satir) + "\n")

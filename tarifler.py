"""tarifler.py - Toplantıya tek tıkla uygulanan hazır bakışlar (2026-10-20; Granola "Recipes" ve Tactiq özel istemlerinden esinle).

Hazır tarifler ajans işine göre seçildi (koçluk, müşteri istekleri, itirazlar, gündem, yöneticiye özet, riskler, fikirler). Kullanıcı kendi tarifini
(ad + istem) kaydedebilir: `profil/tarifler.json`. Sonuç markdown olarak `veri["tarifler"][kod] = {ad, metin, zaman, model}`.
Toplantı içeriği: Claude yalnızca 'Toplantılarda da Claude' açıksa (claude_yaz.toplanti()); yoksa yerel model.
"""
import json
import re
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
OZEL = KLASOR / "profil" / "tarifler.json"

HAZIR = {
    "kocla": {"ad": "Beni koçla", "aciklama": "Toplantıyı nasıl yönettiniz: güçlü yanlar, geliştirilecekler, örnek anlarla",
              "istem": "Toplantıyı {ben} açısından değerlendiren dürüst bir koç gibi yaz. Bölümler: **Güçlü yanlar** (3 madde, her biri konuşmadan kısa "
                       "bir örnek ve zamanıyla), **Geliştirilecekler** (3 madde; ne oldu, bir dahaki sefere tam olarak ne söylenebilirdi), "
                       "**Konuşma dengesi** (kim ne kadar konuştu, sorular yeterli miydi), **Tek cümlelik öneri**. Övgüyü abartma; somut ol."},
    "istekler": {"ad": "Kim ne istedi", "aciklama": "Müşterinin ve ekibin talepleri, kimden, ne zamana",
                 "istem": "Toplantıda dile getirilen her isteği/talebi çıkar. Tablo: | İsteyen | İstek | Kimden bekleniyor | Ne zamana | Zaman |. "
                          "Tarih açıkça söylenmediyse 'belirtilmedi' yaz. Sonra **Belirsiz kalanlar**: netleşmesi gereken istekler, kime sorulmalı."},
    "itirazlar": {"ad": "Kaygılar ve itirazlar", "aciklama": "Karşı tarafın çekinceleri, memnuniyetsizlik sinyalleri ve nasıl karşılandığı",
                  "istem": "Karşı tarafın (müşteri ya da paydaş) dile getirdiği kaygıları, itirazları, memnuniyetsizlik ya da tereddüt sinyallerini çıkar. "
                           "Her biri için: kim, ne dedi (kısa alıntı + zaman), toplantıda nasıl karşılandı, hâlâ açık mı. Sonunda **Önerilen yanıtlar**: "
                           "açık kalanlar için 1-2 cümlelik, kullanıcının bir sonraki mesajda söyleyebileceği ifadeler."},
    "gundem": {"ad": "Sonraki toplantının gündemi", "aciklama": "Açık kalanlardan bir sonraki görüşmenin taslak gündemi",
               "istem": "Bu toplantıda açık kalan konulardan, verilen sözlerden ve bekleyen kararlardan bir sonraki toplantı için gündem taslağı yaz. "
                        "Başlık, süre önerisi, 4-7 gündem maddesi (her birinde amaç ve kimin hazırlık yapacağı), toplantıdan önce gönderilmesi gerekenler."},
    "yonetici": {"ad": "Yöneticiye üç cümle", "aciklama": "Durumu bilmeyen birine 30 saniyelik güncelleme",
                 "istem": "Toplantıya katılmamış bir yöneticiye gönderilecek en fazla üç cümlelik güncelleme yaz: ne konuşuldu, ne karar verildi, "
                          "ondan ne gerekiyor (gerekmiyorsa söyleme). Sonra ayrı satırda tek cümlelik risk notu (varsa)."},
    "riskler": {"ad": "Riskler ve belirsizlikler", "aciklama": "Takvimi, bütçeyi ya da işi tehlikeye atabilecek noktalar",
                "istem": "İşi, takvimi, bütçeyi ya da müşteri ilişkisini tehlikeye atabilecek noktaları çıkar. Her biri: **risk**, dayanağı (kısa alıntı + "
                         "zaman), olasılık (düşük/orta/yüksek), ne yapılabilir. Yalnızca konuşmada dayanağı olanlar; genel proje riskleri yazma."},
    "fikirler": {"ad": "Konuşulan fikirler", "aciklama": "Masaya gelen yaratıcı fikirler ve kimden geldikleri",
                 "istem": "Toplantıda ortaya atılan her yaratıcı ya da stratejik fikri çıkar: fikir (1-2 cümle), kimden, karşılığı (beğenildi / tartışıldı / "
                          "reddedildi), zaman. Sonra **Geliştirilebilir olanlar**: en umut verici iki fikir için bir sonraki adım önerisi."},
}


def _ozel():
    try:
        return json.loads(OZEL.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def liste():
    oz = _ozel()
    return [{"kod": k, "ad": v["ad"], "aciklama": v.get("aciklama", ""), "ozel": False} for k, v in HAZIR.items()] + \
           [{"kod": k, "ad": v["ad"], "aciklama": v.get("istem", "")[:120], "ozel": True} for k, v in oz.items()]


def ozel_kaydet(ad, istem):
    ad, istem = str(ad or "").strip()[:60], str(istem or "").strip()[:3000]
    if not ad or len(istem) < 10:
        raise ValueError("Tarifin adı ve en az bir cümlelik istemi olmalı.")
    kod = "o_" + (re.sub(r"[^a-z0-9]+", "_", ad.lower().translate(str.maketrans("çğıöşü", "cgiosu"))).strip("_")[:30] or str(int(time.time())))
    oz = _ozel(); oz[kod] = {"ad": ad, "istem": istem, "zaman": time.time()}
    OZEL.parent.mkdir(exist_ok=True); OZEL.write_text(json.dumps(oz, ensure_ascii=False, indent=1), encoding="utf-8")
    return kod


def ozel_sil(kod):
    oz = _ozel()
    if oz.pop(kod, None) is not None:
        OZEL.write_text(json.dumps(oz, ensure_ascii=False, indent=1), encoding="utf-8")


def calistir(json_yolu, kod, log=print):
    """Tarifi toplantıya uygular; sonucu JSON'a yazar ve döner."""
    import claude_yaz
    import ozet as ozet_modulu
    from transkript import paragrafla
    t = HAZIR.get(kod) or _ozel().get(kod)
    if not t:
        raise ValueError("Böyle bir tarif yok.")
    yol = Path(json_yolu); d = json.loads(yol.read_text(encoding="utf-8")); veri = d["veri"]
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(d["segmentler"], etiket)
    metin = "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in par)
    try:
        ben = (json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8")).get("benim_adim") or "kullanıcı").split()[0]
    except Exception:  # noqa: BLE001
        ben = "kullanıcı"
    ek = ""
    try:
        import notlarim
        ek = notlarim.istem_ek(veri)
    except Exception:  # noqa: BLE001
        pass
    istem = (f"Toplantı: {veri.get('baslik') or ''}\nKullanıcı (bu notu isteyen): {ben}\n{ek}\n"
             f"GÖREV: {t['istem'].replace('{ben}', ben)}\n\n"
             "Kurallar: Türkçe, doğal ve kısa; çeviri kokan kalıplar yok. Yalnızca konuşmada geçenlere dayan, uydurma. Alıntı yaparken [dk:sn] zamanını "
             "ver. Markdown kullan (kalın başlıklar, madde, gerekirse tablo). Giriş cümlesi ya da 'İşte ...' gibi açılış yazma.\n\nTRANSKRİPT:\n" + metin[:240000])
    with claude_yaz.toplanti() if veri.get("toplanti") else _bos():
        cevap = ozet_modulu._sor(istem, json_bekle=False, num_ctx=16384, zaman_asimi=600)
    cevap = str(cevap or "").strip()
    if not cevap:
        raise RuntimeError("Yanıt alınamadı.")
    sonuc = {"ad": t["ad"], "metin": cevap, "zaman": time.time(), "model": ozet_modulu.SON_MODEL}
    log(f"Tarif hazır: {t['ad']}")
    return sonuc                                               # dosyaya yazmayı çağıran yapar (site: kilit altında)


class _bos:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

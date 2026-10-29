#!/usr/bin/env python3
"""
ozet.py - Transkriptten özet, öne çıkanlar ve zaman damgalı bölümler üretir.
Bilgisayarda çalışan Ollama (http://127.0.0.1:11434) ve gemma3:4b modelini kullanır; dışarı veri gitmez.

Kullanım (tek başına): python ozet.py transkript_x.json [tr|auto]
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import os
OLLAMA = "http://127.0.0.1:11434"
MODEL = os.environ.get("OZET_MODEL", "gemma3:4b")
PARCA_KELIME = 2500          # bu kadar kelimeden uzun metinler parçalanır (küçük parça = daha dikkatli özet)

DIL_ADI = {"tr": "Türkçe", "en": "İngilizce", "de": "Almanca", "fr": "Fransızca", "es": "İspanyolca",
           "it": "İtalyanca", "pt": "Portekizce", "ru": "Rusça", "ar": "Arapça", "fa": "Farsça",
           "nl": "Felemenkçe", "ja": "Japonca", "ko": "Korece", "zh": "Çince", "az": "Azerice",
           "el": "Yunanca", "pl": "Lehçe", "uk": "Ukraynaca", "sv": "İsveççe", "hi": "Hintçe", "id": "Endonezce"}


def claude_hazir():
    try:
        import claude_yaz
        return claude_yaz.hazir()
    except Exception:  # noqa: BLE001
        return False


def hazir(model=MODEL):
    """Yazı yazacak bir model var mı? Önce Claude (giriş yapılmış ve izinliyse), sonra Ollama."""
    if model == MODEL and claude_hazir():
        return True
    return ollama_hazir(model)


def ollama_hazir(model=MODEL):
    """Ollama çalışıyor ve model inmiş mi?"""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
            adlar = [m.get("name", "") for m in json.load(r).get("models", [])]
        return any(a == model or a.split(":")[0] == model.split(":")[0] for a in adlar)
    except Exception:  # noqa: BLE001
        return False


SON_MODEL = MODEL                 # son yanıtı hangi model verdi (çıktılarda "model" alanı için)


def _sor(istem, json_bekle=True, num_ctx=16384, zaman_asimi=900):
    """Önce Claude (abonelikle), olmazsa bilgisayardaki Ollama modeli."""
    global SON_MODEL
    if claude_hazir():
        try:
            import claude_yaz
            yanit = claude_yaz.sor(istem, "Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun; öncesinde ya da sonrasında açıklama yazma."
                                   if json_bekle else "", zaman_asimi=max(120, min(zaman_asimi, 900)))
            SON_MODEL = claude_yaz.etiket()
            return yanit
        except Exception as e:  # noqa: BLE001
            print(f"      Claude yanıt vermedi ({str(e)[:100]}); bilgisayardaki modelle devam ediliyor", flush=True)
    if not ollama_hazir():
        raise RuntimeError("Yapay zekâ modeli hazır değil")
    SON_MODEL = MODEL
    govde = {"model": MODEL, "prompt": istem, "stream": False,
             "options": {"temperature": 0.2, "num_ctx": num_ctx, "num_predict": 2000}}
    if json_bekle:
        govde["format"] = "json"
    import time
    son_hata = None
    for deneme in range(3):                       # bellek sıkışması vb. geçici hatalarda tekrar dene
        req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(govde).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=zaman_asimi) as r:
                return json.load(r).get("response", "")
        except urllib.error.HTTPError as e:
            son_hata = e
            if e.code not in (500, 502, 503):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            son_hata = e
        time.sleep(15 * (deneme + 1))
    raise son_hata


def _zaman(sn):
    import ortak                                           # tek sürüm: bir saatin üstünde h:mm:ss (2026-10-25)
    return ortak.zaman(sn)


def _json_coz(metin):
    try:
        return json.loads(metin)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", metin, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                pass
    return {}


def _parcala(satirlar):
    parcalar, simdiki, kelime = [], [], 0
    for s in satirlar:
        n = len(s.split())
        if kelime + n > PARCA_KELIME and simdiki:
            parcalar.append(simdiki); simdiki, kelime = [], 0
        simdiki.append(s); kelime += n
    if simdiki:
        parcalar.append(simdiki)
    return parcalar


BICIMLER = {   # 2026-10-27: özeti yenilerken seçilen biçim (Studio gelişim önerisi "Özeti ilk seferde doğru yap")
    "kisa": "BİÇİM: kısa. Özet en çok 2 cümle, en çok 4 madde; yalnız en önemli bilgi.",
    "ayrintili": "BİÇİM: ayrıntılı. Özet 6-8 cümle, 8-12 madde; adları, rakamları, örnekleri ve gerekçeleri koru.",
    "madde": "BİÇİM: madde madde. Özet tek cümle; asıl yük maddelerde (6-10 madde), her madde kendi başına anlaşılır.",
}


def ozet_uret(paragraflar, kaynak_dil="tr", hedef_dil="tr", log=print, goruntu=None, bicim=None, istek=""):
    """paragraflar: [{"bas","ad","metin"}] -> {"ozet","maddeler","bolumler","dil","model"} | None
    goruntu: isteğe bağlı görüntü notları [{"sn","aciklama","yazi"}]; transkripte (GÖRÜNTÜ) satırları olarak eklenir.
    bicim: kisa | ayrintili | madde | "" (verilmezse Ayarlar'daki `ozet_bicim`); istek: kullanıcının serbest notu ("rakamları da yaz")."""
    if bicim is None:
        try:
            import ortak
            bicim = str(ortak.ayar().get("ozet_bicim") or "")
        except Exception:  # noqa: BLE001
            bicim = ""
    if not paragraflar and not goruntu:
        return None
    dil = kaynak_dil if hedef_dil == "auto" else hedef_dil
    dil_adi = DIL_ADI.get(dil, dil)
    satirlar = [(p["bas"], f"[{_zaman(p['bas'])}] {p['ad']}: {p['metin']}") for p in paragraflar]
    for g in (goruntu or []):
        metin = (g.get("aciklama") or "").strip()
        if g.get("yazi"):
            metin += (" " if metin else "") + "Ekranda yazı: " + " / ".join(g["yazi"])
        if metin:
            satirlar.append((g["sn"], f"[{_zaman(g['sn'])}] (GÖRÜNTÜ) {metin}"))
    satirlar = [m for _, m in sorted(satirlar, key=lambda x: x[0])]
    # Claude uzun metni tek seferde okuyabilir (≈60 bin kelimeye kadar); parçalamak bağlamı koparır
    parcalar = [satirlar] if claude_hazir() and sum(len(s.split()) for s in satirlar) < 60000 else _parcala(satirlar)

    kurallar = (("(GÖRÜNTÜ) satırları videoda görünenleri anlatır; özet ve maddelerde bunları da kullan. " if goruntu else "") +
                f"Yanıtı yalnızca {dil_adi} dilinde yaz. Sade, nesnel ve bilgi yoğun ol; abartma, süsleme ve "
                f"övgü kullanma. Metinde olmayan bilgi ekleme, isim uydurma. Konuşmacılardan transkriptteki adlarıyla söz et; "
                "'Konuşmacı 1' gibi genel etiketleri özete ve maddelere YAZMA (okur için anlamsız): tek kişi konuşuyorsa 'video', "
                "'anlatıcı' ya da kanal adıyla, birden çok adsız kişi varsa rollerinden ('sunucu', 'konuk') söz et. "
                "Özet ve maddeler videoda SÖYLENEN SOMUT BİLGİYİ aktarsın: hangi haber, kim neyi iddia etti, hangi rakam, "
                "hangi sonuç. 'tartışılıyor', 'ele alınıyor', 'değiniliyor', 'konuşuluyor' gibi genel ifadeler KULLANMA; "
                "doğrudan bilgiyi yaz (örnek: 'OpenAI'nin ajanları engelli sitelere sızdığı için yeni modelin çıkışı iptal edildi'). "
                "'kararlar' ve 'yapilacaklar' YALNIZCA konuşmacıların kendi aralarında aldığı kararlar ve kendilerinin üstlendiği "
                "somut işler içindir (toplantı, planlama, sesli not gibi); haber, yorum, anlatım ya da eğitim videolarında bu listeler "
                "BOŞ kalır. Konuşulan şirketler/üçüncü kişiler için iş uydurma." +
                (" " + BICIMLER[bicim] + " Bu biçim aşağıdaki cümle ve madde sayılarının önüne geçer." if bicim in BICIMLER else "") +
                (f" KULLANICININ İSTEĞİ (uy, ama metinde olmayanı ekleme): {str(istek)[:400]}" if str(istek or "").strip() else ""))

    bolum_sema = ('"bolumler": [{"zaman": "mm:ss", "baslik": "kısa bölüm başlığı"}]')
    bolum_kural = ("Bölümler konunun değiştiği anları göstersin; 'zaman' alanı bölümün BAŞLADIĞI satırın köşeli parantez "
                   "içindeki damgası olsun (tek damga, aralık yazma, örn. \"15:11\"); başlık 3-7 kelime, somut konu adı.")
    if len(parcalar) == 1:
        istem = (f"Aşağıda bir videonun zaman damgalı transkripti var.\n{kurallar}\n"
                 "Şu JSON yapısında yanıt ver:\n"
                 '{"ozet": "3-5 cümlelik özet", "maddeler": ["öne çıkan 4-8 nokta, her biri tek cümle"], '
                 '"kararlar": ["videoda alınan kararlar; yoksa boş liste"], "yapilacaklar": ["üstlenilen işler, varsa kimin yapacağıyla; yoksa boş liste"], '
                 + bolum_sema + "}\n"
                 + bolum_kural + (" 6-14 bölüm olsun (uzun videoda daha çok)." if len(satirlar) > 400 else " 4-8 bölüm olsun.") + "\n\n"
                 "TRANSKRİPT:\n" + "\n".join(satirlar))
        log(f"      Özet {'Claude' if claude_hazir() else 'modele'} gönderiliyor ({sum(len(s.split()) for s in satirlar)} kelime)...")
        veri = _json_coz(_sor(istem))
    else:
        ara = []
        for i, parca in enumerate(parcalar, 1):
            log(f"      Özet: parça {i}/{len(parcalar)} işleniyor...")
            istem = (f"Aşağıda uzun bir videonun transkriptinin {i}. parçası var ({len(parcalar)} parça).\n{kurallar}\n"
                     "Şu JSON yapısında yanıt ver:\n"
                     '{"ozet": "bu parçanın 3-4 cümlelik özeti", "maddeler": ["bu parçadaki önemli 3-5 nokta; her biri somut, tek cümle"], '
                     '"kararlar": ["bu parçada alınan kararlar; yoksa boş liste"], "yapilacaklar": ["üstlenilen işler; yoksa boş liste"], '
                     + bolum_sema + "}\n"
                     + bolum_kural + " Bu parça için 2-4 bölüm olsun.\n\n"
                     "TRANSKRİPT PARÇASI:\n" + "\n".join(parca))
            ara.append(_json_coz(_sor(istem)))
        log("      Özet: parçalar birleştiriliyor...")
        tum_maddeler = []
        for a in ara:
            tum_maddeler += [str(m).strip() for m in (a.get("maddeler") or []) if str(m).strip()]
        birlesik = "\n\n".join(f"Parça {i + 1} ({len(ara)} parçadan) özeti: {a.get('ozet', '')}" for i, a in enumerate(ara))
        istem = (f"Aşağıda uzun bir videonun parça parça çıkarılmış özetleri ve öne çıkan noktaları var.\n{kurallar}\n"
                 "Görev: (1) Videonun tamamı için 4-6 cümlelik bütünlüklü bir özet yaz; parçaları sırayla kapsa. "
                 "(2) Aşağıdaki nokta listesinden en önemli 6-10 tanesini SEÇ; yakın olanları tek maddede birleştir; "
                 "listede olmayan bir şey ekleme; ifadeleri somut tut.\n"
                 'Şu JSON yapısında yanıt ver: {"ozet": "...", "maddeler": ["..."]}\n\n'
                 + birlesik + "\n\nNOKTA LİSTESİ:\n" + "\n".join(f"- {m}" for m in tum_maddeler))
        son = _json_coz(_sor(istem, num_ctx=8192))
        maddeler = [str(m).strip() for m in (son.get("maddeler") or []) if str(m).strip()] or tum_maddeler[:10]
        bolumler, kararlar, yapilacaklar = [], [], []
        for a in ara:
            bolumler += a.get("bolumler", []) or []
            kararlar += [str(m).strip() for m in (a.get("kararlar") or []) if str(m).strip()]
            yapilacaklar += [str(m).strip() for m in (a.get("yapilacaklar") or []) if str(m).strip()]
        veri = {"ozet": son.get("ozet", "") or " ".join(a.get("ozet", "") for a in ara), "maddeler": maddeler, "bolumler": bolumler,
                "kararlar": kararlar[:10], "yapilacaklar": yapilacaklar[:12]}

    if not veri.get("ozet"):
        return None
    # Bölüm zamanlarını saniyeye çevir, geçersizleri at, sırala
    bolumler = []
    for b in veri.get("bolumler", []) or []:
        if not isinstance(b, dict) or not b.get("baslik"):
            continue
        z = str(b.get("zaman", "")).strip()
        m = re.search(r"(?:(\d+):)?(\d{1,2}):(\d{2})", z)        # "15:11", "1:05:30", "00:00-01:06" (ilk damga)
        if not m:
            continue
        sn = (int(m.group(1) or 0) * 3600) + int(m.group(2)) * 60 + int(m.group(3))
        bolumler.append({"sn": sn, "baslik": str(b["baslik"]).strip().rstrip(".")[:80]})
    bolumler.sort(key=lambda b: b["sn"])
    toplam = paragraflar[-1]["bas"] if paragraflar else 0
    en_az_aralik = max(45.0, toplam / 14.0)                      # 69 dk video -> ~5 dk'dan sık bölüm olmasın
    tekil, son_sn = [], -1e9
    for b in bolumler:
        if b["sn"] - son_sn >= en_az_aralik:
            tekil.append(b); son_sn = b["sn"]
    temiz = lambda a: [str(m).strip() for m in (veri.get(a) or []) if isinstance(m, (str, int, float)) and str(m).strip()]  # noqa: E731
    return {"ozet": str(veri["ozet"]).strip(),
            "maddeler": temiz("maddeler")[:12], "kararlar": temiz("kararlar")[:10], "yapilacaklar": temiz("yapilacaklar")[:12],
            "bolumler": tekil[:20], "dil": dil, "model": SON_MODEL,
            **({"bicim": bicim} if bicim in BICIMLER else {}), **({"istek": str(istek)[:400]} if str(istek or "").strip() else {})}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    yol = Path(sys.argv[1])
    hedef = sys.argv[2] if len(sys.argv) > 2 else "tr"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from transkript import ciktilari_yaz, paragrafla
    d = json.loads(yol.read_text(encoding="utf-8"))
    if not hazir():
        raise SystemExit("HATA: Özet modeli hazır değil (Ollama çalışmıyor ya da model inmemiş).")
    paragraflar = paragrafla(d["segmentler"], d["veri"]["etiket"])
    o = ozet_uret(paragraflar, d["veri"].get("dil", "tr"), hedef)
    if not o:
        raise SystemExit("HATA: Özet üretilemedi.")
    d["veri"]["ozet"] = o
    ciktilari_yaz(yol.with_suffix(""), d["veri"], d["segmentler"])
    print("Özet hazır:", yol.with_suffix(".txt"))

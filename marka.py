"""marka.py - Marka/seri özelinde içerik paketi: kapak (thumbnail) başlığı, YouTube başlık + açıklama, blog yazısı,
Shorts kesiti. Stil, markalar/<marka>/stil.json'dan (kanaldaki son videolar + blog yazılarından çıkarılmış) öğrenilir.

Kullanım: .venv/bin/python marka.py transkript_x.json finansal_terapi kapak,youtube,blog,shorts
Çıktı: veri["marka_paket"][marka] = {...}; <temel>.<marka>.docx ve .txt (seçilen bölümler).
Model: Ollama gemma3:4b (her bölüm ayrı sorgu; blog iki aşamalı: iskelet → bölümler).
"""
import json

import harfler
import re
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))

PARCALAR = {"kapak": "Kapak (thumbnail) başlığı", "youtube": "YouTube başlığı ve açıklaması", "blog": "Blog yazısı", "shorts": "Shorts kesiti",
            "kurgu": "Kurgucuya notlar", "linkedin": "LinkedIn gönderisi", "instagram": "Instagram kaydırmalı gönderi"}
YALNIZ_CLAUDE = {"kurgu", "linkedin", "instagram"}        # bilgisayardaki model bunları iyi yazamıyor; yalnızca Claude


def stil_yukle(marka):
    yol = KLASOR / "markalar" / marka / "stil.json"
    if not yol.exists():
        raise SystemExit(f"HATA: {marka} için stil dosyası yok ({yol}).")
    return json.loads(yol.read_text(encoding="utf-8"))


def markalar():
    """Kurulu markalar: [{"kod", "ad"}]"""
    out = []
    for d in sorted((KLASOR / "markalar").glob("*/stil.json")):
        try:
            out.append({"kod": d.parent.name, "ad": json.loads(d.read_text(encoding="utf-8")).get("ad") or d.parent.name})
        except Exception:  # noqa: BLE001
            pass
    return out


import os

def model_sec():
    """İçerik yazımı için en iyi kurulu model: MARKA_MODEL > gemma3:12b > özet modeli."""
    import ozet as ozet_modulu
    import urllib.request
    tercih = os.environ.get("MARKA_MODEL") or "gemma3:12b"
    try:                                                   # tam etiket eşleşmesi (ozet.hazir gevşek eşleşir: gemma3:4b ≠ gemma3:12b)
        with urllib.request.urlopen(ozet_modulu.OLLAMA + "/api/tags", timeout=3) as r:
            adlar = {m.get("name", "") for m in json.load(r).get("models", [])}
        return tercih if tercih in adlar else ozet_modulu.MODEL
    except Exception:  # noqa: BLE001
        return ozet_modulu.MODEL


def _sor(istem, num_ctx=16384, num_predict=2500, json_bekle=True):
    return _sor_ham(istem, num_ctx, num_predict, json_bekle)


def _sor_metin(istem, num_ctx, num_predict):
    return _sor_ham(istem, num_ctx, num_predict, False)


def _sor_ham(istem, num_ctx, num_predict, json_bekle, model=None):
    import urllib.request
    import ozet as ozet_modulu
    model = model or model_sec()
    if "12b" in model or "27b" in model:
        num_ctx = min(num_ctx, 8192)                       # 16 GB Mac: büyük modelde geniş bağlam bellek hatası (HTTP 500) veriyor
    govde = {"model": model, "prompt": istem, "stream": False, "options": {"temperature": 0.35 if json_bekle else 0.5, "num_ctx": num_ctx, "num_predict": num_predict}}
    if json_bekle:
        govde["format"] = "json"
    req = urllib.request.Request(ozet_modulu.OLLAMA + "/api/generate", data=json.dumps(govde).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r).get("response", "")
    except urllib.error.HTTPError as e:
        if e.code >= 500 and model != ozet_modulu.MODEL:
            return _sor_ham(istem, num_ctx, num_predict, json_bekle, model=ozet_modulu.MODEL)
        raise


def _json(istem, **kw):
    import ozet as ozet_modulu
    return ozet_modulu._json_coz(_sor(istem, **kw)) or {}


def _zaman(sn):
    import ortak                                           # tek sürüm: bir saatin üstünde h:mm:ss (2026-10-25)
    return ortak.zaman(sn)


def _baglam(veri, segmentler, en_cok_kelime=6000):
    """Modele verilecek içerik: özet + maddeler + bölümler + (kısaltılmış) transkript."""
    from transkript import paragrafla
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(segmentler, etiket)
    metin = "\n".join(f"[{_zaman(p['bas'])}] {p['ad']}: {p['metin']}" for p in par)
    kel = metin.split()
    if len(kel) > en_cok_kelime:
        bas = " ".join(kel[:en_cok_kelime * 2 // 3]); son = " ".join(kel[-en_cok_kelime // 3:])
        metin = bas + "\n[... orta kısım kısaltıldı ...]\n" + son
    o = veri.get("ozet") or {}
    ozet = ""
    if o:
        ozet = "ÖZET: " + (o.get("ozet") or "") + "\nÖNE ÇIKANLAR: " + "; ".join(o.get("maddeler") or []) + "\n"
        if o.get("bolumler"):
            ozet += "BÖLÜMLER: " + "; ".join(f"{_zaman(b.get('sn', 0))} {b.get('baslik', '')}" for b in o["bolumler"]) + "\n"
    return ozet, metin


def klipler_sn(z):
    import klipler
    try:
        return klipler._sn(str(z).strip())
    except Exception:  # noqa: BLE001
        return None


def _konu(ozet, metin):
    """Bölümün konusunu tek paragrafta sabitler; tüm parçalar bu konuya bağlı kalır (model örnek konulara kaymasın)."""
    c = _json("Aşağıdaki özet ve transkript hangi konuyu anlatıyor? 2-3 cümleyle, somut: kim(ler) neyi tartışıyor, ana iddialar ne. "
              "Örnek ya da genel bilgi ekleme; yalnızca bu içerik. Yalnızca JSON: {\"konu\": \"...\", \"anahtar_kelimeler\": [\"...\"]}\n\n" + ozet + "\nTRANSKRİPT:\n" + metin[:8000], num_predict=400)
    return str(c.get("konu") or "").strip(), [str(k) for k in (c.get("anahtar_kelimeler") or [])][:10]


def _ilgili_parca(metin, sorgu, en_cok=6000, kullanilan=None):
    """Transkriptten, sorguyla (H2 + noktalar) en çok kelime paylaşan paragrafları seçer. `kullanilan` (küme) önceki
    bölümlere giden paragrafları tutar; onlar ve videonun açılış paragrafları (genel giriş) yeniden verilmez ki her
    bölüm aynı alıntıyla başlamasın."""
    paragraflar = [p for p in re.split(r"\n(?=\[\d)", metin) if p.strip()]
    if len(paragraflar) < 4:
        return metin[:en_cok]
    kullanilan = kullanilan if kullanilan is not None else set()
    sk = {w for w in re.findall(r"[a-zçğıöşü]{4,}", sorgu.lower())}
    puanli = []
    for i, p in enumerate(paragraflar):
        if i in kullanilan or i < 2:
            continue
        pk = set(re.findall(r"[a-zçğıöşü]{4,}", p.lower()))
        puanli.append((len(sk & pk), -i, i))
    if not puanli:
        kullanilan.clear()
        puanli = [(len(sk & set(re.findall(r"[a-zçğıöşü]{4,}", p.lower()))), -i, i) for i, p in enumerate(paragraflar) if i >= 2]
    secili = sorted(i for _s, _n, i in sorted(puanli, reverse=True)[:12])
    out, top = [], 0
    for i in secili:
        if top + len(paragraflar[i]) > en_cok:
            break
        out.append(paragraflar[i]); top += len(paragraflar[i]); kullanilan.add(i)
    return "\n".join(out) if out else metin[:en_cok]


def _alintisiz(govde, h2, stil_ses):
    """Bölüm açılışında transkript alıntısı (tırnak) kaldıysa yalnızca ilk paragrafı alıntısız yeniden yazdırır."""
    paragraflar = govde.split("\n\n")
    ilk = paragraflar[0].strip()
    if not re.match(r'^[“"«]', ilk) and not re.search(r'[”"»]\s+(sorusu|diye|dedi|ifadesi)', ilk):
        return govde
    yeni = _sor_metin(f"Ses tonu: {stil_ses}\nBölüm başlığı: {h2}\nAşağıdaki paragrafı tırnak içindeki alıntıyı tamamen kaldırarak, "
                      "ilk cümle bölümün sorusunu doğrudan yanıtlayacak şekilde, aynı uzunlukta ve aynı bilgiyle yeniden yaz. Tırnak kullanma. "
                      "Yalnızca paragraf:\n\n" + ilk, 4096, 320).strip()
    if yeni and not re.match(r'^[“"«]', yeni):
        paragraflar[0] = yeni
    return "\n\n".join(paragraflar)


def _basliksiz(metin):
    """Model 'başlık yazma' dense de '# ...' satırı ekliyordu (kapanışta H1'i yineledi); markdown başlık satırları atılır."""
    return "\n".join(l for l in metin.split("\n") if not re.match(r"^\s*#{1,6}\s", l)).strip()


def _adlari_dogrula(parca, kaynak):
    """Kişi gibi anılan 'Ad Soyad' (ör. 'finans uzmanımız Ayşe Demir ile') kaynakta (özet+transkript) geçmiyorsa
    'konuğumuz' yapılır; model gerçek konuğun yerine ad uyduruyordu. 'Yönetim Kurulu' gibi kurum adları dokunulmaz."""
    AD = r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}(?: [A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}){1,2}"
    def degis(m):
        ad = m.group("ad")
        return m.group(0) if ad in kaynak else m.group(0).replace(ad, "konuğumuz")
    parca = re.sub(r"(?:uzman[ıi](?:m[ıi]z)?|konu[kğ](?:umuz)?|sunucu(?:muz)?|ekonomist|yazar|dan[ıi]şman[ıi]?|profesör|doktor)\s+(?P<ad>" + AD + ")", degis, parca)
    parca = re.sub(r"(?P<ad>" + AD + r")(?=\s+(?:ile|anlat[ıi]yor|ele al[ıi]yor|konuşuyor|aç[ıi]kl[ıi]yor|değerlendiriyor))", degis, parca)
    return parca


def _bugun():
    return time.strftime("%d.%m.%Y")


def _ornekler(stil, n=6):
    s = "(Bunlar yalnızca STİL referansıdır; konuları ve cümleleri KOPYALAMA, yeni bölüm bambaşka bir konu olabilir.)\n"
    for v in stil.get("ornek_videolar", [])[:n]:
        s += f"- Başlık: {v['baslik']}\n  Açıklama: {v['aciklama_govde'][:600]}\n"
    return s


def _kapak_ornekleri(stil):
    return [" / ".join(v.get("kapak_yazisi") or []) for v in stil.get("ornek_videolar", []) if v.get("kapak_yazisi")][:6]


def _ornege_benziyor(metin, ornekler, esik=0.6):
    import difflib
    m = re.sub(r"\W+", " ", metin.lower()).strip()
    for o in ornekler:
        oo = re.sub(r"\W+", " ", o.lower()).strip()
        if m and oo and (m in oo or oo in m or difflib.SequenceMatcher(None, m, oo).ratio() >= esik):
            return True
    return False


def kapak(stil, ozet, metin, log):
    istem = (f"Sen '{stil['ad']}' YouTube serisinin editörüsün. Kapak (thumbnail) yazısı kalıbı: {stil['kapak_kalibi']}\n"
             f"Serinin önceki kapak yazıları (yalnızca biçim referansı; bunları ya da konularını KOPYALAMA): {' | '.join(_kapak_ornekleri(stil))}\n"
             "Yeni bölümün konusu yalnızca aşağıdaki transkripttir; kapak yazısı bu bölümde gerçekten konuşulan bir şeyi vaat etmeli.\n"
             "Aşağıdaki yeni bölüm için 6 kapak yazısı öner: 2'si merak sorusu, 2'si karşıtlık/uyarı, 2'si sayı/kazanç kancası. Her biri 2 satır, BÜYÜK HARF, "
             "satır başına en çok 4 kelime; bölümde gerçekten söylenen bir şeye dayansın, klişe (ŞOK, İNANILMAZ) kullanma. 'tur' alanına soru|karsitlik|sayi yaz; "
             "seriye uygunsa 'rozet' alanına kısa seri adı, yoksa boş.\n"
             "Yalnızca JSON: {\"kapaklar\": [{\"satir1\": \"...\", \"satir2\": \"...\", \"tur\": \"soru\", \"rozet\": \"\", \"neden\": \"tek cümle\"}]}\n\n" + ozet + "\nTRANSKRİPT (kısaltılmış):\n" + metin[:9000])
    return _kapak_temizle(_json(istem).get("kapaklar"), stil)


def _kapak_temizle(liste, stil):
    """Kapak önerilerini kalıba göre süzer: 2 satır, satır ≤4 kelime, BÜYÜK HARF, ünlem/klişe yok, örneklerin kopyası yok."""
    out = []
    orn = _kapak_ornekleri(stil) + [v["baslik"] for v in stil.get("ornek_videolar", [])]
    for k in liste or []:
        if not (isinstance(k, dict) and k.get("satir1")):
            continue
        parcalar = [x.strip(" -–") for x in re.split(r"\s*[|/]\s*", f"{k['satir1']} / {k.get('satir2') or ''}") if x.strip(" -–")]
        if len(parcalar) < 2:
            continue
        s1, s2 = harfler.ust(parcalar[0]), harfler.ust(parcalar[1])
        if len(s1.split()) > 4 or len(s2.split()) > 4 or "!" in s1 + s2 or re.search(r"ŞOK|İNANILMAZ|MUTLAKA", s1 + s2):
            continue
        if _ornege_benziyor(f"{s1} {s2}", orn):
            continue
        rozet = str(k.get("rozet") or "").strip()[:40]
        if not re.search(r"film kulübü|kitap kulübü|ekonomiyi değiştiren fikirler", rozet, re.I):
            rozet = ""                                                     # uydurma seri adı yok
        out.append({"satir1": s1[:40], "satir2": s2[:40], "tur": str(k.get("tur") or "").strip()[:12], "rozet": rozet, "neden": str(k.get("neden") or "").strip()[:200]})
    return out[:6]


def youtube(stil, ozet, metin, veri, log):
    istem = (f"Sen '{stil['ad']}' YouTube serisinin editörüsün. Ses tonu: {stil['ses']}\n"
             f"Başlık kalıbı: {stil['youtube_baslik_kalibi']}\nAçıklama kalıbı: {stil['youtube_aciklama_kalibi']}\n"
             f"Serinin önceki başlık ve açıklamaları:\n{_ornekler(stil, 6)}\n"
             "Aşağıdaki yeni bölüm için: 3 başlık alternatifi (kalıba birebir uygun, bu bölümün konusundan) ve 1 açıklama metni (120-200 kelime, düz paragraflar; "
             "hashtag, madde, başlık, 'alt blok' ya da bağlantı YAZMA, onlar sonradan eklenir). Konuşmacı adlarını transkriptte geçtiği gibi kullan; "
             "kurum ya da unvanını transkriptte açıkça söylenmiyorsa YAZMA (uydurma). "
             "8 etiket (tag) öner. Yalnızca JSON: {\"basliklar\": [\"...\"], \"aciklama\": \"...\", \"etiketler\": [\"...\"]}\n\n"
             + ozet + "\nTRANSKRİPT (kısaltılmış):\n" + metin[:10000])
    c = _json(istem)
    bolumler = []
    for b in ((veri.get("ozet") or {}).get("bolumler") or []):
        bolumler.append(f"{_zaman(b.get('sn', 0))} {b.get('baslik', '')}")
    aciklama = str(c.get("aciklama") or "").strip()
    aciklama = re.split(r"\n\s*(?:\*\*|#|Sabit|Bölümler:)", aciklama)[0].strip()         # modelin eklediği fazlalıkları at
    aciklama = re.sub(r"\*\*", "", aciklama)
    basliklar = [str(b).strip()[:120] for b in (c.get("basliklar") or []) if not _ornege_benziyor(str(b), [v["baslik"] for v in stil.get("ornek_videolar", [])], 0.75)][:3]
    # Konu tutarlılığı: başlık/açıklama bölümün konusuyla kelime paylaşmalı; paylaşmıyorsa örnek konulara kaymıştır → örneksiz yeniden dene
    def _kelimeler(t):
        return {w for w in re.findall(r"[a-zçğıöşü]{5,}", t.lower())}
    konu_k = _kelimeler(ozet[:1500])
    if konu_k:
        basliklar = [b for b in basliklar if len(_kelimeler(b) & konu_k) > 0]            # konuyla kelime paylaşmayan başlık atılır
    if konu_k and not basliklar:
        log("      Başlıklar konudan sapmış; örneksiz yeniden deneniyor")
        c2 = _json(f"Sen '{stil['ad']}' YouTube serisinin editörüsün. Başlık kalıbı: {stil['youtube_baslik_kalibi']}\nAçıklama kalıbı: {stil['youtube_aciklama_kalibi']}\n"
                   "Aşağıdaki bölüm için 3 başlık ve 1 açıklama (120-200 kelime, düz paragraf, hashtag/bağlantı yok) yaz; YALNIZCA bu bölümün konusu. "
                   "Yalnızca JSON: {\"basliklar\": [\"...\"], \"aciklama\": \"...\", \"etiketler\": [\"...\"]}\n\n" + ozet + "\nTRANSKRİPT:\n" + metin[:10000])
        basliklar = [str(b).strip()[:120] for b in (c2.get("basliklar") or [])][:3]
        aciklama = re.sub(r"\*\*", "", re.split(r"\n\s*(?:\*\*|#|Sabit|Bölümler:)", str(c2.get("aciklama") or "").strip())[0]).strip()
        c = {**c, "etiketler": c2.get("etiketler") or c.get("etiketler")}
    return _youtube_tamamla(basliklar, aciklama, c.get("etiketler"), veri, stil)


def _youtube_tamamla(basliklar, aciklama, etiketler, veri, stil):
    """Açıklamaya bölüm zamanlarını ve serinin sabit alt bloğunu ekler."""
    bolumler = [f"{_zaman(b.get('sn', 0))} {b.get('baslik', '')}" for b in ((veri.get("ozet") or {}).get("bolumler") or [])]
    if bolumler:
        aciklama += "\n\nBölümler:\n" + "\n".join(bolumler)
    if stil.get("aciklama_alt_blok"):
        aciklama += "\n\n" + stil["aciklama_alt_blok"]
    return {"basliklar": basliklar, "aciklama": aciklama,
            "etiketler": [str(e).strip() for e in (etiketler or [])][:10]}


def blog(stil, ozet, metin, log):
    orn = "\n\n".join(f"ÖRNEK YAZI: {y['baslik']}\n{y['metin'][:2500]}" for y in stil.get("ornek_bloglar", [])[:2])
    log("      Blog: SEO iskeleti")
    iskelet = _json(f"Sen '{stil['ad']}' blogunun SEO ve GEO odaklı yazarısın. Blog kalıbı: {stil['blog_kalibi']}\nSes tonu: {stil['ses']}\n"
                    f"Önceki yazı başlıkları: {'; '.join(stil.get('blog_basliklari', [])[:10])}\n"
                    "Aşağıdaki bölüm için yazı iskeleti çıkar: ana anahtar kelime, 8-12 anahtar kelime, H1 (50-65 karakter, anahtar kelime içeren), meta_baslik (≤60 karakter), "
                    "meta_aciklama (≤155 karakter; okuyucuya faydayı söyler; 'yapay zeka', 'arama motoru', 'SEO' gibi teknik/talimat sözleri İÇERMEZ), slug (küçük harf, tire), "
                    "kisa_yanit (40-60 kelime; sorunun doğrudan kesin yanıtı), 6 H2 (arama sorusu biçiminde; her biri için 2-3 madde somut nokta, transkriptten), "
                    "sss (4-6 soru), oneriler (kapanış için 3 uygulanabilir öneri). "
                    "Yalnızca JSON: {\"anahtar\": \"...\", \"anahtar_kelimeler\": [\"...\"], \"h1\": \"...\", \"meta_baslik\": \"...\", \"meta_aciklama\": \"...\", \"slug\": \"...\", "
                    "\"kisa_yanit\": \"...\", \"bolumler\": [{\"h2\": \"...\", \"noktalar\": [\"...\"]}], \"sss\": [\"...\"], \"oneriler\": [\"...\"]}\n\n" + ozet + "\nTRANSKRİPT (kısaltılmış):\n" + metin[:11000])
    if not iskelet.get("h1"):
        return None
    yazi = [f"# {iskelet['h1']}", ""]
    if iskelet.get("kisa_yanit"):
        yazi += [f"**Kısa yanıt:** {str(iskelet['kisa_yanit']).strip()}", ""]
    log("      Blog: giriş")
    giris = _sor_metin(f"Sen '{stil['ad']}' blogunun yazarısın. Ses tonu: {stil['ses']}\nÖrnek yazıların giriş biçimi:\n{orn[:2200]}\n\n"
                       f"Başlık: {iskelet['h1']}\nAna anahtar kelime: {iskelet.get('anahtar', '')}\nKısa yanıt (zaten yazıldı, tekrar etme): {iskelet.get('kisa_yanit', '')}\n"
                       f"Bugünün tarihi: {_bugun()} (yıl yazacaksan bu yıl). Giriş için 2 paragraf yaz (toplam 110-160 kelime): 1) bağlam ve konu neden şimdi önemli; "
                       f"2) '{stil.get('giris_kalibi') or stil['ad'] + ' serisinin bu bölümünde ...'}' diye başlayıp bölümde kimin neyi ele aldığını (YALNIZCA aşağıdaki özet/transkriptte geçen adla; "
                       "ad geçmiyorsa 'konuğumuz' de, ad UYDURMA) ve yazının ne öğreteceğini söyle. "
                       "Kısa cümleler, her paragraf tek fikir. Başlık yazma, yalnızca iki paragraf.\n\nÖZET:\n" + ozet[:3000], 8192, 500).strip()
    giris = _adlari_dogrula(_basliksiz(giris), ozet + "\n" + metin)
    yazi += [giris, ""]
    kullanilan = set()
    for i, b in enumerate(iskelet.get("bolumler") or [], 1):
        log(f"      Blog: bölüm {i}")
        govde = _sor_metin(f"Sen '{stil['ad']}' blogunun SEO/GEO odaklı yazarısın. Ses tonu: {stil['ses']}\nYazının başlığı: {iskelet['h1']}\nAna anahtar kelime: {iskelet.get('anahtar', '')}\n"
                           f"Şimdi yazılacak bölüm (H2): {b.get('h2')}\nBu bölümde anlatılacak noktalar: {'; '.join(b.get('noktalar') or [])}\n"
                           "Transkriptten bu bölümle ilgili kısım:\n" + _ilgili_parca(metin, f"{b.get('h2')} {' '.join(b.get('noktalar') or [])}", kullanilan=kullanilan) + "\n\n"
                           f"Bugünün tarihi: {_bugun()}. Bu bölümü 2-4 paragraf (160-240 kelime) yaz. İlk cümle bölümün sorusunu doğrudan yanıtlasın (alıntılanabilir). "
                           "Transkriptten tırnak içinde alıntı YAPMA (özellikle açılış cümlelerini tekrar etme); kendi cümlelerinle anlat. Somut sayı/örnek kullan, uydurma; "
                           "adım adım anlatım gerekiyorsa numaralı liste, karşılaştırma gerekiyorsa 2-4 satırlık markdown tablo kullan. Bölüm içinde ürün çağrısı, "
                           "okuyucuya soru sorarak reklam yapma (bu yalnızca kapanışta olur). Başlık yazma, yalnızca metin.", 12288, 650).strip()
        govde = _adlari_dogrula(_alintisiz(_basliksiz(govde), b.get("h2"), stil["ses"]), ozet + "\n" + metin)
        # yalnızca reklam/çağrı paragrafı atılır (ürünü yalnızca anan paragraf kalır; stil.json `urun_kelimeleri` düzenli ifadesi)
        govde = "\n\n".join(pg for pg in govde.split("\n\n")
                            if not (stil.get("urun_kelimeleri") and re.search(stil["urun_kelimeleri"], pg, re.I) and re.search(r"musunuz|mısınız|oluştur|hemen|tıkla|başvur|ziyaret|keşfed", pg, re.I))) or govde
        yazi += [f"## {b.get('h2')}", "", govde, ""]
    noktalar = []
    for b in iskelet.get("bolumler") or []:
        noktalar += [str(n) for n in (b.get("noktalar") or [])[:1]]
    if noktalar:
        yazi += ["## Öne çıkan noktalar", ""] + [f"- {n}" for n in noktalar[:7]] + [""]
    if iskelet.get("sss"):
        log("      Blog: sık sorulan sorular")
        sss = _json(f"Sen '{stil['ad']}' blogunun yazarısın. Aşağıdaki sorulara transkripte dayanarak 2-3 cümlelik, doğrudan ve kesin yanıtlar yaz (uydurma; bilinmiyorsa 'bölümde bu ele alınmıyor' deme, soruyu atla). "
                    "Yalnızca JSON: {\"sss\": [{\"soru\": \"...\", \"yanit\": \"...\"}]}\nSorular: " + "; ".join(str(q) for q in iskelet["sss"][:6]) + "\n\nTRANSKRİPT:\n" + metin[:9000])
        cift = [(str(q.get("soru")), str(q.get("yanit"))) for q in (sss.get("sss") or []) if isinstance(q, dict) and q.get("soru") and q.get("yanit")]
        if cift:
            yazi += ["## Sık sorulan sorular", ""]
            for q, a in cift[:6]:
                yazi += [f"**{q}**", "", a, ""]
    log("      Blog: kapanış")
    kapanis = _sor_metin(f"Sen '{stil['ad']}' blogunun yazarısın. Ses tonu: {stil['ses']}\nYazının başlığı: {iskelet['h1']}\n"
                         f"Öneriler: {'; '.join(str(o) for o in (iskelet.get('oneriler') or []))}\n"
                         f"Kapanış bölümünü yaz (110-160 kelime): bu önerileri 3 maddelik uygulanabilir liste olarak ver (genel yaklaşım). {stil.get('kapanis_kurali') or 'Son paragrafta markanın ürününe doğal bir bağ kur.'} Başlık yazma.", 8192, 450).strip()
    yazi += ["## Ne yapmalı?", "", _basliksiz(kapanis)]
    metin_son = "\n".join(yazi)
    return {"h1": iskelet["h1"], "metin": metin_son, "kelime": len(metin_son.split()), "meta_baslik": str(iskelet.get("meta_baslik") or "")[:70],
            "meta_aciklama": re.sub(r"\s*(Yapay zek[âa] arama motorlar\S*|SEO|GEO)[^.]*\.?", "", str(iskelet.get("meta_aciklama") or "")).strip()[:170], "slug": re.sub(r"[^a-z0-9\-]", "", str(iskelet.get("slug") or "").lower().replace(" ", "-"))[:80],
            "anahtar_kelimeler": [str(k) for k in (iskelet.get("anahtar_kelimeler") or [])][:12]}


def shorts(stil, ozet, metin, veri, segmentler, log):
    istem = (f"Sen '{stil['ad']}' serisinin sosyal medya editörüsün. Shorts kesit kalıbı: {stil['shorts_kalibi']}\nKapak yazısı kalıbı: {stil['kapak_kalibi']}\n"
             "Aşağıdaki zaman damgalı transkriptten Shorts/Reels için en güçlü 3 kesiti seç (20-60 sn). Her kesit için: bas ve bit (mm:ss ya da h:mm:ss, cümle sınırında), "
             "neden (tek cümle: hangi kanca), shorts_baslik (2 satır BÜYÜK HARF kapak yazısı, '/' ile ayır, ≤6 kelime), aciklama (1 cümle), etiketler (3 hashtag). "
             "Yalnızca JSON: {\"kesitler\": [{\"bas\": \"mm:ss\", \"bit\": \"mm:ss\", \"neden\": \"...\", \"shorts_baslik\": \"... / ...\", \"aciklama\": \"...\", \"etiketler\": [\"#...\"]}]}\n\n"
             + ozet + "\nTRANSKRİPT:\n" + metin[:14000])
    return _shorts_temizle(_json(istem).get("kesitler"), segmentler)


def _shorts_temizle(liste, segmentler):
    """Kesit zamanlarını cümle sınırına oturtur; 12-90 sn dışındakileri atar."""
    import klipler
    out = []
    for k in liste or []:
        b, e = klipler._sn(str(k.get("bas") or "")), klipler._sn(str(k.get("bit") or ""))
        if b is None or e is None or e <= b:
            continue
        b, e = klipler._oturt(b, e, segmentler)
        if e - b < 12 or e - b > 90:
            continue
        out.append({"bas": b, "bit": e, "neden": str(k.get("neden") or "")[:200], "shorts_baslik": harfler.ust(str(k.get("shorts_baslik") or ""))[:80], "aciklama": str(k.get("aciklama") or "")[:200],
                    "etiketler": [("#" + str(t).strip().lstrip("#")) for t in (k.get("etiketler") or []) if str(t).strip()][:3]})
    return out[:3]


TURKCE_ILKELER = (
    "TÜRKÇE YAZIM İLKELERİ (en önemli kural): Ana dili Türkçe olan, iyi bir dergi editörü gibi yaz. Metin İngilizceden "
    "çevrilmiş gibi DURMAMALI. Kaçın: '... önemlidir / gerekir / söz konusudur / bulunmaktadır' ile biten kalıp cümleler; "
    "'... anlamına gelmez', '... açısından kritik', '... konusunda farkındalık', 'bu bağlamda', 'günümüzde', 'sonuç olarak' "
    "gibi çeviri ve rapor kalıpları; art arda aynı yapıda cümleler; gereksiz edilgen çatı; 'Bu yazıda ... ele alıyoruz / "
    "toparlıyoruz' gibi yazının kendisinden söz eden cümleler; tarih yazmak ('17 Ekim 2026 itibarıyla' gibi). Bunun yerine: "
    "Türkçenin doğal söz dizimi, somut fiiller, gündelik ama özenli dil, yer yer kısa ve vurucu cümleler, okura 'siz' diye "
    "sıcak bir hitap, konuşmadaki canlı örnekleri ve benzetmeleri kullanmak. Sesli okununca doğal gelmeyen cümleyi yeniden kur."
)


def _md_duz(m):
    """Markdown'ı işaretsiz düz metne çevirir (txt dosyası ve düz kopya için): '#', '**', tablo çizgileri gider."""
    out = []
    for satir in str(m or "").split("\n"):
        t = satir.rstrip()
        if re.match(r"^\s*\|?\s*:?-{3,}", t):
            continue
        h = re.match(r"^(#{1,6})\s+(.*)", t)
        if h:
            out += ["", h.group(2).strip().replace("**", ""), ""]
            continue
        if t.startswith("|"):
            t = " — ".join(c.strip() for c in t.strip("|").split("|"))
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
        t = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", t)
        t = re.sub(r"^\s*[-*]\s+", "• ", t)
        out.append(t)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _turkce_elden_gecir(paket, stil, log):
    """İkinci geçiş: blog ve YouTube açıklaması bir Türkçe editörün elinden geçer (bilgi ve yapı aynı kalır)."""
    import claude_yaz
    blog = (paket.get("blog") or {}).get("metin") or ""
    yt = paket.get("youtube") or {}
    aciklama = (yt.get("aciklama") or "").split("\n\nBölümler:")[0].split("\n\n" + (stil.get("aciklama_alt_blok") or "\0"))[0]
    if not blog and not aciklama:
        return
    log("      Türkçe editör geçişi...")
    istem = ("Aşağıdaki metinleri bir Türkçe editör gibi elden geçir. Bilgiyi, iddiaları, kişi adlarını, sayıları ve markdown yapısını "
             "('#', '##' başlıkları, '**Kısa yanıt:**', '- ' maddeler, '1.' listeler, '|' tablolar, '**Soru?**' satırları) AYNEN koru; "
             "başlık sayısını değiştirme. Yalnızca dili düzelt: çeviri kokan, robotik, kalıp cümleleri doğal Türkçeye çevir; tekrarları "
             "azalt; yazının kendisinden söz eden ve tarih içeren cümleleri çıkar. Başlıkları da doğal Türkçe soru/ifade yap.\n\n"
             f"{TURKCE_ILKELER}\n\nBiçim: {{\"blog\": \"...\", \"aciklama\": \"...\"}}\n\nBLOG:\n{blog}\n\nYOUTUBE AÇIKLAMASI:\n{aciklama}")
    try:
        c = claude_yaz.sor_json(istem, f"Sen '{stil['ad']}' için kıdemli Türkçe editörsün. Ses tonu: {stil['ses']}", zaman_asimi=900, model_adi=_yazi_modeli())
    except Exception as e:  # noqa: BLE001
        log(f"      Editör geçişi atlandı ({str(e)[:80]})"); return
    yeni_blog = str(c.get("blog") or "").strip()
    if blog and yeni_blog and abs(yeni_blog.count("\n## ") - blog.count("\n## ")) <= 1 and len(yeni_blog.split()) > len(blog.split()) * 0.75:
        paket["blog"]["metin"] = yeni_blog; paket["blog"]["kelime"] = len(yeni_blog.split())
        h1 = re.search(r"^#\s+(.+)$", yeni_blog, re.M)
        if h1:
            paket["blog"]["h1"] = h1.group(1).strip()
    yeni_ac = str(c.get("aciklama") or "").strip()
    if aciklama and yeni_ac and len(yeni_ac.split()) > len(aciklama.split()) * 0.6:
        paket["youtube"]["aciklama"] = yt["aciklama"].replace(aciklama, yeni_ac, 1)


def _yazi_modeli():
    """Marka içerikleri için Claude modeli: ayarlar 'claude_model_yazi' (varsayılan opus; en iyi Türkçe)."""
    import claude_yaz
    return os.environ.get("CLAUDE_MODEL_YAZI") or claude_yaz._ayar().get("claude_model_yazi") or "opus"


def claude_paket(stil, veri, seg, secim, log):
    """Seçilen parçaların hepsini Claude'a tek istemle yazdırır (1-3 dk). Biçim, yerel yolla aynı sözlükler."""
    import claude_yaz
    ozet, metin = _baglam(veri, seg, en_cok_kelime=40000)          # Claude'a transkriptin tamamı gider
    orn_blog = "\n\n".join(f"ÖRNEK YAZI: {y['baslik']}\n{y['metin'][:3000]}" for y in stil.get("ornek_bloglar", [])[:2])
    istenen, sema = [], {"konu": "bölümün konusu, 2-3 cümle"}
    if "kapak" in secim:
        istenen.append(f"KAPAK YAZISI: 6 öneri (2 merak sorusu, 2 karşıtlık/uyarı, 2 sayı/kazanç kancası). Kalıp: {stil['kapak_kalibi']}\n"
                       f"Önceki kapak yazıları (yalnızca biçim; KOPYALAMA): {' | '.join(_kapak_ornekleri(stil))}\n"
                       "Her biri 2 satır, BÜYÜK HARF, satır başına en çok 4 kelime, ünlem ve klişe (ŞOK, İNANILMAZ) yok. Amaç izletmek: bölümde gerçekten "
                       "söylenen en çarpıcı şeyi vaat etsin. 'rozet' yalnızca Film Kulübü / Kitap Kulübü / Ekonomiyi Değiştiren Fikirler serisindense, yoksa boş.")
        sema["kapak"] = [{"satir1": "...", "satir2": "...", "tur": "soru|karsitlik|sayi", "rozet": "", "neden": "tek cümle"}]
    if "youtube" in secim:
        istenen.append(f"YOUTUBE: 3 başlık + 1 açıklama + 8 etiket. Başlık kalıbı: {stil['youtube_baslik_kalibi']}\nAçıklama kalıbı: {stil['youtube_aciklama_kalibi']}\n"
                       f"Önceki başlık ve açıklamalar:\n{_ornekler(stil, 6)}\n"
                       "Açıklama 120-200 kelime düz paragraf; hashtag, madde, bölüm listesi ve bağlantı YAZMA (sonradan eklenir).")
        sema["youtube"] = {"basliklar": ["..."], "aciklama": "...", "etiketler": ["..."]}
    if "shorts" in secim:
        istenen.append(f"SHORTS: en güçlü 3 kesit (20-60 sn, cümle sınırında, transkriptteki zaman damgalarına göre). Kalıp: {stil['shorts_kalibi']}\n"
                       "Her kesit için bas/bit (mm:ss ya da h:mm:ss), neden (hangi kanca), shorts_baslik (2 satır BÜYÜK HARF, '/' ile, ≤6 kelime), aciklama (1 cümle), 3 hashtag.")
        sema["shorts"] = [{"bas": "mm:ss", "bit": "mm:ss", "neden": "...", "shorts_baslik": "... / ...", "aciklama": "...", "etiketler": ["#..."]}]
    if "kurgu" in secim:
        istenen.append("KURGUCUYA NOTLAR: Videonun kurgucusu için zaman damgalı, uygulanabilir notlar (8-15 not). Bak: uzayan ya da tekrar eden "
                       "kısımlar (kısaltılabilir/çıkarılabilir), konudan sapan yerler, anlaşılmayan ya da bağlamı eksik anlar (süper/ekran yazısı önerisi), "
                       "vurgulanması gereken güçlü cümleler, bölüm geçişleri. Ayrıca 'acilis': videonun ilk 10-15 saniyesi için hangi cümleyle (zamanıyla) "
                       "açılması izleyiciyi tutar. Notlar kısa ve net; kurgucuya hitap eder gibi. 'zaman' transkriptteki damgalardan, aralıksa 'mm:ss-mm:ss'.")
        sema["kurgu"] = {"acilis": "...", "notlar": [{"zaman": "mm:ss-mm:ss", "tur": "kısalt|çıkar|süper|vurgula|geçiş|ses", "not": "..."}]}
    if "linkedin" in secim:
        istenen.append(f"LINKEDIN: {stil.get('marka') or stil['ad']} kurumsal hesabı için tek gönderi, 900-1500 karakter. İlk iki satır kanca (LinkedIn 'devamını gör' öncesi); "
                       "bölümdeki en değerli 2-3 fikri somut anlat; sonda bölümü izlemeye doğal bir çağrı. Emoji en fazla 2, madde işareti olarak '→' "
                       "kullanılabilir; hashtag METNE YAZMA, 'etiketler' alanına 3 tane ver. Kurumsal ama sıcak, insan sesi.")
        sema["linkedin"] = {"metin": "...", "etiketler": ["..."]}
    if "instagram" in secim:
        istenen.append("INSTAGRAM KAYDIRMALI GÖNDERİ: 6-8 slayt. 1. slayt güçlü bir kanca (kapak gibi), son slayt bölüme çağrı. Her slaytta 'baslik' "
                       "(en çok 6 kelime) ve 'metin' (en çok 25 kelime, sade). Ayrıca 'aciklama' (80-150 kelime, doğal) ve 'etiketler' (5 hashtag).")
        sema["instagram"] = {"slaytlar": [{"baslik": "...", "metin": "..."}], "aciklama": "...", "etiketler": ["#..."]}
    if "blog" in secim:
        istenen.append(f"BLOG: SEO ve GEO (yapay zekâ aramalarında alıntılanacak biçim) odaklı, 1200-1600 kelime. Kalıp: {stil['blog_kalibi']}\n"
                       f"Önceki yazı başlıkları: {'; '.join(stil.get('blog_basliklari', [])[:10])}\nÖrnek yazılar (ses ve biçim; KOPYALAMA):\n{orn_blog}\n"
                       f"'metin' alanı markdown: '# H1', ardından '**Kısa yanıt:** ...' (40-60 kelime), 2 paragraf giriş ('{stil.get('giris_kalibi') or stil['ad'] + ' serisinin bu bölümünde ...'}'), arama sorusu biçiminde 5-6 '## H2' bölüm (her biri 2-4 paragraf, ilk cümlesi sorunun doğrudan yanıtı; gerekiyorsa '- ' liste "
                       "ya da '|' tablo), '## Öne çıkan noktalar' (5-7 '- ' madde), '## Sık sorulan sorular' (4-6 soru; soru satırı '**Soru?**', altında 2-3 cümle yanıt), "
                       f"{stil.get('kapanis_kurali') or chr(39) + '## Ne yapmalı?' + chr(39) + ' (3 maddelik uygulanabilir liste; markanın ürün çağrısı yalnızca bu kapanışta).'} Transkriptten uzun alıntı yapma; aynı alıntıyı "
                       "tekrar etme. meta_baslik ≤60, meta_aciklama ≤155 karakter (okura faydayı söyler), slug küçük harf ve tire.")
        sema["blog"] = {"h1": "...", "meta_baslik": "...", "meta_aciklama": "...", "slug": "...", "anahtar_kelimeler": ["..."], "metin": "markdown"}
    sistem = (f"Sen '{stil['ad']}' ({stil.get('marka') or 'markanın'} YouTube serisi ve blogu) için içerik editörüsün. Ses tonu: {stil['ses']}\n"
              f"Bugünün tarihi {time.strftime('%d.%m.%Y')} (yalnızca yıl hatası yapmaman için; metne tarih yazma). Yalnızca verilen transkripte dayan: "
              "kişi adlarını transkriptte geçtiği gibi kullan, unvan/kurum/sayı uydurma; örneklerdeki konuları ve cümleleri kopyalama.\n" + TURKCE_ILKELER)
    istem = ("Aşağıdaki yeni bölüm için şu parçaları hazırla:\n\n" + "\n\n".join(f"{i + 1}) {t}" for i, t in enumerate(istenen)) +
             "\n\nYanıt biçimi (JSON): " + json.dumps(sema, ensure_ascii=False) +
             f"\n\nBÖLÜMÜN ADI: {veri.get('baslik') or ''}\n{ozet}\nTRANSKRİPT (zaman damgalı):\n{metin}")
    log(f"      Claude yazıyor ({_yazi_modeli()})...")
    t0 = time.time()
    try:
        c = claude_yaz.sor_json(istem, sistem, zaman_asimi=1200, model_adi=_yazi_modeli())
    except Exception as e:  # noqa: BLE001
        log(f"      {_yazi_modeli()} yanıt vermedi ({str(e)[:80]}); {claude_yaz.model()} ile deneniyor")
        c = claude_yaz.sor_json(istem, sistem, zaman_asimi=900)
    log(f"      Claude {int(time.time() - t0)} sn'de yazdı")
    paket = {"konu": str(c.get("konu") or "").strip()}
    if "kapak" in secim:
        paket["kapak"] = _kapak_temizle(c.get("kapak"), stil)
    if "youtube" in secim and isinstance(c.get("youtube"), dict):
        y = c["youtube"]
        aciklama = re.sub(r"\*\*", "", re.split(r"\n\s*(?:#|Bölümler:)", str(y.get("aciklama") or "").strip())[0]).strip()
        paket["youtube"] = _youtube_tamamla([str(b).strip()[:120] for b in (y.get("basliklar") or [])][:3], aciklama, y.get("etiketler"), veri, stil)
    if "shorts" in secim:
        paket["shorts"] = _shorts_temizle(c.get("shorts"), seg)
    if "blog" in secim and isinstance(c.get("blog"), dict) and c["blog"].get("metin"):
        b = c["blog"]; m = str(b["metin"]).strip()
        paket["blog"] = {"h1": str(b.get("h1") or ""), "metin": m, "kelime": len(m.split()), "meta_baslik": str(b.get("meta_baslik") or "")[:70],
                         "meta_aciklama": str(b.get("meta_aciklama") or "")[:170], "slug": re.sub(r"[^a-z0-9\-]", "", str(b.get("slug") or "").lower())[:80],
                         "anahtar_kelimeler": [str(k) for k in (b.get("anahtar_kelimeler") or [])][:12]}
    if "kurgu" in secim and isinstance(c.get("kurgu"), dict):
        k = c["kurgu"]
        notlar = []
        for n in k.get("notlar") or []:
            if isinstance(n, dict) and n.get("not"):
                z = str(n.get("zaman") or "")
                bas = klipler_sn(z.split("-")[0]) if z else None
                notlar.append({"zaman": z[:20], "sn": bas or 0, "tur": str(n.get("tur") or "")[:20], "not": str(n["not"]).strip()[:500]})
        if notlar:
            paket["kurgu"] = {"acilis": str(k.get("acilis") or "").strip()[:600], "notlar": sorted(notlar, key=lambda x: x["sn"])}
    if "linkedin" in secim and isinstance(c.get("linkedin"), dict) and c["linkedin"].get("metin"):
        li = c["linkedin"]
        paket["linkedin"] = {"metin": re.sub(r"(?<!\w)#\w+", "", str(li["metin"])).strip(), "etiketler": ["#" + str(e).strip().lstrip("#") for e in (li.get("etiketler") or [])][:3]}
    if "instagram" in secim and isinstance(c.get("instagram"), dict) and c["instagram"].get("slaytlar"):
        ig = c["instagram"]
        sl = [{"baslik": str(x.get("baslik") or "").strip()[:80], "metin": str(x.get("metin") or "").strip()[:300]} for x in ig["slaytlar"] if isinstance(x, dict)][:10]
        paket["instagram"] = {"slaytlar": sl, "aciklama": str(ig.get("aciklama") or "").strip(), "etiketler": ["#" + str(e).strip().lstrip("#") for e in (ig.get("etiketler") or [])][:6]}
    _turkce_elden_gecir(paket, stil, log)
    eksik = [p for p in secim if p in PARCALAR and not paket.get(p)]
    return paket, eksik


def uret(json_yolu, marka, secim, log=print):
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8")); veri, seg = d["veri"], d["segmentler"]
    stil = stil_yukle(marka)
    secim = [p for p in secim if p in PARCALAR]
    paket = (veri.get("marka_paket") or {}).get(marka) or {}
    import claude_yaz
    if claude_yaz.hazir():
        try:
            yeni, eksik = claude_paket(stil, veri, seg, secim, log)
            paket.update({k: v for k, v in yeni.items() if v}); paket["yazan"] = "claude"
            secim_yerel = eksik
            if eksik:
                log(f"      Claude şu parçaları veremedi, bilgisayardaki modelle yazılacak: {', '.join(PARCALAR[p] for p in eksik)}")
        except Exception as e:  # noqa: BLE001
            log(f"      Claude'a ulaşılamadı ({str(e)[:120]}); bilgisayardaki modelle devam ediliyor")
            secim_yerel = list(secim)
    else:
        secim_yerel = list(secim)
    if not secim_yerel:
        return _kaydet(json_yolu, veri, seg, marka, stil, paket, secim, log)
    import ozet as ozet_modulu
    if not ozet_modulu.hazir():
        raise SystemExit("HATA: Yapay zekâ modeli hazır değil (Ollama).")
    ozet, metin = _baglam(veri, seg)
    log("      Bölümün konusu belirleniyor...")
    try:
        konu, anahtarlar = _konu(ozet, metin)
    except Exception:  # noqa: BLE001
        konu, anahtarlar = "", []
    if konu:
        ozet = f"BU BÖLÜMÜN KONUSU (her şey yalnızca bununla ilgili olmalı; başka konu yazma): {konu}\nANAHTAR KELİMELER: {', '.join(anahtarlar)}\n" + ozet
    paket["konu"] = paket.get("konu") or konu
    paket["yazan"] = "claude+yerel" if paket.get("yazan") == "claude" else "yerel"
    atlanan = [p for p in secim_yerel if p in YALNIZ_CLAUDE]
    if atlanan:
        log(f"      {', '.join(PARCALAR[p] for p in atlanan)}: yalnızca Claude bağlıyken hazırlanır")
    for p in [x for x in secim_yerel if x not in YALNIZ_CLAUDE]:
        log(f"[{PARCALAR[p]}] hazırlanıyor...")
        try:
            if p == "kapak":
                paket["kapak"] = kapak(stil, ozet, metin, log)
            elif p == "youtube":
                paket["youtube"] = youtube(stil, ozet, metin, veri, log)
            elif p == "blog":
                paket["blog"] = blog(stil, ozet, metin, log)
            elif p == "shorts":
                paket["shorts"] = shorts(stil, ozet, metin, veri, seg, log)
        except Exception as e:  # noqa: BLE001
            log(f"      {PARCALAR[p]} üretilemedi ({e})")
    return _kaydet(json_yolu, veri, seg, marka, stil, paket, secim, log)


def _kaydet(json_yolu, veri, seg, marka, stil, paket, secim, log):
    paket["zaman"] = time.time(); paket["secim"] = sorted(set((paket.get("secim") or []) + list(secim)))
    veri.setdefault("marka_paket", {})[marka] = paket
    veri["marka"] = marka
    import kayit_json                                        # 2026-10-25: yeniden oku, yalnız kendi alanlarını yaz

    def _yaz(d):
        d["veri"].setdefault("marka_paket", {})[marka] = paket
        d["veri"]["marka"] = marka
    kayit_json.guncelle(json_yolu, _yaz)
    temel = json_yolu.with_suffix("")
    belge_yaz(temel, veri, stil, paket, secim)
    log(f"Bitti. Dosya: {temel}.{marka}.docx")
    return paket


def metin_yaz(veri, stil, paket, secim):
    s = [f"{stil['ad']} · İçerik paketi", veri.get("baslik") or "", ""]
    if "kapak" in secim and paket.get("kapak"):
        s += ["KAPAK (THUMBNAIL) BAŞLIĞI"] + [f"{i + 1}. {k['satir1']} / {k['satir2']}" + (f"  [{k['rozet']}]" if k.get("rozet") else "") + (f"  ({k['tur']})" if k.get("tur") else "") + (f"  — {k['neden']}" if k.get("neden") else "") for i, k in enumerate(paket["kapak"])] + [""]
    if "youtube" in secim and paket.get("youtube"):
        y = paket["youtube"]
        s += ["YOUTUBE BAŞLIĞI"] + [f"{i + 1}. {b}" for i, b in enumerate(y.get("basliklar") or [])] + ["", "YOUTUBE AÇIKLAMASI", y.get("aciklama") or "", "", "ETİKETLER", ", ".join(y.get("etiketler") or []), ""]
    if "shorts" in secim and paket.get("shorts"):
        s += ["SHORTS KESİTLERİ (kurgucuya)"] + [f"{i + 1}. {_zaman(k['bas'])} – {_zaman(k['bit'])} ({int(k['bit'] - k['bas'])} sn)\n   Neden: {k['neden']}\n   Kapak: {k['shorts_baslik']}\n   Açıklama: {k['aciklama']}" for i, k in enumerate(paket["shorts"])] + [""]
    if "kurgu" in secim and paket.get("kurgu"):
        k = paket["kurgu"]
        s += ["KURGUCUYA NOTLAR"] + ([f"Açılış önerisi: {k['acilis']}"] if k.get("acilis") else []) + [f"{n['zaman']}  [{n['tur']}]  {n['not']}" for n in k["notlar"]] + [""]
    if "linkedin" in secim and paket.get("linkedin"):
        s += ["LINKEDIN GÖNDERİSİ", paket["linkedin"]["metin"], " ".join(paket["linkedin"].get("etiketler") or []), ""]
    if "instagram" in secim and paket.get("instagram"):
        ig = paket["instagram"]
        s += ["INSTAGRAM KAYDIRMALI GÖNDERİ"] + [f"Slayt {i + 1}: {x['baslik']}\n   {x['metin']}" for i, x in enumerate(ig["slaytlar"])] + ["Açıklama: " + ig.get("aciklama", ""), " ".join(ig.get("etiketler") or []), ""]
    if "blog" in secim and paket.get("blog"):
        bl = paket["blog"]
        s += ["BLOG YAZISI (SEO/GEO)", f"Meta başlık: {bl.get('meta_baslik', '')}", f"Meta açıklama: {bl.get('meta_aciklama', '')}", f"URL eki: {bl.get('slug', '')}",
              f"Anahtar kelimeler: {', '.join(bl.get('anahtar_kelimeler') or [])}", "", _md_duz(bl["metin"]), ""]
    return "\n".join(s)


def _satir_ici(p, metin):
    """'**kalın**' ve '*eğik*' işaretlerini Word biçimine çevirir."""
    for parca in re.split(r"(\*\*[^*]+\*\*|(?<!\w)\*[^*\s][^*]*\*(?!\w))", metin):
        if not parca:
            continue
        if parca.startswith("**") and parca.endswith("**"):
            p.add_run(parca[2:-2]).bold = True
        elif parca.startswith("*") and parca.endswith("*") and len(parca) > 2:
            p.add_run(parca[1:-1]).italic = True
        else:
            p.add_run(parca)


def _md_docx(doc, metin):
    """Blog markdown'ını Word öğelerine çevirir: başlık, paragraf, madde, numaralı liste, tablo; hiçbir işaret kalmaz."""
    satirlar = str(metin or "").split("\n")
    i = 0
    while i < len(satirlar):
        t = satirlar[i].rstrip()
        if t.startswith("|"):
            blok = []
            while i < len(satirlar) and satirlar[i].strip().startswith("|"):
                if not re.match(r"^\s*\|?\s*:?-{3,}", satirlar[i]):
                    blok.append([c.strip() for c in satirlar[i].strip().strip("|").split("|")])
                i += 1
            if blok:
                tab = doc.add_table(rows=len(blok), cols=max(len(r) for r in blok)); tab.style = "Table Grid"
                for ri, r in enumerate(blok):
                    for ci, c in enumerate(r):
                        hucre = tab.cell(ri, ci).paragraphs[0]
                        _satir_ici(hucre, c)
                        if ri == 0:
                            for run in hucre.runs:
                                run.bold = True
            continue
        h = re.match(r"^(#{1,6})\s+(.*)", t)
        if h:
            doc.add_heading(h.group(2).replace("**", "").strip(), level=min(len(h.group(1)), 3))
        elif re.match(r"^\s*[-*•]\s+", t):
            _satir_ici(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*•]\s+", "", t))
        elif re.match(r"^\s*\d+[.)]\s+", t):
            _satir_ici(doc.add_paragraph(style="List Number"), re.sub(r"^\s*\d+[.)]\s+", "", t))
        elif t.strip():
            _satir_ici(doc.add_paragraph(), t)
        i += 1


def belge_yaz(temel, veri, stil, paket, secim):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    marka = veri.get("marka") or "marka"
    Path(f"{temel}.{marka}.txt").write_text(metin_yaz(veri, stil, paket, secim), encoding="utf-8")
    doc = Document()
    for sec in doc.sections:
        sec.page_width, sec.page_height = Cm(21), Cm(29.7); sec.left_margin = sec.right_margin = Cm(2.2)
    st = doc.styles["Normal"]; st.font.name = "Helvetica Neue"; st.font.size = Pt(10.5)
    GRI = RGBColor(0x6E, 0x6E, 0x73)
    doc.add_heading(f"{stil['ad']} · İçerik paketi", level=0)
    p = doc.add_paragraph(); r = p.add_run(veri.get("baslik") or ""); r.font.color.rgb = GRI
    if "kapak" in secim and paket.get("kapak"):
        doc.add_heading("Kapak (thumbnail) başlığı", level=1)
        for ad in paket.get("kapak_gorsel") or []:
            yol = Path(temel).parent / ad
            if yol.exists():
                doc.add_picture(str(yol), width=Cm(12))
        for k in paket["kapak"]:
            p = doc.add_paragraph(style="List Number"); r = p.add_run(f"{k['satir1']} / {k['satir2']}"); r.bold = True
            if k.get("rozet"):
                p.add_run(f"  [{k['rozet']}]")
            if k.get("neden"):
                r2 = p.add_run(f"  — {k['neden']}"); r2.font.color.rgb = GRI; r2.font.size = Pt(9.5)
    if "youtube" in secim and paket.get("youtube"):
        y = paket["youtube"]
        doc.add_heading("YouTube başlığı", level=1)
        for b in y.get("basliklar") or []:
            doc.add_paragraph(b, style="List Number")
        doc.add_heading("YouTube açıklaması", level=1)
        for par in (y.get("aciklama") or "").split("\n"):
            doc.add_paragraph(par)
        if y.get("etiketler"):
            doc.add_heading("Etiketler", level=2); doc.add_paragraph(", ".join(y["etiketler"]))
    if "shorts" in secim and paket.get("shorts"):
        doc.add_heading("Shorts kesitleri (kurgucuya)", level=1)
        for k in paket["shorts"]:
            p = doc.add_paragraph(style="List Number"); r = p.add_run(f"{_zaman(k['bas'])} – {_zaman(k['bit'])}  ({int(k['bit'] - k['bas'])} sn)"); r.bold = True
            doc.add_paragraph(f"Neden: {k['neden']}"); doc.add_paragraph(f"Kapak yazısı: {k['shorts_baslik']}"); doc.add_paragraph(f"Açıklama: {k['aciklama']}")
    if "kurgu" in secim and paket.get("kurgu"):
        k = paket["kurgu"]
        doc.add_heading("Kurgucuya notlar", level=1)
        if k.get("acilis"):
            p = doc.add_paragraph(); r = p.add_run("Açılış önerisi: "); r.bold = True; p.add_run(k["acilis"])
        tab = doc.add_table(rows=1, cols=3); tab.style = "Table Grid"
        for ci, bas in enumerate(("Zaman", "Tür", "Not")):
            tab.cell(0, ci).paragraphs[0].add_run(bas).bold = True
        for n in k["notlar"]:
            r = tab.add_row().cells; r[0].text = n["zaman"]; r[1].text = n["tur"]; r[2].text = n["not"]
    if "linkedin" in secim and paket.get("linkedin"):
        doc.add_heading("LinkedIn gönderisi", level=1)
        for par in paket["linkedin"]["metin"].split("\n"):
            doc.add_paragraph(par)
        if paket["linkedin"].get("etiketler"):
            p = doc.add_paragraph(); r = p.add_run(" ".join(paket["linkedin"]["etiketler"])); r.font.color.rgb = GRI
    if "instagram" in secim and paket.get("instagram"):
        ig = paket["instagram"]
        doc.add_heading("Instagram kaydırmalı gönderi", level=1)
        for i, x in enumerate(ig["slaytlar"], 1):
            p = doc.add_paragraph(); r = p.add_run(f"Slayt {i}: {x['baslik']}"); r.bold = True
            doc.add_paragraph(x["metin"])
        if ig.get("aciklama"):
            p = doc.add_paragraph(); r = p.add_run("Açıklama: "); r.bold = True; p.add_run(ig["aciklama"])
        if ig.get("etiketler"):
            p = doc.add_paragraph(); r = p.add_run(" ".join(ig["etiketler"])); r.font.color.rgb = GRI
    if "blog" in secim and paket.get("blog"):
        doc.add_page_break(); doc.add_heading("Blog yazısı (SEO/GEO)", level=1)
        bl = paket["blog"]
        for et, dg in (("Meta başlık", bl.get("meta_baslik")), ("Meta açıklama", bl.get("meta_aciklama")), ("URL eki", bl.get("slug")), ("Anahtar kelimeler", ", ".join(bl.get("anahtar_kelimeler") or []))):
            if dg:
                p = doc.add_paragraph(); r = p.add_run(et + ": "); r.bold = True; p.add_run(str(dg))
        _md_docx(doc, paket["blog"]["metin"])
    doc.save(f"{temel}.{marka}.docx")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(1)
    secim = (sys.argv[3] if len(sys.argv) > 3 else "kapak,youtube,blog,shorts").split(",")
    uret(sys.argv[1], sys.argv[2], secim)

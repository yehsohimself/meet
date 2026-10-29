"""Türkçe konuşmanın içine karışan İngilizce terimler.

İki iş yapar:
1. ipucu_yap(dil, isimler): ses modeline (Whisper) verilecek başlangıç ipucunu kurar. Türkçe çözümde
   sık kullanılan İngilizce iş terimleri + kullanıcının sözlüğü + müşteri adları + konuşmacı adları
   ipucuna girer; model "session"ı "sesin", "creative"i "kreativ" diye yazmaz.
2. duzelt(segmentler, log): yazı çıktıktan sonra özet modeliyle (Ollama) yanlış yazılmış terimleri bulur.
   Yalnızca sözlükteki terimlerin bozuk yazımları düzeltilir; Türkçe kelimelere dokunulmaz.
   Her öneri ayrıca benzerlik ve sözlük denetiminden geçer.

Elle: python terimler.py transkript_tr_X.json   (txt/docx/srt yeniden yazılır)
Sözlük: ayarlar.json → "sozluk": ["onboarding", "dashboard"]  (sitede Ayarlar → Sık geçen terimler)
"""
import difflib
import json
import os
import re
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent

# Ajans / pazarlama / iş hayatında Türkçe cümle içinde sık geçen İngilizce terimler.
VARSAYILAN_TERIMLER = [
    "brief", "session", "creative", "feedback", "deadline", "launch", "client", "content", "brand", "meeting",
    "agenda", "budget", "design", "review", "approve", "presentation", "workshop", "call", "follow-up", "insight",
    "strategy", "campaign", "concept", "storyboard", "timeline", "update", "pitch", "trend", "target", "performance",
    "engagement", "influencer", "reels", "story", "post", "shooting", "casting", "mood board", "key visual", "copy",
    "headline", "slogan", "deck", "asset", "schedule", "benchmark", "reference", "revize", "onboarding", "dashboard",
    "report", "insight", "lead", "funnel", "conversion", "awareness", "reach", "impression", "organic", "paid", "ads",
    "boost", "sponsor", "collab", "product", "packaging", "sample", "mockup", "prototype", "roadmap", "milestone",
    "sprint", "backlog", "ticket", "bug", "release", "demo", "beta", "default", "template", "format", "export",
    "share", "link", "drive", "slide", "mail", "chat", "call", "check", "ok", "okay", "team", "lead", "manager",
    "founder", "partner", "investor", "startup", "scale", "growth", "retention", "churn", "metric", "kpi", "okr",
    "ceo", "cmo", "cto", "art director", "copywriter", "strategist", "account", "community", "social media",
    "stakeholder", "value proposition", "go-to-market", "user", "customer", "journey", "touchpoint", "persona",
    "positioning", "tone of voice", "guideline", "identity", "logo", "layout", "typography", "visual", "video",
    "motion", "edit", "cut", "render", "voice over", "jingle", "script", "scene", "frame", "storytelling",
]
# Whisper ipucuna girecek kısa çekirdek (ipucu ~224 parça ile sınırlı; en sık olanlar yeter)
IPUCU_TERIMLER = [
    "session", "creative", "brief", "deadline", "feedback", "launch", "pitch", "client", "content", "brand",
    "meeting", "agenda", "budget", "design", "review", "approve", "presentation", "workshop", "call", "follow-up",
    "insight", "strategy", "campaign", "concept", "storyboard", "timeline", "update", "trend", "target",
    "performance", "engagement", "influencer", "reels", "story", "post", "shooting", "casting", "mood board",
    "key visual", "copy", "headline", "deck", "asset", "schedule", "benchmark", "reference", "onboarding",
    "dashboard", "report", "lead", "funnel", "conversion", "awareness", "roadmap", "sprint", "demo", "template",
]


def ayar_sozlugu():
    """ayarlar.json'daki kullanıcı sözlüğü + müşteri adları. Misafir işlerinde boş (sahibin müşteri adları sızmasın)."""
    if os.environ.get("VH_MISAFIR"):
        return [], []
    try:
        d = json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        d = {}
    terimler = [str(x).strip() for x in (d.get("sozluk") or []) if str(x).strip()]
    try:                                       # Studio'da elle düzeltilen adlar/terimler (studio_duzelt; 2026-10-24)
        import studio_duzelt
        terimler += studio_duzelt.ogrenilen_terimler()
    except Exception:  # noqa: BLE001
        pass
    musteriler = [str(x).strip() for x in (d.get("musteriler") or []) if str(x).strip()]
    # şirketlerin müşteri listeleri de (2026-10-28): eski düz liste yalnız 5 addı, 31 müşterinin çoğu ses tanımaya hiç verilmiyordu ("ING" → "YNG")
    for sk in d.get("sirketler") or []:
        if isinstance(sk, dict):
            musteriler += [str(x).strip() for x in (sk.get("musteriler") or []) if str(x).strip()]
    return terimler, musteriler


def _tekil(liste):
    gorulen, sonuc = set(), []
    for t in liste:
        k = t.lower()
        if k and k not in gorulen:
            gorulen.add(k); sonuc.append(t)
    return sonuc


_TOKEN = None


def _parca_sayisi(metin):
    """Whisper'ın ipucu parça (token) sayısı; ayırıcı yüklenemezse kaba tahmin (3,2 harf ≈ 1 parça)."""
    global _TOKEN
    if _TOKEN is None:
        try:
            from mlx_whisper.tokenizer import get_tokenizer
            _TOKEN = get_tokenizer(multilingual=True, num_languages=100)
        except Exception:  # noqa: BLE001
            _TOKEN = False
    return len(_TOKEN.encode(metin)) if _TOKEN else int(len(metin) / 3.2) + 1


def _musteri_sirasi(musteriler):
    """Müşteri adları son 60 günün toplantılarında ne sıklıkta geçtiyse o sırada (toplantının müşterisi ×3, Kısaca maddesi ×1); bütçeye en çok
    çalışılanlar sığsın. Okunamazsa sıra değişmez."""
    try:
        import time
        import kitaplik_onbellek
        say = {}
        for x in kitaplik_onbellek.hepsi():
            v = x.get("veri") or {}
            if not v.get("toplanti") or (v.get("olusturma") or 0) < time.time() - 60 * 86400:
                continue
            if v.get("musteri"):
                say[str(v["musteri"]).casefold()] = say.get(str(v["musteri"]).casefold(), 0) + 3
            for m in (v.get("kisaca") or {}).get("musteriler") or []:
                say[str(m.get("ad")).casefold()] = say.get(str(m.get("ad")).casefold(), 0) + int(m.get("adet") or 1)
        return sorted(musteriler, key=lambda m: -say.get(m.casefold(), 0))
    except Exception:  # noqa: BLE001
        return musteriler


IPUCU_BUTCE = 190            # Whisper ipucunu 223 parçada soldan keser (baştaki "Türkçe konuşuyoruz" çerçevesi gider); payla


def ipucu_yap(dil, isimler=None, ekstra=None):
    """Whisper başlangıç ipucu. dil: çözülecek dil kodu (None = bilinmiyor). 2026-10-28: şirketlerin bütün müşterileri girince ipucu 242 parçaya
    çıkıyordu; artık parça bütçesiyle kurulur: kullanıcının sözlüğü, en sık 10 terim, müşteri adları, kalan yere öteki terimler; en çok 8 kişi adı."""
    isimler = [x for x in (isimler or []) if x]
    ozel, musteriler = ayar_sozlugu()
    ozel = _tekil(ozel + (ekstra or []))
    if dil == "tr":
        ad_kismi = (" " + ", ".join(isimler[:8]) + " sohbet ediyor.") if isimler else ""
        kalip = lambda T: "Sohbet ediyoruz. Türkçe konuşuyoruz ama " + ", ".join(T) + " gibi İngilizce terimler de kullanıyoruz." + ad_kismi   # noqa: E731
        terimler = []
        for t in _tekil(ozel + IPUCU_TERIMLER[:10] + _musteri_sirasi(_tekil(musteriler)) + IPUCU_TERIMLER[10:])[:90]:   # en sık 10 terim ("session", "creative") önce
            if _parca_sayisi(kalip(terimler + [t])) > IPUCU_BUTCE:
                if len(terimler) >= 12:
                    break
                continue
            terimler.append(t)
        return kalip(terimler)
    parcalar = []
    if isimler:
        parcalar.append(", ".join(isimler) + (" sohbet ediyor." if dil in (None, "tr") else "."))
    adlar = _tekil(ozel + musteriler)[:40]
    if adlar:
        parcalar.append(", ".join(adlar) + ".")
    return " ".join(parcalar) or None


# ----------------------------------------------------------------------------- yazı sonrası düzeltme
def _asciile(s):
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")
    return s.translate(tablo).lower()


def _kelime_deseni(kelime):
    return re.compile(r"(?<![^\W\d_])" + re.escape(kelime) + r"(?![^\W\d_])", re.IGNORECASE)


def _oneri_gecerli(yanlis, dogru, satir, sozluk):
    if not yanlis or not dogru or len(yanlis) < 3 or len(dogru) < 3:
        return False
    if not _kelime_deseni(yanlis).search(satir):
        return False
    govde = dogru.split("'")[0].split("’")[0].strip().lower()
    if not re.fullmatch(r"[A-Za-z][A-Za-z \-]*", govde):          # düzeltme İngilizce/Latin olmalı
        return False
    if _asciile(yanlis.split("'")[0]) == govde:                     # zaten aynı
        return False
    if govde not in sozluk:                                         # yalnızca sözlükteki terimler (Türkçe kelimeye dokunma)
        return False
    return difflib.SequenceMatcher(None, _asciile(yanlis), govde).ratio() >= 0.5


def _kelimelere_uygula(kelimeler, yanlis, dogru):
    """Kelime zamanları listesinde (bas, bit, kelime) yanlış yazımı değiştirir; çok kelimeli ise birleştirir."""
    if not kelimeler:
        return
    hedef = _asciile(re.sub(r"[^\w'’\- ]+", "", yanlis)).split()
    n = len(hedef)
    i = 0
    while i <= len(kelimeler) - n:
        parca = [_asciile(re.sub(r"[^\w'’\-]+", "", k[2])) for k in kelimeler[i:i + n]]
        if parca == hedef:
            son = kelimeler[i + n - 1]
            ek = re.search(r"[^\w'’\-]+$", son[2])
            kelimeler[i] = [kelimeler[i][0], son[1], dogru + (ek.group(0) if ek else "")]
            del kelimeler[i + 1:i + n]
        i += 1


def _sor(istem, zaman_asimi=600):
    """Ollama'ya kararlı (sıcaklık 0) JSON sorusu."""
    import urllib.request
    import ozet as ozet_modulu
    govde = {"model": ozet_modulu.MODEL, "prompt": istem, "stream": False, "format": "json",
             "options": {"temperature": 0.0, "seed": 7, "num_ctx": 8192, "num_predict": 1500}}
    req = urllib.request.Request(ozet_modulu.OLLAMA + "/api/generate", data=json.dumps(govde).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=zaman_asimi) as r:
        return json.load(r).get("response", "")


def ozet_hazir():
    try:
        import ozet as ozet_modulu
        return ozet_modulu.hazir()
    except Exception:  # noqa: BLE001
        return False


def duzelt(segmentler, log=print, ekstra=None, dil="tr"):
    """Segmentlerdeki yanlış yazılmış İngilizce terimleri Ollama ile bulup düzeltir. Döner: [(yanlış, doğru)]."""
    if dil != "tr" or not segmentler:
        return []
    try:
        import ozet as ozet_modulu
    except Exception:  # noqa: BLE001
        return []
    if not ozet_modulu.hazir():
        return []
    ozel, musteriler = ayar_sozlugu()
    terimler = _tekil(ozel + (ekstra or []) + musteriler + VARSAYILAN_TERIMLER)
    sozluk = {t.lower() for t in terimler}
    yapilan = []
    # Parçalar: ~60 satır ya da ~1200 kelime
    parcalar, parca, kelime_sayisi = [], [], 0
    for i, s in enumerate(segmentler):
        parca.append(i); kelime_sayisi += len((s.get("metin") or "").split())
        if len(parca) >= 60 or kelime_sayisi >= 1200:
            parcalar.append(parca); parca, kelime_sayisi = [], 0
    if parca:
        parcalar.append(parca)
    for p_no, indeksler in enumerate(parcalar):
        satirlar = [f"[{i}] {segmentler[i].get('metin', '')}" for i in indeksler if (segmentler[i].get("metin") or "").strip()]
        if not satirlar:
            continue
        istem = (
            "Aşağıda Türkçe bir konuşmanın yazıya dökümü var. Konuşmacılar Türkçe cümlelerin içinde şu İngilizce "
            "terimleri kullanıyor: " + ", ".join(terimler) + ".\n"
            "Ses tanıma bu İngilizce kelimeleri bazen Türkçe okunuşuyla (ör. \"fitbek\" = feedback, \"kreativ\" = creative) "
            "ya da benzer sesli bir Türkçe kelimeyle (ör. \"ayrı bir sesin yapalım\" → session) yazmış.\n"
            "Görevin: SADECE listedeki terimlerin yanlış yazılmış hallerini bul ve doğru İngilizce yazımını ver. "
            "Türkçe ek varsa kesme işaretiyle koru (fitbekleri → feedback'leri). Cümle Türkçe kelimeyle zaten anlamlıysa "
            "(ör. \"sesin güzel\") DOKUNMA. Türkçe kelimelere, cümle yapısına, noktalamaya dokunma. Emin değilsen listeleme. "
            "Düzeltme yoksa boş liste ver.\n"
            "JSON biçimi: {\"duzeltmeler\": [{\"satir\": 4, \"yanlis\": \"sesin\", \"dogru\": \"session\"}]}\n\n"
            "Metin:\n" + "\n".join(satirlar) + "\n"
        )
        try:
            yanit = _sor(istem)
            oneriler = (ozet_modulu._json_coz(yanit) or {}).get("duzeltmeler") or []
        except Exception as e:  # noqa: BLE001
            log(f"      Terim denetimi bu parçada yapılamadı ({e}).")
            continue
        for o in oneriler:
            if not isinstance(o, dict):
                continue
            try:
                i = int(o.get("satir"))
            except (TypeError, ValueError):
                continue
            yanlis = str(o.get("yanlis") or "").strip(" .,;:!?\"'")
            dogru = str(o.get("dogru") or "").strip(" .,;:!?\"")
            if i < 0 or i >= len(segmentler):
                continue
            s = segmentler[i]
            if not _oneri_gecerli(yanlis, dogru, s.get("metin") or "", sozluk):
                continue
            desen = _kelime_deseni(yanlis)
            m = desen.search(s["metin"])
            yeni = __import__('harfler').ust(dogru.split(' ')[0])[:1] + dogru[1:] if m and m.group(0)[:1].isupper() else dogru
            s["metin"] = desen.sub(lambda _m: yeni, s["metin"], count=1)
            _kelimelere_uygula(s.get("kelimeler") or [], yanlis, yeni)
            yapilan.append((yanlis, dogru))
    return yapilan


def _claude_oneri_gecerli(eski, yeni, satir):
    """Claude düzeltmesi güvenli mi: eski satırda geçmeli, kısa olmalı, anlamı değiştirecek kadar farklı olmamalı."""
    if not eski or not yeni or eski == yeni or len(eski) > 60 or len(yeni) > 70:
        return False
    if eski not in satir:
        return False
    ek, yk = eski.split(), yeni.split()
    if len(ek) > 5 or abs(len(yk) - len(ek)) > 2:
        return False
    # sesçe benzerlik: düzeltme yanlış duyulmuş hali onarmalı, cümleyi yeniden yazmamalı
    oran = difflib.SequenceMatcher(None, _asciile(eski), _asciile(yeni)).ratio()
    if oran < 0.4:
        return False
    # Kelime kelime: ses benzerliği olmayan değişim (yüksek → kısa) ses tanıma hatası değil, anlam değişikliğidir
    if len(ek) == len(yk):
        for a, b in zip(ek, yk):
            if a.lower() == b.lower():
                continue
            yabanci = (b.isupper() and len(b) <= 5) or re.search(r"[wqxWQX]", b)
            r = difflib.SequenceMatcher(None, _asciile(a), _asciile(b)).ratio()
            ayni_bas = _asciile(a)[:1] == _asciile(b)[:1]
            if not yabanci and (r < 0.34 or (not ayni_bas and r < 0.5)):
                return False
    # Lakabın tam ada açılması (Mami → Muhammed): tek kelimelik özel ad belirgin uzuyorsa
    if len(ek) == len(yk) == 1 and eski[:1].isupper() and yeni[:1].isupper() and len(yeni) >= len(eski) * 1.6 and _asciile(eski)[:1] == _asciile(yeni)[:1]:
        return False
    return True


def claude_temizle(segmentler, dil="tr", isimler=None, log=print, sohbet_adlari=None):
    """Yazıya dökümü Claude'a okutur: yanlış duyulmuş özel adlar, İngilizce terimler, marka/kurum adları ve bariz ses
    tanıma hataları düzeltilir; anlam, üslup, dolgu kelimeleri ve noktalama korunur. Zaman damgaları ve kelime
    zamanları bozulmaz (yalnızca kelime değişir). Döner: [(eski, yeni)]."""
    import claude_yaz
    if not segmentler or not claude_yaz.hazir():
        return []
    ozel, musteriler = ayar_sozlugu()
    sozluk = _tekil(ozel + musteriler + VARSAYILAN_TERIMLER + list(isimler or []) + list(sohbet_adlari or []))
    satirlar = [f"[{i}] {s.get('metin', '').strip()}" for i, s in enumerate(segmentler) if (s.get("metin") or "").strip()]
    if not satirlar:
        return []
    # çok uzun metin: ~1500 satırlık parçalar (bir saatlik konuşma ≈ 600-900 satır, tek parça)
    parcalar = [satirlar[i:i + 1500] for i in range(0, len(satirlar), 1500)]
    sistem = ("Sen titiz bir transkript editörüsün. Görevin yalnızca ses tanımanın YANLIŞ DUYDUĞU kelimeleri bulmak. "
              "Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun.")
    yapilan = []
    for no, parca in enumerate(parcalar, 1):
        istem = (f"Aşağıda otomatik ses tanımayla yazıya dökülmüş bir konuşma var (dil: {dil}). Her satırın başında numarası var.\n"
                 "Bul ve düzelt: (1) yanlış yazılmış kişi, şirket, marka, ürün, yer adları; (2) Türkçe içinde kullanılan İngilizce "
                 "terimlerin Türkçe okunuşla ya da benzer sesli kelimeyle yazılmış halleri (ör. 'fitbek' → 'feedback', 'ayrı bir sesin "
                 "yapalım' → 'session', 'kreativ' → 'creative'; Türkçe eki kesme işaretiyle koru: 'fitbekleri' → 'feedback'leri'); "
                 "(3) bağlama göre açıkça yanlış duyulmuş kelimeler (ör. aynı konuşmada 'bütçe açığı' iken bir yerde 'büyüce açığı').\n"
                 "DOKUNMA: doğru Türkçe kelimeler (içerik, strateji, toplantı gibi Türkçe karşılığı olanları İngilizceye ÇEVİRME), "
                 "konuşma dili, devrik cümle, dolgu kelimeleri (ee, ıı, yani), noktalama, büyük-küçük harf tercihleri, okey/okay gibi yazım tercihleri, "
                 "lakaplar ve kısaltılmış adlar (Mami, Memo gibi; tam ada çevirme), kişinin ağzından çıkan dil sürçmeleri ve yanlış bilgiler "
                 "(konuşmacı 'yüksek vadeli' dediyse doğrusu başka olsa bile DEĞİŞTİRME; biz yalnızca ses tanımanın hatasını düzeltiyoruz, "
                 "konuşmacının söylediğini değil). Anlamı değiştiren hiçbir düzeltme yapma. Emin değilsen listeleme.\n"
                 + (f"Bu konuşmada geçebilecek adlar ve terimler (doğru yazımları): {', '.join(sozluk[:150])}\n" if sozluk else "")
                 + "Her düzeltme için satır numarası, satırda AYNEN geçen yanlış ifade (1-4 kelime) ve doğrusu. "
                 'Biçim: {"duzeltmeler": [{"satir": 12, "eski": "büyüce açığı", "yeni": "bütçe açığı"}]}. Düzeltme yoksa boş liste.\n\n'
                 + "\n".join(parca))
        try:
            c = claude_yaz.sor_json(istem, sistem, zaman_asimi=900)
        except Exception as e:  # noqa: BLE001
            log(f"      Metin denetimi yapılamadı ({str(e)[:100]})"); return yapilan
        for o in c.get("duzeltmeler") or []:
            if not isinstance(o, dict):
                continue
            try:
                i = int(o.get("satir"))
            except (TypeError, ValueError):
                continue
            if i < 0 or i >= len(segmentler):
                continue
            seg = segmentler[i]
            eski = str(o.get("eski") or "").strip(" .,;:!?\"")
            yeni = str(o.get("yeni") or "").strip(" .,;:!?\"")
            if not _claude_oneri_gecerli(eski, yeni, seg.get("metin") or ""):
                continue
            seg.setdefault("ham_metin", seg["metin"])       # 23 Ekim: duyulan ham metin korunur, düzeltme bölümde kayıtlı (okuma ekranı gösterir)
            seg.setdefault("duzeltmeler", []).append({"eski": eski, "yeni": yeni})
            seg["metin"] = seg["metin"].replace(eski, yeni, 1)
            _kelimelere_uygula(seg.get("kelimeler") or [], eski, yeni)
            yapilan.append((eski, yeni))
    return yapilan


def toplu_temizle(log=print, paralel=3):
    """Kitaplıktaki temizlenmemiş tüm transkriptleri Claude ile temizler (hazır altyazılılar hariç); önce yedek alır.
    txt/docx/srt yeniden yazılır; veri["temizlik"] işareti konur (düzeltme olmasa da, tekrar denenmesin)."""
    import shutil
    from concurrent.futures import ThreadPoolExecutor
    from transkript import ciktilari_yaz
    import claude_yaz
    yedek = KLASOR / ".yedek" / ("temizlik_" + __import__("time").strftime("%Y-%m-%d_%H%M"))
    adaylar = []
    for js in sorted(KLASOR.glob("transkript_*.json")):
        try:
            d = json.loads(js.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        v = d["veri"]
        if v.get("temizlik") or "altyaz" in str(v.get("kaynak", "")).lower() or not d.get("segmentler"):
            continue
        adaylar.append(js)
    if not adaylar:
        log("Temizlenecek transkript yok."); return []
    yedek.mkdir(parents=True, exist_ok=True)
    for js in adaylar:
        shutil.copy2(js, yedek / js.name)
    log(f"{len(adaylar)} transkript temizlenecek; yedek: {yedek}")
    sonuc = []

    def _tek(js):
        d = json.loads(js.read_text(encoding="utf-8")); v, seg = d["veri"], d["segmentler"]
        adlar = [a for a in (v.get("etiket") or {}).values() if not str(a).startswith("Konuşmacı ")]
        try:
            if v.get("toplanti"):
                with claude_yaz.toplanti():
                    yapilan = claude_temizle(seg, dil=v.get("dil", "tr"), sohbet_adlari=adlar, log=log) if claude_yaz.hazir() else None
            else:
                yapilan = claude_temizle(seg, dil=v.get("dil", "tr"), sohbet_adlari=adlar, log=log)
        except Exception as e:  # noqa: BLE001
            log(f"  {js.stem}: hata ({e})"); return
        if yapilan is None:
            log(f"  {js.stem}: toplantılarda Claude kapalı, atlandı"); return
        # dosya bu arada site tarafından değiştirildiyse veri alanlarını yeniden oku, yalnız segmentleri koy
        try:
            guncel = json.loads(js.read_text(encoding="utf-8")); v = guncel["veri"]
        except Exception:  # noqa: BLE001
            pass
        v["temizlik"] = {"duzeltme": len(yapilan), "ornekler": [f"{a} → {b}" for a, b in yapilan[:20]], "zaman": __import__("time").time(), "toplu": True}
        if yapilan:
            ciktilari_yaz(js.with_suffix(""), v, seg)
        js.write_text(json.dumps({"veri": v, "segmentler": seg}, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  {js.stem}: {len(yapilan)} düzeltme" + (": " + ", ".join(f"{a} → {b}" for a, b in yapilan[:6]) if yapilan else ""))
        sonuc.append((js.stem, yapilan))

    with ThreadPoolExecutor(max_workers=paralel) as ex:
        list(ex.map(_tek, adaylar))
    log(f"Bitti. {sum(len(y) for _, y in sonuc)} düzeltme, {len(sonuc)} transkript.")
    return sonuc


def main():
    if "--hepsi" in sys.argv:
        sys.path.insert(0, str(KLASOR))
        toplu_temizle(log=lambda m: print(m, flush=True)); return
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    yol = Path(sys.argv[1])
    sys.path.insert(0, str(KLASOR))
    from transkript import ciktilari_yaz, cikti_adi  # noqa: F401
    v = json.loads(yol.read_text(encoding="utf-8"))
    veri, segmentler = v["veri"], v["segmentler"]
    if "--claude" in sys.argv:
        yapilan = claude_temizle(segmentler, dil=veri.get("dil", "tr"), sohbet_adlari=[a for a in (veri.get("etiket") or {}).values() if not str(a).startswith("Konuşmacı ")])
        if yapilan:
            veri["temizlik"] = {"duzeltme": len(yapilan), "ornekler": [f"{a} → {b}" for a, b in yapilan[:20]], "zaman": __import__("time").time()}
    else:
        yapilan = duzelt(segmentler, dil=veri.get("dil", "tr"))
    if not yapilan:
        print("Düzeltilecek terim bulunamadı."); return
    temel = yol.with_suffix("")
    ciktilari_yaz(temel, veri, segmentler)
    print(f"{len(yapilan)} düzeltme: " + ", ".join(f"{a} → {b}" for a, b in yapilan))
    print(f"Bitti. Dosya: {temel}.txt")


if __name__ == "__main__":
    main()

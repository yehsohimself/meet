"""duman_testi.py - Her değişiklikten sonra 1-2 dakikalık otomatik kontrol: "bir şeyi bozdum mu?"

Neden (2026-10-18 teknik değerlendirme): otomatik test yoktu; sözdizimi hatası ya da kayıp bir alan siteyi açılmaz hale getirebilirdi.
Katmanlar:
  hizli  : bütün .py dosyaları derlenir, ana modüller içe aktarılır, static/index.html içindeki betik sözdizimi denetlenir (deno).
  birim  : saf hesaplar (atölye kuralları, süper sayımı, kalıp yakalama, marka brief'i, Radar tohumları, viral puanı, paylaşım planı).
  canli  : çalışan sitenin uçları 200 ve geçerli JSON döner mi.
  tam    : macOS'in Türkçe sesiyle (Yelda) kısa ses üretilir, transkript.py ile yazıya dökülür, Türkçe kelimeler aranır (~1-2 dk).
  studio : aynı sentetik örnek VİDEOyla Studio zinciri: yazıya dökme → YouTube altyazısı kuralları → altyazılı video → klip → metinden kesme (her gece, ~20 sn).
  studio_dublaj : studio + 8 sn'lik dublaj önizlemesi, ses var mı (haftada bir; ağır model).
yeniden_baslat.py yeniden başlatmadan ÖNCE hizli+birim çalıştırır; başarısızsa siteyi yeniden başlatmaz (bozuk kod devreye girmez),
sonra canli. Sonuç: kayitlar/.duman.json. Elle: python duman_testi.py [hizli|birim|canli|tam|studio|studio_dublaj|meet|meet_kisaca|hepsi]
Test çıktıları geçici klasörde üretilir (--ad duman_<zaman>) ve yalnızca o adla silinir.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
PY = str(KLASOR / ".venv" / "bin" / "python") if (KLASOR / ".venv" / "bin" / "python").exists() else sys.executable   # kesilen depoda venv olmayabilir (2026-10-25)
SITE = "http://127.0.0.1:8765"
SONUC = KLASOR / "kayitlar" / ".duman.json"


def hizli():
    hatalar = []
    for f in sorted(KLASOR.glob("*.py")) + sorted((KLASOR / "sunucu").glob("*.py")):   # site.py 2026-10-23'te sunucu/ parçalarına bölündü
        r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True)
        if r.returncode:
            hatalar.append(f"{f.name}: derlenmiyor: {r.stderr.strip().splitlines()[-1][:200]}")
    _adlar = [a.strip() for a in "atolye, atolye_bilgi, atolye_kaynak, atolye_analiz, paylasim, claude_yaz, ozet, marka, yedek, ghost_gelisim, ghost_hikaye, ghost_yanit, couple, couple_site, couple_kaynak, couple_takip, couple_video, studio_duzelt, yayin, sahne_dizin, studio_gelisim, pt, pt_beslenme, pt_hareket, pt_rota, pt_site, pt_sohbet, pt_saglik, pt_yemek, pt_form, pt_kanit, pt_push, pt_koc, pt_kart, pt_gorsel, pt_storyboard, pt_youtube, pt_ses, pt_oyun, pt_kitaplik, pt_hizli, pt_anatomi, pt_programlar, pt_oneri, pt_kisayol, pt_bls".split(",") if a.strip()]
    _adlar = [a for a in _adlar if (KLASOR / f"{a}.py").exists()]            # kesilen depoda bazı ürünler yok (2026-10-25)
    modul = "import " + ", ".join(_adlar)
    r = subprocess.run([PY, "-c", f"import sys; sys.path.insert(0, {str(KLASOR)!r}); {modul}"], capture_output=True, text=True, cwd=str(KLASOR))
    if r.returncode:
        hatalar.append(f"modül içe aktarılamıyor: {r.stderr.strip().splitlines()[-1][:200]}")
    import collections                                     # 2026-10-25: aynı ad iki parçada tanımlanırsa (sarmalama kalıbı `x_onceki = x` / `x_sahip = x` olmadan)
    tanim = collections.defaultdict(list)                  # sonraki öncekini sessizce ezer (_toplanti_bitir olayı: Ghost sürümü Meet'inkini ezdi)
    for f in sorted((KLASOR / "sunucu").glob("[0-9][0-9]_*.py")):
        metin = f.read_text(encoding="utf-8")
        for m in re.finditer(r"^def (\w+)\(", metin, re.M):
            tanim[m.group(1)].append((f.name, metin))
    for ad, yerler in tanim.items():
        if len(yerler) > 1:
            for dosya, metin in yerler[1:]:
                if not re.search(rf"^\w+ = {ad}\s*(#.*)?$", metin, re.M):      # sarmalama: önceki tanım bir ada alınmış (`_x_onceki = x`)
                    hatalar.append(f"{dosya}: `{ad}` başka bir parçada da tanımlı ve sarmalanmıyor (önceki tanım ezilir)")
    try:                                                   # 2026-10-25: depoya kişisel bilgi sızmasın (sizinti.py; ayarlardaki adlar, e-posta, anahtar, /Users yolu)
        import sizinti
        for b in sizinti.denetle()[:12]:
            hatalar.append(f"sızıntı: {b['dosya']}:{b['satir']} {b['tur']}: {b['parca']}")
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"sızıntı denetimi çalışmadı: {e}")
    for js in [j for j in ("studio_ek.js", "pt-sw.js") if (KLASOR / "static" / j).exists()]:   # ayrı betik dosyaları (sözdizimi hatası bütün ekleri durdurur)
        node = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")
        r = subprocess.run([node, "--check", str(KLASOR / "static" / js)], capture_output=True, text=True) if Path(node).exists() else None
        if r is not None and r.returncode:
            hatalar.append(f"{js}: sözdizimi hatası: {(r.stderr.strip().splitlines() or [''])[-1][:200]}")
    for sayfa in [p for p in ("index.html", "couple.html", "pt.html") if (KLASOR / "static" / p).exists()]:   # Couple ve PT sayfaları kuruluysa (2026-10-25: ürünler ayrı)
        html = (KLASOR / "static" / sayfa).read_text(encoding="utf-8")
        betik = "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S))
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
            t.write("new Function(" + json.dumps(betik) + ");\n")
        r = subprocess.run(["/opt/homebrew/bin/deno", "run", "--quiet", t.name], capture_output=True, text=True)
        Path(t.name).unlink(missing_ok=True)
        if r.returncode:
            hatalar.append(f"{sayfa} betiği: {(r.stderr or r.stdout).strip().splitlines()[0][:200]}")
    return hatalar


def birim():
    hatalar = []

    def dene(ad, kosul):
        try:
            if not kosul():
                hatalar.append(f"{ad}: beklenen sonuç çıkmadı")
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{ad}: {type(e).__name__}: {str(e)[:160]}")
    # 2026-10-25: ürünler ayrı kurulabilir; bir ürünün modülleri yoksa o blok atlanır (hata değil)
    def _urun(ad, modüller, blok):
        import importlib.util
        for m in modüller:
            if importlib.util.find_spec(m) is None:
                return
        blok()

    def _b_atolye():
        import atolye
        import atolye_kaynak as K
        import paylasim
        akis = {"bicim": "kisa", "sure": "30 sn", "sahneler": [
            {"zaman": "0-3 sn", "super": "Üst köşe: #reklam | Ortada: Sizce ne var?", "ses": "Bunu kimse beklemiyordu, bakın."},
            {"zaman": "3-30 sn", "super": "Kısa yazı", "ses": " ".join(["kelime"] * 70)}]}
        dene("süper sayımı etiket ve yerleşim notunu saymaz", lambda: atolye._super_kelime("Üst köşe: #işbirliği | Ortada: Sizce zarfta ne var?") == 4)
        dene("kural denetimi temiz akışta not vermez", lambda: atolye.kural_denetimi(akis) == [])
        dene("kural denetimi uzun süperi yakalar", lambda: any("8 kelime" in u for u in atolye.kural_denetimi(
            {**akis, "sahneler": [akis["sahneler"][0], {"zaman": "3-30 sn", "super": " ".join(["a"] * 12), "ses": "x"}]})))
        _ilk = next(iter(atolye.markalar_oku().get("markalar") or {}), "")
        dene("marka brief'i profil + kampanya", lambda: not _ilk or ("BU KAMPANYA" in atolye.marka_brief(_ilk, "Ürün", "deneme") and "YASAKLAR" in atolye.marka_brief(_ilk)))
        dene("Radar tohumları okunuyor", lambda: len(atolye.radar_tohumlari("bebek cilt bakımı")) >= 5)
        dene("reklamla şişmiş izlenme sezilir", lambda: atolye.ucretli_suphesi({"izlenme": 500000, "etkilesim": 0.05}))
        dene("viral puanı (olağanın katı)", lambda: (K.viral_puani({"izlenme": 50000, "tarih": "", "kisa": True},
                                                                   {"izlenme": 10000, "gunluk": None, "n": 12}) or {}).get("kat") == 5.0)
        dene("paylaşım: kişisel deneyim ve konuşmacı yakalanır", lambda: len(paylasim._kalip_notlari("Benim akışımda böyle. Ali denedi.", [], ["Ali"], "")) == 2)
        dene("paylaşım: klişe yakalanır", lambda: bool(paylasim._kalip_notlari("Sonuç şu: bu tablo çok şey gösteriyor.", [])))
        def _plan_dengeli():
            T = [{"alan": a, "okur": {}, "zaman": time.time()} for a in ["Futbol"] * 8 + ["Kreatif"] * 6 + ["Toplum"] * 6 + ["Teknoloji ve yapay zekâ"] * 6]
            bugun = [t for t in paylasim.plan(T) if t.get("plan_gun") == "Bugün"]
            g = int((paylasim.profil().get("hedef") or {}).get("x_gunluk") or 4)
            tavan = 1 if g <= 4 else -(-g // 3)
            return (all(sum(1 for t in bugun if t["alan"] == a) <= tavan for a in {t["alan"] for t in bugun})
                    and sum(1 for t in bugun if "yapay" in t["alan"]) <= max(1, len(bugun) // 4))
        dene("paylaşım planı: alan başına tavan, yapay zekâ en çok dörtte biri", _plan_dengeli)
        dene("X profili yükleniyor", lambda: len(paylasim.profil().get("ornekler") or []) >= 5)
        dene("atölye indirmesi özgün ses kanalını ister", lambda: "format_note*=original" in (KLASOR / "atolye_analiz.py").read_text(encoding="utf-8"))
    _urun('atolye', ('atolye', 'atolye_kaynak', 'paylasim'), _b_atolye)

    def _b_studio():
        dene("studio: altyazı denetimi çakışma, uzun satır ve bozuk kartı yakalar", lambda: _srt_denetle(
            "1\n00:00:00,500 --> 00:00:03,000\nMerhaba dünya\n\n2\n00:00:03,100 --> 00:00:06,000\nİkinci kart\n", 6.5) == [] and len(_srt_denetle(
            "1\n00:00:00,500 --> 00:00:03,000\nBu satır kırk iki karakterden çok daha uzun olduğu için kurala uymaz\n\n3\n00:00:02,000 --> 00:00:12,000\nx\n", 6.5)) >= 2)
        import studio_duzelt                                   # Studio (2026-10-24): yerinde düzeltme zamanları korur, yayın bölümleri YouTube kuralına uyar
        import yayin

        def _duzelt():
            seg = [{"bas": 0, "bit": 2, "metin": "Bugün Pekşat çektik.", "kelimeler": [[0, .5, "Bugün"], [.5, 1.2, "Pekşat"], [1.2, 2, "çektik."]]}]
            r = studio_duzelt.paragraf_duzelt(seg, 0, 2, "Bugün Packshot çektik.")
            return seg[0]["metin"] == "Bugün Packshot çektik." and seg[0]["kelimeler"][1] == [.5, 1.2, "Packshot"] and r["ciftler"] == [("Pekşat", "Packshot")]
        dene("studio: paragraf düzeltmesi kelime zamanlarını korur", _duzelt)
        dene("studio: yayın bölümleri 00:00'dan başlar, 10 sn'den sık değildir",
             lambda: [b["sn"] for b in yayin._bolumleri_temizle([{"zaman": "00:05", "baslik": "a"}, {"zaman": "00:09", "baslik": "b"}, {"zaman": "01:00", "baslik": "c"},
                                                                {"zaman": "02:00", "baslik": "d"}], 300)] == [0, 60, 120])
    _urun('studio', ('studio_duzelt', 'yayin'), _b_studio)

    def _b_ghost():
        import ghost_gelisim
        import ghost_hikaye
        dene("hikâye: dayanak cümlesi kaynakta aranır", lambda: ghost_hikaye._kaynak_var("On 24 October 1885 she was travelling from Antwerp",
                                                                                        ["x On 24 October 1885 she was travelling from Antwerp, Belgium y"])
             and not ghost_hikaye._kaynak_var("tamamen uydurma bir cümle burada duruyor", ["başka bir metin"]))
        def _sinirli():
            d = {"aktif": {}}; pr = {"alanlar": [{"kod": "futbol", "agirlik": 3}], "hedef": {"x_gunluk": 10}}; kayit = {}
            r1 = ghost_gelisim._uygula({"tur": "agirlik", "alan": "futbol", "yeni": 9}, d, lambda **k: kayit.update(k), pr)
            r2 = ghost_gelisim._uygula({"tur": "x_gunluk", "yeni": 30}, d, lambda **k: kayit.update(k), pr)
            r3 = ghost_gelisim._uygula({"tur": "asama_kapat", "hedef": "rm -rf"}, d, lambda **k: kayit.update(k), pr)
            return r1["yeni"] == 4 and r2["yeni"] == 12 and r3 is None
        dene("gelişim: kendiliğinden ayarlar sınırlı (±1 ağırlık, ±2 hedef, bilinmeyen aşama yok)", _sinirli)
    _urun('ghost', ('ghost_gelisim', 'ghost_hikaye', 'paylasim'), _b_ghost)

    def _b_couple():
        import couple
        kz = {"sektor": "Dermokozmetik, bebek bakımı"}
        dene("couple: tedavi iddiası yakalanır, yasak listesindeki aynı söz yakalanmaz",
             lambda: couple.kod_denetimi("Bu krem egzamayı tedavi eder.", kz) and not couple.kod_denetimi("Yasaklar: tedavi eder gibi ifadeler kullanılmaz.", kz))
        dene("couple: creator brief'inde işbirliği etiketi aranır", lambda: any("etiket" in n["not"] for n in couple.kod_denetimi("Ana mesaj: rahat uyku.", kz, "creator_brief")))
        dene("couple: sunum metni slaytlara bölünür",
             lambda: [x["baslik"] for x in couple._slaytlar("## Slayt 1: İçgörü\n- a\nKonuşmacı notu: n\n**Slayt 2 — Fikir**\n- b")] == ["İçgörü", "Fikir"])
    _urun('couple', ('couple',), _b_couple)

    def _b_meet():
        import meet_gelisim                                    # Meet (2026-10-24): kesin durumlarda eleme, türetilmiş alanlara ad yayma
        seg = [{"bas": 0, "bit": 60, "k": "0"}, {"bas": 60, "bit": 120, "k": "1"}, {"bas": 120, "bit": 180, "k": "2"}]
        dene("meet: katılımcı listesinden eleyerek ad (tek adsız, tek kalan kişi)",
             lambda: meet_gelisim.eleme({"etiket": {"0": "Ali Veli", "1": "Eray Yıldız", "2": "Konuşmacı 3"},
                                         "katilimcilar": ["Ali Veli", "Eray Yıldız", "Ayşe Demir", "Enter Full Screen"]}, seg) == {"2": "Ayşe Demir"})
        dene("meet: belirsizse eleme ad vermez (iki adsız)",
             lambda: meet_gelisim.eleme({"etiket": {"0": "Ali", "1": "Konuşmacı 2", "2": "Konuşmacı 3"}, "katilimcilar": ["Ali", "Ayşe Kaya", "Can Er"]}, seg) == {})
        def _yay():
            v = {"kisaca": {"kisiler": [{"ad": "Konuşmacı 1", "isler": [{"is": "Konuşmacı 1 sunumu atar"}]}, {"ad": "Konuşmacı 12"}]}}
            meet_gelisim.etiket_yay(v, "Konuşmacı 1", "Ayşe Demir")
            return v["kisaca"]["kisiler"][0]["ad"] == "Ayşe Demir" and v["kisaca"]["kisiler"][1]["ad"] == "Konuşmacı 12"
        dene("meet: ad değişikliği Kısaca'ya yayılır, 'Konuşmacı 12' bozulmaz", _yay)

        def _birlestir():                                     # toplantı sonrası akış, o arada yapılan kullanıcı değişikliklerini ezmez (2026-10-25)
            import ast
            import copy
            import threading
            kaynak = (KLASOR / "sunucu" / "04_toplanti.py").read_text(encoding="utf-8")
            agac = ast.parse(kaynak)
            parca = [ast.get_source_segment(kaynak, n) for n in agac.body if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("_MEET_YOK", "MEET_KULLANICI_ALANI")
                     for t in n.targets)) or (isinstance(n, ast.FunctionDef) and n.name == "_meet_kaydet")]
            d = Path(tempfile.mkdtemp(prefix="duman_birlestir_"))
            ns = {"KLASOR": d, "kilit": threading.Lock(), "ciktilari_yaz": lambda *a: None}
            exec("\n".join(parca), ns)
            js = d / "t.json"
            js.write_text(json.dumps({"veri": {"etiket": {"0": "Konuşmacı 1"}, "baslik": "eski"}, "segmentler": [{"metin": "eski", "k": "0"}]}), encoding="utf-8")
            veri = json.loads(js.read_text(encoding="utf-8"))["veri"]; ilk = copy.deepcopy(veri)
            veri["kisaca"] = {"ozet": ["yeni"]}; veri["baslik"] = "akış"
            f = json.loads(js.read_text(encoding="utf-8")); f["veri"]["etiket"]["0"] = "Ayşe"; f["segmentler"][0]["metin"] = "düzeltildi"
            js.write_text(json.dumps(f), encoding="utf-8")
            ns["_meet_kaydet"]("t", veri, ilk)
            son = json.loads(js.read_text(encoding="utf-8"))
            shutil.rmtree(d, ignore_errors=True)
            return son["veri"].get("kisaca") == {"ozet": ["yeni"]} and son["veri"]["etiket"]["0"] == "Ayşe" and son["segmentler"][0]["metin"] == "düzeltildi" \
                and son["veri"]["baslik"] == "akış"
        dene("meet: toplantı sonrası akış kullanıcının o arada yaptığı ad ve metin değişikliklerini ezmez", _birlestir)
    _urun('meet', ('meet_gelisim',), _b_meet)

    def _b_pt():
        import pt                                              # PT (2026-10-25): görünür kurallar kodda; sabah ışığı, basamaklar, ekipmansız karşılık
        dene("pt: kötü uyku + düşük enerji kırmızı, ağrı 4 sarı, iyi gün yeşil",
             lambda: pt.sabah_isigi({"uyku": "kotu", "enerji": 2})[0] == "kirmizi" and pt.sabah_isigi({"agri": [{"bolge": "diz", "puan": 4}]})[0] == "sari"
             and pt.sabah_isigi({"uyku": "iyi", "enerji": 4})[0] == "yesil")
        dene("pt: zincirde bir üst/alt basamak", lambda: pt.zincir_komsu("sinav", 1) == "elmas_sinav" and pt.zincir_komsu("duvar_sinav", -1) is None)
        dene("pt: yolda barfiks ekipmansız bir harekete döner", lambda: pt.KATALOG[pt.ekipmansiz_karsilik("barfiks", set())]["ekipman"] in ("yok", "mat", "duvar"))
        import pt_form, math as _m
        dene("pt: form raporu tekrarları sayar (yapay açı eğrisi)", lambda: len(pt_form._tekrarlar([170 - 40 * (1 - _m.cos(2 * _m.pi * i / 25)) for i in range(125)])) == 5)
        dene("pt: nabız bölgeleri yaştan", lambda: pt.nabiz_bolgeleri({"yas": 36})["en_yuksek"] == 183)
        dene("pt: yaş doğum tarihinden", lambda: pt.yas_hesapla("2000-01-01") == pt.bugun().year - 2000 - (0 if (pt.bugun().month, pt.bugun().day) >= (1, 1) else 1))
        dene("pt: kırmızı gün yükleme yapmaz", lambda: pt.seansi_uyarla({"tur": "kalistenik", "bolumler": [{"ad": "Ana bölüm", "hareketler": [{"kod": "sinav"}]}]}, "kirmizi").get("toparlanma"))
    _urun('pt', ('pt', 'pt_form'), _b_pt)

    return hatalar


def testler():
    """pytest (tests/): sanal kökte birim + Flask istemcisi testleri (2026-10-25). Hatalar: başarısız test adları."""
    r = subprocess.run([PY, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "--no-header"], capture_output=True, text=True, cwd=str(KLASOR), timeout=600)
    if r.returncode == 0:
        return []
    return [l.strip()[:200] for l in (r.stdout + r.stderr).splitlines() if l.startswith("FAILED") or l.startswith("ERROR")] or [f"pytest çıkış kodu {r.returncode}"]


def canli():
    hatalar = []
    for yol in ("/", "/api/isler", "/api/gecmis", "/api/ayarlar", "/api/atolye", "/api/atolye/bilgi", "/api/paylasimlar", "/api/mesgul",
                "/api/indirilenler", "/api/takip", "/api/sistem-durum", "/api/pt", "/api/pt/katalog"):
        try:
            with urllib.request.urlopen(SITE + yol, timeout=30) as r:
                govde = r.read()
                if r.status != 200:
                    hatalar.append(f"{yol}: HTTP {r.status}")
                elif yol != "/":
                    json.loads(govde)
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{yol}: {str(e)[:120]}")
    # Studio davetlileri (2026-10-24): 8770 kapısı davetsiz isteği ve sahibin uçlarını REDDETMELİ (tünel dışarıya bu porta açılır)
    for yol, beklenen in (("/", 403), ("/api/gecmis", 401), ("/api/ayarlar", 401), ("/api/davetler", 401), ("/?u=meet", 403),
                          ("/api/meet/durum", 401), ("/static/index.html", 403),   # Meet davetlileri (2026-10-24)
                          ("/api/sahip-cihaz", 401), ("/s/uydurmaanahtaruydurmaanahtaruydurma1", 403), ("/sahip-manifest.webmanifest", 401)):   # telefon (2026-10-25)
        try:
            urllib.request.urlopen("http://127.0.0.1:8770" + yol, timeout=15)
            hatalar.append(f"misafir kapısı {yol}: davetsiz istek GEÇTİ")
        except urllib.error.HTTPError as e:
            if e.code != beklenen:
                hatalar.append(f"misafir kapısı {yol}: {e.code} (beklenen {beklenen})")
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"misafir kapısı {yol}: {str(e)[:80]}")
    return hatalar


def tam():
    """Türkçe sentetik sesle uçtan uca yazıya dökme (ses modeli + hat çalışıyor mu)."""
    d = Path(tempfile.mkdtemp(prefix="duman_"))
    ses = d / "duman.aiff"
    subprocess.run(["say", "-v", "Yelda", "-o", str(ses), "Merhaba, bu bir deneme kaydıdır. Video Hub sistemi çalışıyor mu diye bakıyoruz."], check=True)
    m4a = d / "duman.m4a"
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-loglevel", "error", "-i", str(ses), str(m4a)], check=True)
    ad = f"duman_{int(time.time())}"
    r = subprocess.run([PY, "-u", str(KLASOR / "transkript.py"), str(m4a), "tr", "turbo", "--ozet-yok", "--konusmaci-yok", "--ad", ad],
                       capture_output=True, text=True, timeout=600, cwd=str(KLASOR))
    hatalar = []
    js = KLASOR / f"{ad}.json"
    if not js.exists():
        satirlar = [x for x in (r.stdout + r.stderr).strip().splitlines() if "warn" not in x.lower()]
        hatalar.append("tam: yazıya dökülemedi: " + (satirlar[-1][:200] if satirlar else "çıktı yok"))
    else:
        metin = " ".join(s["metin"] for s in json.loads(js.read_text(encoding="utf-8"))["segmentler"]).lower()
        if not ("deneme" in metin and ("çalışıyor" in metin or "sistem" in metin)):
            hatalar.append(f"tam: beklenen Türkçe kelimeler yok: {metin[:120]}")
    for f in KLASOR.glob(f"{ad}.*"):                       # yalnızca bu testin ürettikleri
        f.unlink(missing_ok=True)
    return hatalar


# ---------------------------------------------------------------- Meet örnek toplantısı (2026-10-25; Ghost oturumunun önerisi, kullanıcı onayladı:
# "konuşmacıları ve kararları bilinen sabit bir örnek toplantı; her değişiklikten sonra işlensin, sonuç kodla kontrol edilsin"). İki konuşmacı: macOS'ta tek
# Türkçe ses (Yelda) var; ikincisi perdesi kalınlaştırılıp (asetrate 0,62 + alçak geçiren) ayrı ses yapılır (benzerlik 0,22; kısa replikler birleşiyordu,
# repliklerin uzunluğu bu yüzden 7-10 sn). Asana'ya, Drive'a, e-postaya hiçbir şey gitmez: yalnız transkript.py ve kisaca.uret; dosyalar silinir.
MEET_ORNEK = [
    ("A", "Merhaba Can, hoş geldin. Bugünkü toplantıda yeni kampanyanın takvimini ve bütçesini konuşalım, sonra kimin ne yapacağını netleştirelim."),
    ("B", "Merhaba Ayşe, teşekkürler. Ben afiş taslağını perşembe gününe kadar hazırlarım. Görselleri de aynı gün paylaşırım, böylece cuma onaylarız."),
    ("A", "Harika. Bütçe konusunda da karar verelim: reklam bütçesini on bin lira olarak sabitliyoruz. Ek harcama olursa önce bana sorulacak."),
    ("B", "Tamam, on bin lirada anlaştık, ek harcama için sana soracağım. Peki sosyal medya metinlerini kim yazacak, onlar da yetişmeli."),
    ("A", "Metinleri ben cuma gününe kadar yazarım. Bir sonraki toplantıyı da pazartesi sabah yapalım, orada son hali gözden geçiririz."),
    ("B", "Anlaştık, pazartesi sabah görüşürüz. Kolay gelsin, görüşmek üzere."),
]


def _meet_ornek_coz():
    """Örnek toplantıyı üretir ve Claude'suz yazıya döker. Döner: (json yolu ya da None, hata metni, silinecek ad)."""
    d = Path(tempfile.mkdtemp(prefix="duman_meet_"))
    ff = "/opt/homebrew/bin/ffmpeg"
    liste = []
    for i, (kim, metin) in enumerate(MEET_ORNEK):
        a = d / f"r{i}.aiff"; w = d / f"r{i}.wav"; s = d / f"s{i}.wav"
        subprocess.run(["say", "-v", "Yelda", "-o", str(a), metin], check=True)
        af = ["-af", "asetrate=22050*0.62,aresample=22050,atempo=1.613,lowpass=f=2600"] if kim == "B" else []
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(a), *af, "-ar", "22050", "-ac", "1", str(w)], check=True)
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-t", "0.8", "-i", "anullsrc=r=22050:cl=mono", str(s)], check=True)
        liste += [f"file '{w}'", f"file '{s}'"]
    (d / "liste.txt").write_text("\n".join(liste), encoding="utf-8")
    m4a = d / "ornek.m4a"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(d / "liste.txt"), "-ac", "1", "-c:a", "aac", str(m4a)], check=True)
    ad = f"duman_meet_{int(time.time())}"
    r = subprocess.run([PY, "-u", str(KLASOR / "transkript.py"), str(m4a), "tr", "turbo", "--ozet-yok", "--claude-yok", "--ad", ad],
                       capture_output=True, text=True, timeout=900, cwd=str(KLASOR))
    shutil.rmtree(d, ignore_errors=True)
    js = KLASOR / f"{ad}.json"
    if not js.exists():
        satirlar = [x for x in (r.stdout + r.stderr).strip().splitlines() if "warn" not in x.lower()]
        return None, "yazıya dökülemedi: " + (satirlar[-1][:200] if satirlar else "çıktı yok"), ad
    return js, "", ad


def _meet_ornek_denetle(d):
    """Claude'suz denetim: konuşmacı sayısı, anahtar sözcükler, kim neyi söyledi."""
    h = []
    segs = d["segmentler"]; etiket = d["veri"]["etiket"]
    metin = " ".join(s["metin"] for s in segs).lower()
    if len(etiket) != 2:
        h.append(f"konuşmacı sayısı {len(etiket)} (beklenen 2)")
    for kelime in ("afiş", "perşembe", "bütçe", "cuma", "pazartesi"):
        if kelime not in metin:
            h.append(f"'{kelime}' yazıda yok")
    if not any(x in metin for x in ("10 bin", "on bin", "10.000")):
        h.append("'on bin lira' yazıda yok")
    kim = lambda soz: next((str(s.get("k")) for s in segs if soz in s["metin"].lower()), None)   # noqa: E731
    if kim("afiş") and kim("cuma gününe kadar yazarım") and kim("afiş") == kim("cuma gününe kadar yazarım"):
        h.append("iki konuşmacının sözleri aynı kişiye yazıldı (afiş / metinler)")
    if kim("merhaba can") and kim("merhaba ayşe") and kim("merhaba can") == kim("merhaba ayşe"):
        h.append("selamlaşma aynı kişiye yazıldı")
    return h


def meet():
    """Meet örnek toplantısı, Claude'suz (~30 sn): yazıya dökme + konuşmacı ayırma. Meet'te bir değişiklikten sonra çalıştırılır."""
    js, hata, ad = _meet_ornek_coz()
    try:
        if not js:
            return ["meet: " + hata]
        return ["meet: " + x for x in _meet_ornek_denetle(json.loads(js.read_text(encoding="utf-8")))]
    finally:
        for f in KLASOR.glob(f"{ad}.*"):
            f.unlink(missing_ok=True)


def meet_kisaca():
    """Meet örnek toplantısı + Kısaca (Claude; gece): kararlar, kim ne yapacak, ne zaman, alıntı kanıtı. Claude yoksa atlanır (hata sayılmaz)."""
    import claude_yaz
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            print("   meet_kisaca: Claude kullanılamadığı için atlandı")
            return []
    js, hata, ad = _meet_ornek_coz()
    try:
        if not js:
            return ["meet_kisaca: " + hata]
        d = json.loads(js.read_text(encoding="utf-8"))
        h = _meet_ornek_denetle(d)
        segs = d["segmentler"]
        k_ayse = next((str(s.get("k")) for s in segs if "merhaba can" in s["metin"].lower()), None)
        d["veri"]["etiket"] = {k: ("Ayşe" if k == k_ayse else "Can") for k in d["veri"]["etiket"]}
        d["veri"].update({"toplanti": True, "baslik": "Kampanya takvimi ve bütçe"})
        import kisaca
        k = kisaca.uret(d["veri"], segs, log=lambda *_: None) or {}
        if not k.get("ozet"):
            return ["meet_kisaca: Kısaca boş"]
        kararlar = " ".join(x.get("karar", "") for x in k.get("kararlar") or []).lower()
        if not ("bütçe" in kararlar and any(x in kararlar for x in ("10", "on bin"))):
            h.append(f"bütçe kararı yok: {kararlar[:120]}")
        isler = {p.get("ad"): " ".join(f"{x.get('is', '')} {x.get('ne_zaman', '')}" for x in p.get("isler") or []).lower() for p in k.get("kisiler") or []}
        if not ("afiş" in isler.get("Can", "") and "perşembe" in isler.get("Can", "")):
            h.append(f"Can'ın işi (afiş, perşembe) yok: {isler.get('Can', '')[:120]}")
        if not ("metin" in isler.get("Ayşe", "") and "cuma" in isler.get("Ayşe", "")):
            h.append(f"Ayşe'nin işi (metinler, cuma) yok: {isler.get('Ayşe', '')[:120]}")
        supheli = [x.get("is") for p in k.get("kisiler") or [] for x in p.get("isler") or [] if x.get("alinti_dogru") is False]
        if supheli:
            h.append(f"transkriptte bulunamayan alıntı: {supheli[:2]}")
        return ["meet_kisaca: " + x for x in h]
    finally:
        for f in KLASOR.glob(f"{ad}.*"):
            f.unlink(missing_ok=True)


def _sure(f):
    r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _srt_denetle(srt, sure):
    """Altyazı dosyası YouTube biçimine uyuyor mu: sıra numaraları, artan ve çakışmayan zamanlar, video süresini aşmama, satır ≤42 karakter, ≤2 satır,
    kart 0,4-7,5 sn. Döner: sorun listesi."""
    sorun, onceki, n = [], 0.0, 0
    bloklar = [b for b in re.split(r"\n\s*\n", srt.strip()) if b.strip()]
    ts = lambda t: sum(float(x) * k for x, k in zip(t.replace(",", ".").split(":"), (3600, 60, 1)))   # noqa: E731
    for b in bloklar:
        satir = b.strip().splitlines()
        n += 1
        m = re.match(r"(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})", satir[1] if len(satir) > 1 else "")
        if not satir[0].strip().isdigit() or int(satir[0]) != n or not m:
            sorun.append(f"{n}. kart biçimi bozuk"); continue
        a, e = ts(m.group(1)), ts(m.group(2))
        if a < onceki - 0.01:
            sorun.append(f"{n}. kart öncekiyle çakışıyor")
        if not 0.4 <= e - a <= 7.5:
            sorun.append(f"{n}. kart süresi {e - a:.1f} sn")
        if e > sure + 0.5:
            sorun.append(f"{n}. kart video süresini aşıyor ({e:.1f} > {sure:.1f})")
        yazi = satir[2:]
        if not yazi or len(yazi) > 2 or any(len(x) > 42 for x in yazi):
            sorun.append(f"{n}. kartta satır sayısı/uzunluğu kurala uymuyor")
        onceki = e
    if not bloklar:
        sorun.append("altyazı dosyası boş")
    elif onceki < sure * 0.6:
        sorun.append(f"altyazı videonun yalnızca {onceki:.0f}/{sure:.0f} saniyesini kapsıyor")
    return sorun[:6]


def studio(dublaj_da=False):
    """Studio'nun asıl zinciri, hep aynı sentetik örnek videoyla (2026-10-25; kullanıcının X yer imlerinden Daniel Lockyer ve Ersin Koç önerileri:
    "ajan kendi işini kontrol etsin", "model değişti, iş kendiliğinden düzelir sanmayın"): yazıya dökme → YouTube altyazısı (biçim kuralları) →
    altyazılı video → klip; dublaj_da=True ise ayrıca kısa dublaj önizlemesi (haftada bir; ağır model). Hiçbir şey kitaplığa ya da indirilenlere
    kalmaz; Claude'a yalnızca transkriptin kendi adımları gider (çeviri sabit örnektir)."""
    d = Path(tempfile.mkdtemp(prefix="duman_studio_"))
    hatalar = []
    ad = f"duman_studio_{int(time.time())}"
    try:
        ses = d / "ornek.aiff"
        subprocess.run(["say", "-v", "Yelda", "-o", str(ses), "Merhaba, bu Studio için hazırlanmış kısa bir deneme videosudur. Önce konuşma yazıya dökülür, "
                        "sonra altyazı kartları hazırlanır. Ardından altyazılı video ve kısa bir klip üretilir. Her adımın sonucu kontrol edilir."], check=True)
        video = d / "ornek.mp4"
        subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x1c2a3a:s=640x360:r=25", "-i", str(ses),
                        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
        sure = _sure(video)
        r = subprocess.run([PY, "-u", str(KLASOR / "transkript.py"), str(video), "tr", "turbo", "--ozet-yok", "--konusmaci-yok", "--ad", ad],
                           capture_output=True, text=True, timeout=900, cwd=str(KLASOR))
        js = KLASOR / f"{ad}.json"
        if not js.exists():
            satirlar = [x for x in (r.stdout + r.stderr).strip().splitlines() if "warn" not in x.lower()]
            return ["studio: yazıya dökülemedi: " + (satirlar[-1][:200] if satirlar else "çıktı yok")]
        veri = json.loads(js.read_text(encoding="utf-8"))
        metin = " ".join(s["metin"] for s in veri["segmentler"]).lower()
        if not all(k in metin.replace(" ", "") for k in ("deneme", "altyazı", "klip")):   # "alt yazı" da olur
            hatalar.append(f"studio: transkriptte beklenen kelimeler yok: {metin[:120]}")
        srt = KLASOR / f"{ad}.srt"
        hatalar += [f"studio altyazı: {x}" for x in (_srt_denetle(srt.read_text(encoding="utf-8"), sure) if srt.exists() else ["altyazı dosyası oluşmadı"])]
        for etiket, ek, beklenen in (("altyazılı video", [], sure), ("klip", ["--kesit", "0:02-0:07"], 5.0)):
            cikti = d / f"{etiket.split()[0]}.mp4"
            r = subprocess.run([PY, "-u", str(KLASOR / "yakma.py"), str(js), "--video", str(video), "--cikti", str(cikti), *ek],
                               capture_output=True, text=True, timeout=600, cwd=str(KLASOR))
            if not cikti.exists() or cikti.stat().st_size < 10000:
                son = [x for x in (r.stdout + r.stderr).strip().splitlines() if x.strip()]
                hatalar.append(f"studio {etiket}: oluşmadı ({(son[-1] if son else 'çıktı yok')[:120]})")
            elif abs(_sure(cikti) - beklenen) > 1.2:
                hatalar.append(f"studio {etiket}: süre {_sure(cikti):.1f} sn, beklenen {beklenen:.1f} sn")
        seg = veri["segmentler"]                          # metinden kesme: ortadaki cümle çıkarılır, kenarlar sese oturtulmalı
        if len(seg) >= 3:
            tut = [(0.0, seg[0]["bit"] + 0.05), (seg[-1]["bas"] - 0.05, sure)]
            cikti = d / "kesim.mp4"
            r = subprocess.run([PY, "-u", str(KLASOR / "yakma.py"), str(js), "--video", str(video), "--cikti", str(cikti), "--altyazisiz",
                                "--tut", ",".join(f"{a:.2f}-{b:.2f}" for a, b in tut)], capture_output=True, text=True, timeout=600, cwd=str(KLASOR))
            beklenen = sum(b - a for a, b in tut)
            if not cikti.exists():
                son = [x for x in (r.stdout + r.stderr).strip().splitlines() if x.strip()]
                hatalar.append(f"studio kesim: oluşmadı ({(son[-1] if son else 'çıktı yok')[:120]})")
            elif abs(_sure(cikti) - beklenen) > 1.2:
                hatalar.append(f"studio kesim: süre {_sure(cikti):.1f} sn, beklenen {beklenen:.1f} sn")
            elif "sese oturtuldu" not in r.stdout:
                hatalar.append("studio kesim: kesim kenarları sese oturtulmadı")
        if dublaj_da:
            veri["veri"]["ceviriler"] = {"en": {"segmentler": ["This is a short test sentence for the dubbing check."] * len(veri["segmentler"]),
                                                "ozet": {}, "model": "duman", "tarih": time.strftime("%Y-%m-%d")}}
            js.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
            cikti = d / "dublaj.mp4"
            r = subprocess.run([PY, "-u", str(KLASOR / "dublaj.py"), str(js), "--dil", "en", "--video", str(video), "--cikti", str(cikti), "--onizleme", "8"],
                               capture_output=True, text=True, timeout=1800, cwd=str(KLASOR))
            if not cikti.exists():
                son = [x for x in (r.stdout + r.stderr).strip().splitlines() if x.strip()]
                hatalar.append(f"studio dublaj: oluşmadı ({(son[-1] if son else 'çıktı yok')[:120]})")
            else:
                v = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-i", str(cikti), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
                m = re.search(r"mean_volume: (-?[\d.]+) dB", v)
                if not m or float(m.group(1)) < -50:
                    hatalar.append("studio dublaj: ses yok ya da sessiz")
    except subprocess.TimeoutExpired as e:
        hatalar.append(f"studio: zaman aşımı ({Path(str(e.cmd[2] if len(e.cmd) > 2 else '')).name})")
    finally:
        for f in KLASOR.glob(f"{ad}*"):                    # yalnızca bu testin ürettikleri
            if f.is_file():
                f.unlink(missing_ok=True)
        shutil.rmtree(d, ignore_errors=True)
    return hatalar


def studio_dublaj():
    return studio(dublaj_da=True)


def calistir(katmanlar=("hizli", "birim")):
    sonuc = {"zaman": time.time(), "katmanlar": list(katmanlar), "hatalar": {}}
    for k in katmanlar:
        try:
            sonuc["hatalar"][k] = globals()[k]()
        except Exception:  # noqa: BLE001
            sonuc["hatalar"][k] = ["çalıştırılamadı: " + traceback.format_exc().strip().splitlines()[-1][:200]]
    sonuc["basarili"] = not any(sonuc["hatalar"].values())
    try:
        onceki = json.loads(SONUC.read_text(encoding="utf-8")) if SONUC.exists() else {}
        onceki.update({k: {"zaman": sonuc["zaman"], "hatalar": v} for k, v in sonuc["hatalar"].items()})
        SONUC.write_text(json.dumps(onceki, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return sonuc


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "hepsi"
    katman = ("hizli", "birim", "canli", "tam") if arg == "hepsi" else tuple(arg.split(","))
    s = calistir(katman)
    for k, h in s["hatalar"].items():
        print(f"{'✓' if not h else '✗'} {k}" + ("" if not h else "\n   " + "\n   ".join(h)))
    raise SystemExit(0 if s["basarili"] else 1)

# sunucu/23_misafir_meet.py — Meet davetlileri (2026-10-24; kullanıcı: "Meet için de bu linki kapalı bir grup olan başka arkadaşlarım da deneyebilmeli.
# Komple public gibi düşünme. Sadece linke sahip olan, belirleyeceğimiz sayıdaki kısıtlı sayıda kişi.")
# Studio'nun davet kapısının (22_misafir.py) üstüne kurulur: AYNI davet listesi, kişi başı ürün izni (`urunler`: studio, meet), kişi sınırı Ayarlar'dan
# (`misafir_kisi`). Davetlinin toplantısı YALITILMIŞ akıştan geçer (`_misafir_toplanti_bitir`): kayıt ve dosyalar `kayitlar/misafir/<id>/`; transkript,
# Kısaca, başlık, danışman notu (davetlinin kendi geçmişi), sesli özet. Drive, Asana, e-postayla notlar, takvim, şirket/müşteri sınıflaması, sinyaller,
# karar zinciri, sahibin tanınan sesleri, Couple, Ghost, canlı yazıya dökme ve kaydedici davetliye YOK. Claude yalnız davetlinin kendi anahtarıyla.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
import claude_yaz

MEET_MISAFIR = {"en_uzun_sn": 2 * 3600, "kayit_gb": 1.5}     # toplantılar videolardan uzun: 2 saat; tarayıcı kaydı en çok 1,5 GB
URUN_ADLARI = ("studio", "meet")
MEET_IZINLI = {
    ("POST", "/api/misafir/toplanti/baslat"): None, ("POST", "/api/misafir/toplanti/<kid>/parca"): None, ("POST", "/api/misafir/toplanti/<kid>/bitir"): None,
    ("POST", "/api/misafir/toplanti/yukle"): None,
    ("POST", "/api/kisaca/<temel>"): "temel", ("GET", "/api/kisaca-durum/<temel>"): "temel", ("POST", "/api/kisaca/<temel>/is"): "temel",
    ("POST", "/api/danisman/<temel>"): "temel", ("GET", "/api/danisman-durum/<temel>"): "temel",
    ("POST", "/api/sesli-ozet/<temel>"): "temel", ("GET", "/sesli-ozet/<temel>.m4a"): "temel",
    ("GET", "/api/meet/ses/<temel>/<k>.m4a"): "temel", ("GET", "/api/meet/toplanti/<temel>"): "temel",
}
IZINLI.update(MEET_IZINLI)
STUDIO_YENI = {("POST", "/api/baslat"), ("POST", "/api/yukle"), ("GET", "/api/onizle")}     # yeni video: yalnız Studio izni olana

try:                                                          # kişi sınırını sahip belirler (Ayarlar → Davetler)
    MISAFIR_SINIR["kisi"] = max(1, min(30, int(ayarlar_oku().get("misafir_kisi") or MISAFIR_SINIR["kisi"])))
except Exception:  # noqa: BLE001
    pass


def _urunler(kisi):
    u = (kisi or {}).get("urunler")
    u = [x for x in u if x in URUN_ADLARI] if isinstance(u, list) else ["studio"]     # eski davetler yalnız Studio içindi
    return u or ["studio"]


def _sahip_ilk_ad():
    return ((ayarlar_oku().get("benim_adim") or "").strip().split(" ") or [""])[0]


# ---------------------------------------------------------------------------- davetliye giden sayfadan sahibin adları
_HARF = "A-Za-z0-9_çğıöşüÇĞİÖŞÜâîû"


_gizli_onb = {"t": 0, "L": []}


def _gizli_adlar():
    if time.time() - _gizli_onb["t"] < 600:
        return _gizli_onb["L"]
    _gizli_onb.update(t=time.time(), L=_gizli_adlar_hesapla())
    return _gizli_onb["L"]


def _gizli_adlar_hesapla():
    """Davetli sayfasının kaynağında geçmemesi gereken adlar: şirketler, müşteriler/markalar, tanıma sözcükleri, görüşülen kişiler, tanınan sesler.
    Sahibin kendi adı kalır (davetli onu zaten tanıyor; sayfada 'kayıtlar X'in bilgisayarında' denir)."""
    ay = ayarlar_oku(); ad = set()
    for sk in ay.get("sirketler") or []:
        if isinstance(sk, dict):
            ad |= {sk.get("ad") or ""} | set(sk.get("musteriler") or []) | set(sk.get("anahtar") or [])
    ad |= set(ay.get("musteriler") or [])
    for m, ks in (ay.get("musteri_kisiler") or {}).items():
        ad |= {m} | {k for k in ks if not str(k).startswith("@")}
    try:
        import sesler as sesler_modulu
        ad |= set(sesler_modulu.oku())
    except Exception:  # noqa: BLE001
        pass
    try:                                                      # toplantılarda görüşülen kişiler (kişi profilleri)
        import kisiler as kisiler_modulu
        ad |= {str(k.get("ad") or "") for k in kisiler_modulu.liste() if isinstance(k, dict)}
    except Exception:  # noqa: BLE001
        pass
    for _js, v, _s in meet_gelisim.toplantilar(365):          # toplantılardaki adlar ve ad önerileri
        ad |= {str(a) for a in (v.get("etiket") or {}).values() if not meet_gelisim.ADSIZ.match(str(a))} | {str(a) for a in v.get("katilimcilar") or []}
        ad |= {str(o.get("ad") or "") for o in v.get("ad_onerileri") or [] if isinstance(o, dict)}
    ad |= {a.split()[0] for a in list(ad) if len(a.split()) > 1}           # 'Ayşe Demir' → 'Ayşe' de
    ben = {w.casefold() for w in str(ay.get("benim_adim") or "").split()} | {w.casefold() for p_ in (meet_gelisim.ben_tam_ad(),) for w in str(p_ or "").split()}
    ad = {a.strip() for a in ad if a and len(a.strip()) >= 4 and not {w.casefold() for w in a.split()} <= ben}
    return sorted(ad, key=len, reverse=True)


def _sayfa_temizle(html):
    """Sayfa kodundaki örnek ve açıklamalardan müşteri/kişi adları ve e-posta adresleri çıkar (görünür arayüz bunları zaten göstermez)."""
    html = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+\.[A-Za-z0-9.\-]+", "ornek@alan.com", html)
    adlar = _gizli_adlar()
    if adlar:
        desen = re.compile(rf"(?<![{_HARF}])(" + "|".join(re.escape(a) for a in adlar) + rf")(?![{_HARF}])")
        html = desen.sub("Müşteri", html)
    return html


# ---------------------------------------------------------------------------- kapı: ürün izni (Studio'nun kapısından SONRA çalışır)
@app.before_request
def _misafir_meet_kapisi():
    if not _misafir_istek():
        return None
    yol = request.path
    if yol.startswith("/d/") or yol.startswith("/static/"):           # ham .html engeli Studio'nun kapısında (22; 2026-10-25)
        return None
    kisi = _kisi_token(request.cookies.get("vh_misafir", ""))
    if not kisi:
        return None                                           # Studio'nun kapısı zaten reddetti
    kural = request.url_rule.rule if request.url_rule else ""
    k = ("GET" if request.method == "HEAD" else request.method, kural)
    u = _urunler(kisi)
    if k in MEET_IZINLI and "meet" not in u:
        return _red(403, "Meet bu davette kapalı.")
    if k in STUDIO_YENI and "studio" not in u:
        return _red(403, "Studio bu davette kapalı.")
    return None


# ---------------------------------------------------------------------------- sayfa: ürüne göre
_misafir_ana_studio = _misafir_ana


def _misafir_ana(kisi):   # noqa: F811 — Meet izni olan davetli: /?u=meet (ya da yalnız Meet izni varsa /) Meet'i açar
    u = _urunler(kisi)
    meet = "meet" in u and (request.args.get("u") == "meet" or "studio" not in u)
    ek = (f'<script>window.MISAFIR_URUNLER = {json.dumps(u)}; window.MISAFIR_SAHIP = {json.dumps(_sahip_ilk_ad(), ensure_ascii=False)};</script>'
          '<script src="/static/misafir_meet.js?v=3"></script>')
    if not meet:
        r = _misafir_ana_studio(kisi)
        r.set_data(_sayfa_temizle(r.get_data(as_text=True).replace("</body>", ek + "</body>", 1)))
        return r
    html = _sayfa_temizle((Path(app.static_folder) / "index.html").read_text(encoding="utf-8"))   # önce temizle: davetlinin kendi adı değişmesin
    html = html.replace("<html", '<html data-urun="note" data-misafir="1"', 1)
    html = html.replace("</body>", f'<script>window.MISAFIR = {json.dumps({"ad": kisi.get("ad") or ""}, ensure_ascii=False)};</script>'
                        '<script src="/static/misafir.js?v=1"></script>' + ek + "</body>", 1)
    r = make_response(html)
    r.headers["Cache-Control"] = "no-store"
    return r


def _misafir_toplanti_satirlari(gid):
    """Davetlinin toplantıları `toplanti_<id>_*.json` adını taşır: sahibin bütün taramaları (kitaplık, sözler, kişiler, hazırlık notu, şirket yorumu,
    haftalık özet, Couple, arama) yalnız `transkript_*.json`'a baktığı için bunlar sahibe hiç karışmaz; davetlinin kendi listesine buradan eklenir."""
    out = []
    for js in KLASOR.glob(f"toplanti_{re.sub(r'[^a-f0-9]', '', gid)}_*.json"):
        try:
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        if v.get("misafir") != gid:
            continue
        ks = v.get("kisaca") or {}
        kisa = (ks.get("ozet") or [""])[0] or ((v.get("ozet") or {}).get("ozet") if isinstance(v.get("ozet"), dict) else "") or ""
        out.append({"temel": js.stem, "baslik": v.get("baslik") or js.stem, "sure": v.get("sure", 0), "dil": v.get("dil", ""), "konusmacilar": v.get("etiket", {}),
                    "kapak": "", "toplanti": True, "misafir": gid, "uygulama": v.get("uygulama", ""), "katilimcilar": [], "musteri": "", "sirket": "",
                    "ozet": bool(v.get("ozet")), "kisa": kisa[:260], "danisman": bool(v.get("danisman")), "sesli_ozet": (v.get("sesli_ozet") or {}).get("sn") or 0,
                    "adsiz": len([a for a in (v.get("etiket") or {}).values() if str(a).startswith("Konuşmacı ")]),
                    "acik_is": sum(1 for k in ks.get("kisiler") or [] for x in k.get("isler") or [] if not x.get("bitti")), "benim_is": 0,
                    "olusturma": v.get("olusturma") or js.stat().st_mtime, "docx": js.with_suffix(".docx").exists(), "txt": js.with_suffix(".txt").exists(),
                    "uyari": 0, "ceviriler": [], "koleksiyonlar": [], "drive": "", "onay_bekliyor": False})
    return out


@app.after_request
def _misafir_meet_sonra(yanit):
    try:
        if _misafir_istek() and request.path == "/api/gecmis" and yanit.status_code == 200 and _gid():
            L = yanit.get_json(silent=True)
            if isinstance(L, list):
                L = sorted(L + _misafir_toplanti_satirlari(_gid()), key=lambda x: -(x.get("olusturma") or 0))
                yanit.set_data(json.dumps(L, ensure_ascii=False)); yanit.headers["Content-Length"] = str(len(yanit.get_data()))
        elif _misafir_istek() and request.path.startswith("/d/") and request.args.get("u") == "meet" and yanit.status_code in (301, 302, 303):
            yanit.headers["Location"] = "/?u=meet"                 # Meet davet linki doğrudan Meet'i açar
        elif not _misafir_istek() and request.path == "/api/davetler" and request.method == "GET" and yanit.status_code == 200:
            d = yanit.get_json(silent=True) or {}
            U = {k["id"]: _urunler(k) for k in _davetler()["kisiler"]}
            for k in d.get("kisiler") or []:
                k["urunler"] = U.get(k["id"], ["studio"])
                k["meet_link"] = (k["link"] + "?u=meet") if k.get("link") and "meet" in k["urunler"] else ""
            d["sinir"] = {**(d.get("sinir") or {}), "kisi": MISAFIR_SINIR["kisi"], "meet_en_uzun_sn": MEET_MISAFIR["en_uzun_sn"]}
            yanit.set_data(json.dumps(d, ensure_ascii=False)); yanit.headers["Content-Length"] = str(len(yanit.get_data()))
    except Exception as e:  # noqa: BLE001
        print(f"Meet davet süzgeci: {e}", flush=True)
    return yanit


# ---------------------------------------------------------------------------- davetlinin toplantı kaydı (kendi klasöründe)
def _misafir_kayit_dizini(gid):
    """kayitlar/misafir/<id>/: iş başlatıcı yalnız kayitlar/ altındaki yerel dosyayı kabul eder; sahibin taramaları (canlı yazıya dökme, meşgul
    denetimi, kaydedici) yalnız kayitlar/'ın kendisine bakar, alt klasöre inmez."""
    p = KAYIT / "misafir" / re.sub(r"[^a-f0-9]", "", gid)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _misafir_hak(kisi):
    if _bugun_sayisi(kisi) >= MISAFIR_SINIR["gunluk"]:
        return _red(429, f"Bugünlük {MISAFIR_SINIR['gunluk']} kayıt hakkınız doldu; yarın yeniden deneyebilirsiniz.")
    if not _disk_yeter():
        return _red(507, "Şu an yer yok; daha sonra deneyin.")
    return None


def _ses_suresi(yol):
    try:
        r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(yol)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _misafir_toplanti_isi(kisi, kaynak, baslik, bas, uygulama):
    """Kaynak sesi m4a'ya çevirir, süreyi denetler, toplantı işini (davetli bağlamında) kuyruğa koyar. Döner: Flask yanıtı."""
    gid = kisi["id"]; dz = _misafir_kayit_dizini(gid)
    zaman = time.strftime("%Y-%m-%d %H.%M", time.localtime(bas))
    m4a = dz / f"Toplanti {zaman}.m4a"; n = 2
    while m4a.exists():
        m4a = dz / f"Toplanti {zaman} ({n}).m4a"; n += 1
    p = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-i", str(kaynak), "-vn", "-c:a", "aac", "-b:a", "96k", str(m4a)],
                       capture_output=True, text=True, timeout=3600)
    Path(kaynak).unlink(missing_ok=True)
    if p.returncode != 0 or not m4a.exists():
        return _red(500, "Kayıt dosyası dönüştürülemedi.")
    sure = _ses_suresi(m4a)
    if sure < 20:
        m4a.unlink(missing_ok=True)
        return _red(400, "Kayıt çok kısa ya da okunamadı.")
    if sure > MEET_MISAFIR["en_uzun_sn"]:
        m4a.unlink(missing_ok=True)
        return _red(400, f"Davetli kullanımda en çok {MEET_MISAFIR['en_uzun_sn'] // 60} dakikalık toplantılar işlenebilir.")
    hata = _misafir_hak(kisi)
    if hata:
        m4a.unlink(missing_ok=True)
        return hata
    r = _baslat({"link": str(m4a), "ozet": True, "konusmaci": True, "altyazi": False, "toplanti": True, "toplanti_baslik": baslik,
                 "kayit_dosya": str(m4a), "kayit_baslangic": bas, "uygulama": uygulama, "sure": sure,
                 "ad": f"toplanti_{gid}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(bas))}"})
    if isinstance(r, tuple):                                   # _baslat hata verdi (yanıt, kod)
        m4a.unlink(missing_ok=True)
        return r
    j = r.get_json() if hasattr(r, "get_json") else {}
    if j.get("id"):
        _say(gid)
        if isler.get(j["id"]):
            isler[j["id"]]["misafir"] = gid; isler[j["id"]]["baslik"] = baslik or f"Toplantı {zaman}"
    return jsonify({"id": j.get("id"), "hata": j.get("hata")})


def _misafir_kisi_simdi():
    if not _misafir_istek():
        abort(404)
    kisi = _kisi(_gid())
    if not kisi or "meet" not in _urunler(kisi):
        abort(403)
    return kisi


@app.post("/api/misafir/toplanti/baslat")
def misafir_toplanti_baslat():
    kisi = _misafir_kisi_simdi()
    hata = _misafir_hak(kisi)
    if hata:
        return hata
    v = request.get_json(silent=True) or {}
    dz = _misafir_kayit_dizini(kisi["id"])
    for eski in dz.glob("*.webm"):                            # yarım kalmış boş kayıtlar
        if time.time() - eski.stat().st_mtime > 6 * 3600:
            eski.unlink(missing_ok=True); eski.with_suffix(".json").unlink(missing_ok=True)
    acik = [x for x in dz.glob("*.webm") if time.time() - x.stat().st_mtime < 6 * 3600]
    if len(acik) >= 1:                                        # aynı anda tek açık kayıt (2026-10-27 incelemesi: sınırsız açılıp disk doldurulabilirdi)
        return _red(429, "Zaten süren bir kaydınız var; önce onu bitirin.")
    if shutil.disk_usage(str(KAYIT)).free < 10 * 1024 ** 3:
        return _red(507, "Bilgisayarda yer kalmadı; şu an kayıt alınamıyor.")
    kid = uuid.uuid4().hex[:8]
    (dz / f"{kid}.webm").write_bytes(b"")
    (dz / f"{kid}.json").write_text(json.dumps({"baslik": str(v.get("baslik") or "")[:120], "baslangic": time.time()}, ensure_ascii=False), encoding="utf-8")
    return jsonify({"id": kid})


def _misafir_kid(kisi, kid):
    if not re.match(r"^[0-9a-f]{8}$", kid):
        abort(404)
    p = _misafir_kayit_dizini(kisi["id"]) / f"{kid}.webm"
    if not p.exists():
        abort(404)
    return p


@app.post("/api/misafir/toplanti/<kid>/parca")
def misafir_toplanti_parca(kid):
    kisi = _misafir_kisi_simdi()
    p = _misafir_kid(kisi, kid)
    if (request.content_length or 0) > 64 * 1024 ** 2 or p.stat().st_size + (request.content_length or 0) > MEET_MISAFIR["kayit_gb"] * 1e9:
        return _red(413, "Kayıt çok büyüdü; durdurup yazıya dökün.")   # gövde belleğe okunmadan (en çok 4 GB) reddedilir
    if shutil.disk_usage(str(KAYIT)).free < 5 * 1024 ** 3:
        return _red(507, "Bilgisayarda yer kalmadı; kaydı durdurup yazıya dökün.")
    veri = request.get_data()
    if p.stat().st_size + len(veri) > MEET_MISAFIR["kayit_gb"] * 1e9:
        return _red(413, "Kayıt çok büyüdü; durdurup yazıya dökün.")
    with open(p, "ab") as f:
        f.write(veri)
    return jsonify({"tamam": True, "boyut": p.stat().st_size})


@app.post("/api/misafir/toplanti/<kid>/bitir")
def misafir_toplanti_bitir(kid):
    kisi = _misafir_kisi_simdi()
    p = _misafir_kid(kisi, kid)
    v = request.get_json(silent=True) or {}
    try:
        meta = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        meta = {}
    p.with_suffix(".json").unlink(missing_ok=True)
    if p.stat().st_size < 1000:
        p.unlink(missing_ok=True)
        return _red(400, "Kayıt boş görünüyor; mikrofon izni verilmemiş olabilir.")
    baslik = re.sub(r"[/\\:]+", " ", str(v.get("baslik") or meta.get("baslik") or "")).strip()[:80]
    return _misafir_toplanti_isi(kisi, p, baslik, float(meta.get("baslangic") or time.time()), "Tarayıcı")


@app.post("/api/misafir/toplanti/yukle")
def misafir_toplanti_yukle():
    kisi = _misafir_kisi_simdi()
    if (request.content_length or 0) > MISAFIR_SINIR["yukleme_gb"] * 1e9:
        return _red(413, f"Dosya en çok {MISAFIR_SINIR['yukleme_gb']} GB olabilir.")
    hata = _misafir_hak(kisi)
    if hata:
        return hata
    f = request.files.get("dosya")
    if not f:
        return _red(400, "Dosya gelmedi.")
    ad = re.sub(r"[^\w.\- ]+", "_", Path(f.filename or "kayit.m4a").name)[:80]
    if not re.search(r"\.(m4a|mp3|wav|aac|caf|amr|3gp|ogg|opus|webm|flac|aiff?|mp4|mov|qta|m4v)$", ad, re.I):
        return _red(400, "Bu bir ses ya da video dosyasına benzemiyor.")
    gecici = _misafir_kayit_dizini(kisi["id"]) / f".yukleme_{uuid.uuid4().hex[:6]}_{ad}"
    f.save(str(gecici))
    sure = _ses_suresi(gecici)
    try:
        bas = float(request.values.get("zaman_ipucu")) - sure if request.values.get("zaman_ipucu") else time.time() - sure
    except ValueError:
        bas = time.time() - sure
    baslik = re.sub(r"[/\\:]+", " ", str(request.values.get("baslik") or "")).strip()[:80]
    return _misafir_toplanti_isi(kisi, gecici, baslik, min(bas, time.time()), "Dosya")


# ---------------------------------------------------------------------------- yalıtılmış toplantı sonrası akış
_toplanti_bitir_sahip = _toplanti_bitir


def _toplanti_bitir(is_):   # noqa: F811 — davetlinin toplantısı sahibin akışına (Drive, Asana, e-posta, şirketler...) GİRMEZ
    gid = is_.get("misafir") or _temel_sahibi(is_.get("temel"))
    if gid:
        return _misafir_toplanti_bitir(is_, gid)
    return _toplanti_bitir_sahip(is_)


def _misafir_toplanti_bitir(is_, gid):
    temel = is_["temel"]; js = KLASOR / f"{temel}.json"
    kisi = _kisi(gid)
    jeton = claude_yaz.MISAFIR.set(_baglam(kisi) if kisi else {"id": gid, "ad": "", "anahtar": ""})
    log = lambda m: is_["log"].append(m)  # noqa: E731
    toplanti_bitiren.add(temel)
    try:
        with claude_yaz.toplanti():
            d = json.loads(js.read_text(encoding="utf-8")); veri = d["veri"]
            import copy
            ilk = copy.deepcopy(veri)
            veri["misafir"] = gid                             # güvence: kayıt davetlinindir
            try:
                import kisaca
                k = kisaca.uret(veri, d["segmentler"], log=log)
                if k:
                    veri["kisaca"] = k
            except Exception as e:  # noqa: BLE001
                log(f"      Kısa özet hazırlanamadı ({e})")
            zaman = time.strftime("%Y-%m-%d %H.%M", time.localtime(is_.get("kayit_baslangic") or is_.get("olusturma") or time.time()))
            konu = _toplanti_adi_temizle(is_.get("toplanti_baslik") or "")
            if konu:
                veri["baslik_kaynak"] = "elle"
            else:
                konu = _toplanti_baslik(veri) or "Toplantı"; veri["baslik_kaynak"] = "tahmin"
            veri.update({"baslik": f"{zaman} · {konu}", "toplanti": True, "kayit": is_.get("kayit_dosya") or "", "uygulama": is_.get("uygulama") or "",
                         "musteri": "", "sirket": ""})
            try:
                import danisman
                dn = danisman.uret(veri, d["segmentler"], log=log)
                if dn:
                    veri["danisman"] = dn
            except Exception as e:  # noqa: BLE001
                log(f"      Danışman notu hazırlanamadı ({e})")
            d["segmentler"] = _meet_kaydet(temel, veri, ilk)
            try:
                import sesli_ozet
                yol, sn = sesli_ozet.uret(temel, veri)
                if yol:
                    veri["sesli_ozet"] = {"dosya": yol.name, "sn": sn, "zaman": time.time()}
                    _meet_kaydet(temel, veri, ilk, cikti=False)
            except Exception as e:  # noqa: BLE001
                log(f"      Sesli özet hazırlanamadı ({e})")
        is_["baslik"] = veri["baslik"]; is_["drive"] = ""
        _kaydet()
    finally:
        toplanti_bitiren.discard(temel)
        claude_yaz.MISAFIR.reset(jeton)


# ---------------------------------------------------------------------------- sahibin uçları: ürün izni, kişi sınırı, Meet daveti
@app.post("/api/davetler/<gid>/urunler")
def davetler_urunler(gid):
    if _misafir_istek():
        abort(403)
    v = request.get_json(silent=True) or {}
    u = [x for x in URUN_ADLARI if v.get(x)]
    if not u:
        return _red(400, "En az bir ürün açık kalmalı; kimseyi davet etmek istemiyorsanız kaldırın.")
    with _davet_kilit:
        d = _davetler()
        k = next((x for x in d["kisiler"] if x["id"] == gid), None)
        if not k:
            return _red()
        k["urunler"] = u
        _davet_yaz(d)
    return jsonify({"tamam": True, "urunler": u})


@app.post("/api/davetler/sinir")
def davetler_sinir():
    if _misafir_istek():
        abort(403)
    try:
        n = max(1, min(30, int((request.get_json(silent=True) or {}).get("kisi"))))
    except (TypeError, ValueError):
        return _red(400, "Bir sayı girin.")
    aktif = sum(1 for k in _davetler()["kisiler"] if k.get("aktif"))
    if n < aktif:
        return _red(400, f"Şu an {aktif} kişi davetli; sınırı düşürmeden önce birini durdurun ya da kaldırın.")
    ay = ayarlar_oku(); ay["misafir_kisi"] = n; ayarlar_yaz(ay)
    MISAFIR_SINIR["kisi"] = n
    return jsonify({"tamam": True, "kisi": n})


@app.post("/api/davetler/meet")
def davetler_meet():
    """Meet'ten davet: kişi yalnız Meet izniyle oluşturulur (Studio'nun davet ucuyla aynı kurallar: kişi sınırı, tek seferlik link)."""
    if _misafir_istek():
        abort(403)
    v = request.get_json(silent=True) or {}
    with app.test_request_context("/api/davetler", method="POST", json={"ad": v.get("ad")}):
        r = davetler_post()
    if isinstance(r, tuple):
        return r
    j = r.get_json() or {}
    gid = (j.get("kisi") or {}).get("id")
    if gid:
        with _davet_kilit:
            d = _davetler()
            for k in d["kisiler"]:
                if k["id"] == gid:
                    k["urunler"] = ["meet"]
            _davet_yaz(d)
        if j["kisi"].get("link"):
            j["kisi"]["meet_link"] = j["kisi"]["link"] + "?u=meet"
        j["kisi"]["urunler"] = ["meet"]
    return jsonify(j)

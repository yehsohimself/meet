# sunucu/12_api.py — erişim PIN'i, önizleme, yükleme, başlatma, işler, geçmiş, sesler, segment, çeviri, klipler.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- ağ paylaşımında PIN (2026-10-19)
_giris_hata = {}


def _pin_iz(pin):
    import hashlib
    return hashlib.sha256(("video-hub|" + pin).encode()).hexdigest()[:32]


@app.before_request
def _erisim_kontrol():
    """Ağ paylaşımı açıkken başka cihazlar PIN ister (Ayarlar → Paylaşım → Erişim PIN'i). Bu Mac'ten (127.0.0.1) gelen istekler,
    Chrome uzantısı ve kaydedici dahil, hiç etkilenmez. PIN yoksa eski davranış (herkese açık)."""
    ra = request.remote_addr or ""
    if ra in ("127.0.0.1", "::1") or ra.startswith("::ffff:127.") or request.path in ("/giris", "/ping", "/manifest.webmanifest") \
            or request.path.startswith("/static/ikon"):
        return None
    pin = ayarlar_oku().get("erisim_pin") or ""
    if not pin or request.cookies.get("vh_giris") == _pin_iz(pin):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"hata": "Giriş gerekli"}), 401
    import urllib.parse as _up
    return redirect("/giris?devam=" + _up.quote(request.full_path))


@app.route("/giris", methods=["GET", "POST"])
def giris():
    import html as _h
    devam = request.values.get("devam") or "/"
    if not devam.startswith("/") or devam.startswith("//"):
        devam = "/"
    hata = ""
    ra = request.remote_addr or "?"
    kilit_ = _giris_hata.get(ra, (0, 0))
    if request.method == "POST":
        if kilit_[0] >= 8 and time.time() - kilit_[1] < 600:
            hata = "Çok fazla hatalı deneme; 10 dakika sonra tekrar deneyin."
        elif (request.form.get("pin") or "").strip() == (ayarlar_oku().get("erisim_pin") or "") and ayarlar_oku().get("erisim_pin"):
            _giris_hata.pop(ra, None)
            r = make_response(redirect(devam))
            r.set_cookie("vh_giris", _pin_iz(ayarlar_oku()["erisim_pin"]), max_age=365 * 86400, httponly=True, samesite="Lax")
            return r
        else:
            _giris_hata[ra] = (kilit_[0] + 1, time.time()); hata = "PIN yanlış."
    return (f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video Hub</title><style>body{{font-family:-apple-system,Manrope,sans-serif;background:#F7F7F5;color:#1C1C1E;display:grid;place-items:center;
min-height:100vh;margin:0}}@media (prefers-color-scheme:dark){{body{{background:#0E0E11;color:#eee}}}}form{{display:flex;flex-direction:column;gap:12px;
width:260px}}input{{font-size:22px;letter-spacing:6px;text-align:center;padding:12px;border-radius:12px;border:1px solid #ccc}}button{{padding:12px;
border-radius:12px;border:0;background:#3B63E6;color:#fff;font-size:16px}}p{{margin:0;text-align:center}}</style></head><body>
<form method="post"><p><b>Studio</b></p><p>Bu cihazdan girmek için PIN’i yazın.</p>
<input name="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="8" autofocus>
<input type="hidden" name="devam" value="{_h.escape(devam)}"><button>Giriş</button>{f'<p style="color:#d33">{_h.escape(hata)}</p>' if hata else ''}</form></body></html>""")


@app.get("/ping")
def ping():
    return "ok"


def _mevcut_indirme(link):
    """Aynı link daha önce indirildiyse dosya adlarını döner (kalite etiketiyle)."""
    sonuc = []
    for ad, d in _dizin_oku().items():
        if d.get("link") == link and (INDIRILENLER / ad).is_file():
            sonuc.append({"ad": ad, "kalite": d.get("kalite", ""), "kesit": d.get("kesit", ""), "tarih": d.get("olusturma", 0)})
    return sonuc


MODEL_REPO = {"turbo": "mlx-community/whisper-large-v3-turbo", "best": "mlx-community/whisper-large-v3-mlx"}
model_iniyor = {}


@app.post("/api/model-indir")
def model_indir():
    """Ses modelini şimdiden indirir (ilk iş beklemesin)."""
    m = (request.get_json(silent=True) or {}).get("model", "turbo")
    if m not in MODEL_REPO:
        abort(400)
    if _model_var(m):
        return jsonify({"tamam": True, "zaten": True})
    if model_iniyor.get(m):
        return jsonify({"tamam": True, "iniyor": True})
    model_iniyor[m] = True

    def _in():
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(MODEL_REPO[m])
        except Exception:  # noqa: BLE001
            pass
        model_iniyor[m] = False
    threading.Thread(target=_in, daemon=True).start()
    return jsonify({"tamam": True, "iniyor": True})


def _kaliteler(formatlar_json, sure):
    """yt-dlp format listesinden seçenek → yaklaşık MB (ve 'en' için yükseklik). Bilgi yoksa None."""
    try:
        fl = json.loads(formatlar_json) if formatlar_json and formatlar_json != "NA" else []
    except Exception:  # noqa: BLE001
        fl = []
    if not isinstance(fl, list) or not fl:
        return None

    def boyut(f):
        b = f.get("filesize") or f.get("filesize_approx")
        if not b and f.get("tbr") and sure:
            b = f["tbr"] * 1000 / 8 * sure
        return b or 0

    video = [f for f in fl if f.get("height") and (f.get("vcodec") or "none") != "none" and f.get("ext") != "mhtml"]
    ses = [f for f in fl if (f.get("vcodec") or "none") == "none" and (f.get("acodec") or "none") != "none"]
    ses_mb = max((boyut(f) for f in ses), default=0) / 1e6
    if ses_mb > 40 and sure:            # abartılı tahminleri 128 kbps'e çek
        ses_mb = 128000 / 8 * sure / 1e6
    if not video:
        return {"mp3": round(ses_mb, 1) if ses_mb else None} if ses else None
    yukseklikler = sorted({f["height"] for f in video})
    sonuc = {"mp3": round(ses_mb, 1) if ses_mb else None, "en_yukseklik": yukseklikler[-1]}
    for k in ("360", "480", "720", "1080", "en"):
        uygun = [h for h in yukseklikler if k == "en" or h <= int(k) + 8]      # 1088 gibi değerler
        if not uygun:
            sonuc[k] = None
            continue
        h = uygun[-1]
        adaylar = [f for f in video if f["height"] == h]
        avc = [f for f in adaylar if (f.get("vcodec") or "").startswith("avc1")]
        secim = max(avc or adaylar, key=boyut)
        mb = boyut(secim) / 1e6
        if (secim.get("acodec") or "none") == "none":
            mb += ses_mb
        sonuc[k] = {"h": h, "mb": round(mb, 1) if mb else None}
    return sonuc


@app.get("/api/onizle")
def onizle():
    link = (request.args.get("link") or "").strip()
    cerez = request.args.get("cerez") or ""
    if not re.match(r"^https?://", link):
        return jsonify({"hata": "link yok"}), 400
    anahtar = (link, cerez)
    if anahtar not in onizleme_bellek:
        komut = [PYTHON, "-m", "yt_dlp", "--no-playlist", "--no-warnings", "-q", "--print",
                 "%(id)s\n%(title)s\n%(uploader)s\n%(duration)s\n%(thumbnail)s\n%(extractor_key)s\n%(is_live)s\n"
                 "%(formats.:.{height,vcodec,acodec,ext,filesize,filesize_approx,tbr})j\n%(language)s\n%(width)s\n%(height)s"]
        env = _env()
        deno = shutil.which("deno", path=env["PATH"])
        if deno:
            komut += ["--js-runtimes", f"deno:{deno}"]
        if cerez in ("chrome", "safari"):
            komut += ["--cookies-from-browser", cerez]
        komut.append(link_duzelt(link))
        try:
            p = subprocess.run(komut, env=env, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired:
            return jsonify({"hata": "zaman"}), 504
        if p.returncode != 0:
            k = (p.stdout + p.stderr).lower()
            sebep = "giris" if ("login" in k or "sign in" in k or "cookies" in k or "rate-limit" in k) else "bulunamadi"
            return jsonify({"hata": sebep}), 404
        satir = p.stdout.strip().splitlines()
        al = lambda i: satir[i].strip() if len(satir) > i and satir[i].strip() != "NA" else ""  # noqa: E731
        try:
            sure = float(al(3) or 0)
        except ValueError:
            sure = 0
        onizleme_bellek[anahtar] = {"video_id": al(0), "baslik": al(1), "kanal": al(2), "sure": sure,
                                    "kapak": al(4), "platform": al(5), "canli": al(6) in ("True", "true"),
                                    "kaliteler": _kaliteler(al(7), sure), "video_dil": (al(8) or "")[:2].lower(),
                                    "dikey": bool(al(9).isdigit() and al(10).isdigit() and int(al(10)) > int(al(9))) or "/shorts/" in link or "/reel" in link or "tiktok.com" in link}
    d = dict(onizleme_bellek[anahtar])
    d["mevcut"] = _mevcut_kayit(d["video_id"], link)
    d["mevcut_indirme"] = _mevcut_indirme(link)
    d["model_var"] = {"turbo": _model_var("turbo"), "best": _model_var("best")}
    if d["sure"]:
        dk = d["sure"] / 60
        d["tahmin"] = {m: max(1, round(dk / HIZ[m] + 0.5)) for m in HIZ}
        d["tahmin"]["konusmaci"] = round(dk / HIZ_KONUSMACI + 0.3, 1)
        d["tahmin"]["ozet"] = round(dk / HIZ_OZET + 0.5, 1)
        d["tahmin"]["goruntu"] = round(min(12, max(3, dk)) * 0.7 + 1, 1)    # ≤12 kare × ~40 sn + yazı okuma
        import dublaj as _db                                                  # ölçüm (23 Ekim, 60 sn yoğun konuşma): MLX 92 sn toplam → dk×1,6;
        d["tahmin"]["dublaj"] = round(dk * (1.6 if _db._motor() == "mlx" else 3.5) + 1)   # eski PyTorch/CPU yolu dk×3,5
    else:
        d["tahmin"] = None
    return jsonify(d)


YUKLEME = KLASOR / "yuklemeler"


MUZIK = KLASOR / "muzik"


@app.get("/api/muzik")
def muzik_liste():
    """Müzik altlığı için kullanıcının eklediği parçalar (muzik/ klasörü)."""
    MUZIK.mkdir(exist_ok=True)
    return jsonify([{"ad": f.name, "baslik": f.stem, "boyut": f.stat().st_size} for f in sorted(MUZIK.iterdir(), key=lambda x: -x.stat().st_mtime)
                    if f.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg")])


@app.post("/api/muzik")
def muzik_ekle():
    f = request.files.get("dosya")
    if not f or not f.filename:
        return jsonify({"hata": "Dosya seçilmedi."}), 400
    ad = re.sub(r'[\\/:*?"<>|]+', " ", Path(f.filename).name).strip()[:120]
    if Path(ad).suffix.lower() not in (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"):
        return jsonify({"hata": "MP3, M4A, WAV, AAC, FLAC ya da OGG seçin."}), 400
    MUZIK.mkdir(exist_ok=True)
    f.save(str(MUZIK / ad))
    return jsonify({"ad": ad})


@app.post("/api/yukle")
def yukle():
    """Bilgisayardan ses/video dosyası alır; iş bu dosya yoluyla başlatılır."""
    f = request.files.get("dosya")
    if not f or not f.filename:
        return jsonify({"hata": "Dosya seçilmedi."}), 400
    ad = re.sub(r"[^\w.\- ]+", "_", Path(f.filename).name)[:120]
    if not re.search(r"\.(mp4|mov|m4a|mp3|wav|aac|flac|ogg|opus|webm|mkv|avi|m4v|wma|aiff?|caf|amr|3gp)$", ad, re.I):
        return jsonify({"hata": "Bu dosya türü desteklenmiyor. Ses ya da video dosyası seçin."}), 400
    YUKLEME.mkdir(exist_ok=True)
    yol = YUKLEME / f"{uuid.uuid4().hex[:6]}_{ad}"
    f.save(str(yol))
    return jsonify({"yol": str(yol), "ad": ad})


@app.post("/api/liste-ac")
def liste_ac():
    """Oynatma listesi ya da kanal linkindeki videolar (en çok 50), toplu yazıya dökme için."""
    url = ((request.get_json(force=True) or {}).get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return jsonify({"hata": "Geçersiz link."}), 400
    try:
        meta, videolar = takip_modulu.listele(url, 50)
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": str(e)[:200]}), 400
    return jsonify({"ad": meta.get("ad"), "videolar": [x for x in videolar if not x.get("canli")]})


@app.post("/api/baslat")
def baslat():
    v = request.get_json(force=True) or {}
    return _baslat(v)


def _veri_kapak(temel):
    try:
        return json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"].get("kapak") or ""
    except Exception:  # noqa: BLE001
        return ""


def _baslat(v):
    if v.get("islem") == "dublaj":
        temel = v.get("temel") or ""
        if not re.match(r"^[\w\-]+$", temel) or not (KLASOR / f"{temel}.json").exists():
            return jsonify({"hata": "Transkript bulunamadı."}), 400
        import dublaj as dublaj_modulu
        if not dublaj_modulu.hazir():
            return jsonify({"hata": "Seslendirme ortamı kurulu değil."}), 400
        dil = v.get("dil") if re.match(r"^[a-z]{2}$", v.get("dil") or "") else "en"
        is_ = {"id": uuid.uuid4().hex[:8], "tur": "dublaj", "temel": temel, "dil": dil, "ozgun_sil": bool(v.get("ozgun_sil")), "onizleme": bool(v.get("onizleme")),
               "baslik": ((v.get("baslik") or temel) + (" · önizleme" if v.get("onizleme") else ""))[:150], "kalite": "720", "kapak": _kapak_yolu(temel, _veri_kapak(temel)), "sure": float(v.get("sure") or 0), "kanal": v.get("kanal") or "",
               "cerez": v.get("cerez") or "", "durum": "sirada", "adim": 0, "ilerleme": 0, "log": [], "olusturma": time.time(), "indirme": True}
        with kilit:
            isler[is_["id"]] = is_
        _kaydet(); sira_indir.put(is_["id"])
        return jsonify({"id": is_["id"]})
    if v.get("islem") == "dudak":
        import dudak as dudak_modulu
        if not dudak_modulu.hazir():
            return jsonify({"hata": "sync.so anahtarı yok; Ayarlar → Video → Dudak senkronu."}), 400
        yol = _indirilen_dogrula(str(v.get("dosya") or ""))
        d0 = _dizin_oku().get(yol.name, {})
        is_ = {"id": uuid.uuid4().hex[:8], "tur": "dudak", "dosya_ad": yol.name, "baslik": ((d0.get("baslik") or yol.stem) + " · dudak senkronu")[:150],
               "kalite": "dudak", "kapak": d0.get("kapak") or "", "sure": float(d0.get("sure") or 0), "kanal": d0.get("kanal") or "", "link": "",
               "durum": "sirada", "adim": 0, "ilerleme": 0, "log": [], "olusturma": time.time(), "indirme": True}
        with kilit:
            isler[is_["id"]] = is_
        _kaydet(); sira_indir.put(is_["id"])
        return jsonify({"id": is_["id"]})
    if v.get("islem") == "sessizlik":
        temel = v.get("temel") or ""
        if not re.match(r"^[\w\-]+$", temel) or not (KLASOR / f"{temel}.json").exists():
            return jsonify({"hata": "Transkript bulunamadı."}), 400
        bicim = v.get("bicim") if v.get("bicim") in ("mp4", "fcpxml", "premiere", "resolve") else "mp4"
        is_ = {"id": uuid.uuid4().hex[:8], "tur": "sessizlik", "temel": temel, "bicim": bicim, "esik": str(v.get("esik") or "4%"), "pay": str(v.get("pay") or "0.2"),
               "baslik": (v.get("baslik") or temel)[:150], "kalite": "720", "kapak": _kapak_yolu(temel, _veri_kapak(temel)), "sure": float(v.get("sure") or 0), "kanal": v.get("kanal") or "",
               "cerez": v.get("cerez") or "", "durum": "sirada", "adim": 0, "ilerleme": 0, "log": [], "olusturma": time.time(), "indirme": True}
        with kilit:
            isler[is_["id"]] = is_
        _kaydet(); sira_indir.put(is_["id"])
        return jsonify({"id": is_["id"]})
    if v.get("islem") in ("altyazili", "klip", "kesim"):
        is_id = _video_isi_baslat(v)
        if not is_id:
            return jsonify({"hata": "Transkript bulunamadı."}), 404
        return jsonify({"id": is_id})
    link = (v.get("link") or "").strip()
    yukleme = link.startswith(str(YUKLEME) + "/") and Path(link).is_file()
    indirilen = link.startswith(str(INDIRILENLER) + "/") and Path(link).is_file()
    kayit = link.startswith(str(KAYIT) + "/") and Path(link).is_file()
    yerel = yukleme or indirilen or kayit
    if not re.match(r"^https?://", link) and not yerel:
        return jsonify({"hata": "Geçerli bir link girin ya da bir dosya bırakın."}), 400
    if v.get("islem") == "indir":
        if yerel:
            return jsonify({"hata": "Bu zaten bilgisayarınızda bir dosya."}), 400
        return _indirme_baslat(v, link)
    dil = v.get("dil") if re.match(r"^[a-z]{2,5}$", v.get("dil") or "") else "auto"
    model = v.get("model") if v.get("model") in ("turbo", "best") else "turbo"
    cerez = v.get("cerez") if v.get("cerez") in ("chrome", "safari") else ""
    uyari = None
    try:
        if shutil.disk_usage(str(KLASOR)).free < 5 * 1024 ** 3:
            uyari = "Diskte 5 GB'tan az yer kaldı; işlem yarıda kalabilir."
    except Exception:  # noqa: BLE001
        pass
    is_id = uuid.uuid4().hex[:8]
    isler[is_id] = {
        "id": is_id, "link": link, "dil": dil, "model": model, "yerel": yerel, "yerel_sil": yukleme,
        "baslik": re.sub(r"\s*\[[^\]]*\]$", "", re.sub(r"^[0-9a-f]{6}_", "", Path(link).stem)) if yerel else None,
        "isimler": ",".join(x.strip() for x in (v.get("isimler") or "").split(",") if x.strip()),
        "cerez": cerez, "altyazi": bool(v.get("altyazi", True)),
        "ozet": (None if v.get("ozet") is None else bool(v.get("ozet"))),
        "konusmaci": bool(v.get("konusmaci", True)),
        "goruntu": bool(v.get("goruntu", False)), "ozet_modu": bool(v.get("ozet_modu", False)),
        "ad": re.sub(r"[^\w\-]", "", str(v.get("ad") or ""))[:120],
        "ceviri_dil": (v.get("ceviri_dil") if re.match(r"^[a-z]{2,3}$", v.get("ceviri_dil") or "") else ""),
        "dublaj": bool(v.get("dublaj")), "dublaj_dil": (v.get("dublaj_dil") if re.match(r"^[a-z]{2}$", v.get("dublaj_dil") or "") else ""),
        "altyazili": bool(v.get("altyazili")), "altyazi_stil": v.get("altyazi_stil") or "kutu",
        "duzen": {k: v.get("duzen", {}).get(k) for k in ("format", "zoom", "isim_bandi", "studyo", "tekrar", "altyazisiz", "emoji", "muzik", "konusana", "arka")} if isinstance(v.get("duzen"), dict) else {},
        "altyazi_font": re.sub(r"[^a-z]", "", v.get("altyazi_font") or "")[:12], "altyazi_renk": re.sub(r"[^0-9a-fA-F]", "", v.get("altyazi_renk") or "")[:6],
        "video_kalite": str(v.get("video_kalite") or "720"), "takip": v.get("takip") or "", "ghost": bool(v.get("ghost")),
        "ses_temizle": bool(v.get("ses_temizle")), "marka": re.sub(r"[^a-z0-9_]", "", str(v.get("marka") or ""))[:40],
        "toplanti": bool(v.get("toplanti")), "toplanti_baslik": (v.get("toplanti_baslik") or "")[:120], "kayit_dosya": v.get("kayit_dosya") or "", "mik_dosya": v.get("mik_dosya") or "", "takvim": v.get("takvim") if isinstance(v.get("takvim"), dict) else None,
        "musteri": (v.get("musteri") or "")[:40], "uygulama": (v.get("uygulama") or "")[:80], "kayit_baslangic": v.get("kayit_baslangic"),
        "couple": re.sub(r"[^a-f0-9]", "", str(v.get("couple") or ""))[:10], "couple_video": re.sub(r"[^a-f0-9]", "", str(v.get("couple_video") or ""))[:8],
        "katilimcilar": [str(x)[:60] for x in (v.get("katilimcilar") or [])][:50], "konusmaci_olaylari": v.get("konusmaci_olaylari") or [],
        "konusmaci_sayisi": (int(v["konusmaci_sayisi"]) if str(v.get("konusmaci_sayisi") or "").isdigit() and 1 <= int(v["konusmaci_sayisi"]) <= 12 else None),
        "durum": "sirada", "log": [], "ilerleme": 0, "adim": 0, "adim_metni": "Sırada bekliyor",
        "olusturma": time.time(),
    }
    for (l, _c), oz in onizleme_bellek.items():
        if l == link:
            isler[is_id].update({k: oz[k] for k in ("baslik", "kapak", "sure", "kanal") if oz.get(k)})
            break
    if indirilen:
        d = _dizin_oku().get(Path(link).name) or {}
        kap = INDIRILENLER / ".kapaklar" / f"{Path(link).stem}.jpg"
        isler[is_id].update({"baslik": d.get("baslik") or isler[is_id]["baslik"], "kanal": d.get("kanal", ""),
                             "sure": d.get("sure", 0), "kapak": f"/indirilen-kapak/{Path(link).stem}.jpg" if kap.exists() else ""})
    sira.put(is_id)
    indir_id = None
    if v.get("video_kaydet") and not yerel and not v.get("altyazili"):   # transkriptle birlikte videoyu da sakla (altyazılıda zaten iner)
        r = _indirme_baslat({"link": link, "kalite": v.get("video_kalite"), "cerez": cerez}, link)
        indir_id = (r.get_json() or {}).get("id")
    _kaydet()
    return jsonify({"id": is_id, "uyari": uyari, "indir_id": indir_id})


def _indirme_baslat(v, link):
    kalite = str(v.get("kalite") or "720").lower()
    if kalite not in KALITELER:
        kalite = "720"
    cerez = v.get("cerez") if v.get("cerez") in ("chrome", "safari") else ""
    kesit = (v.get("kesit") or "").strip()
    kesit_sn = 0
    if kesit:
        if not re.match(r"^[\d:.]*-[\d:.]*$", kesit):
            return jsonify({"hata": "Bölüm biçimi 1:20-2:45 gibi olmalı."}), 400
        try:
            import indir as indir_modulu
            bas, bit = indir_modulu.kesit_coz(kesit)
            kesit_sn = (bit - bas) if bit is not None else 0
        except SystemExit as e:
            return jsonify({"hata": str(e).replace("HATA: ", "")}), 400
    uyari = None
    try:
        if shutil.disk_usage(str(KLASOR)).free < 2 * 1024 ** 3:
            uyari = "Diskte 2 GB'tan az yer kaldı."
    except Exception:  # noqa: BLE001
        pass
    is_id = uuid.uuid4().hex[:8]
    isler[is_id] = {
        "id": is_id, "tur": "indir", "link": link, "kalite": kalite, "kesit": kesit, "kesit_sn": kesit_sn,
        "kapak_kaydet": bool(v.get("kapak")), "cerez": cerez, "baslik": None,
        "durum": "sirada", "log": [], "ilerleme": 0, "adim": 0, "adim_metni": "Sırada bekliyor", "olusturma": time.time(),
    }
    for (l, _c), oz in onizleme_bellek.items():
        if l == link:
            isler[is_id].update({k: oz[k] for k in ("baslik", "kapak", "sure", "kanal", "platform") if oz.get(k)})
            if kesit_sn:
                isler[is_id]["sure"] = kesit_sn
            break
    sira_indir.put(is_id)
    _kaydet()
    return jsonify({"id": is_id, "uyari": uyari})


def _is_json(is_):
    d = {k: v for k, v in is_.items() if k not in ("log", "p")}
    d["log"] = is_.get("log", [])[-40:]
    bekleyen = [k for k, j in list(isler.items()) if j["durum"] == "sirada" and j.get("tur") == is_.get("tur")]
    d["sira_no"] = (bekleyen.index(is_["id"]) + 1) if is_["id"] in bekleyen else 0
    if not is_.get("tur") and is_["durum"] in ("sirada", "calisiyor"):
        try:
            d["tahmini_bitis"] = _tahmini_bitis(is_)
        except Exception:  # noqa: BLE001
            pass
    return d


_oran_onbellek = {"t": 0, "oran": 0.35}


def _islem_orani():
    """Son 30 günün gerçek transkript süreleri: işlem süresi / video süresi (ortanca). Tahmini bitiş saati için."""
    if time.time() - _oran_onbellek["t"] > 600:
        try:
            import kalite
            L = sorted(x["oran"] for x in kalite._oku(30) if x.get("ozellik") == "transkript" and x.get("oran") and not x.get("toplanti"))
            if len(L) >= 3:
                _oran_onbellek["oran"] = L[len(L) // 2]
        except Exception:  # noqa: BLE001
            pass
        _oran_onbellek["t"] = time.time()
    return _oran_onbellek["oran"]


def _tahmini_bitis(is_):
    """Sıradaki yazıya dökme işlerinin sırayla biteceği saat (epoch); süresi bilinmeyen iş varsa None."""
    oran, simdi, t = _islem_orani(), time.time(), time.time()
    sira = [j for j in sorted(isler.values(), key=lambda x: x["olusturma"]) if not j.get("tur") and j["durum"] in ("calisiyor", "sirada")]
    sira.sort(key=lambda j: j["durum"] != "calisiyor")
    for j in sira:
        sure = j.get("sure") or 0
        if not sure:
            return None
        if j["durum"] == "calisiyor":
            t = simdi + max(30, sure * oran - (simdi - (j.get("baslangic") or simdi)))
        else:
            t += sure * oran
        if j["id"] == is_["id"]:
            return int(t)
    return None


@app.get("/api/is/<is_id>")
def is_durum(is_id):
    is_ = isler.get(is_id)
    if not is_:
        abort(404)
    return jsonify(_is_json(is_))


@app.post("/api/is/<is_id>/ekler")
def is_ekler(is_id):
    """Studio "önce yap, sonra sor" (2026-10-22): transkript işi sürerken ek çıktılar (düzenlenmiş video, dublaj, altyazı dili) değiştirilir;
    `_zincir` iş bitince is_ alanlarını o an okur. İş bittiyse {bitti: true} (ekler artık sonuç sayfasından)."""
    is_ = isler.get(is_id)
    if not is_:
        abort(404)
    if is_["durum"] not in ("sirada", "calisiyor"):
        return jsonify({"bitti": True})
    v = request.get_json(silent=True) or {}
    if "altyazili" in v:
        is_["altyazili"] = bool(v["altyazili"])
    if isinstance(v.get("duzen"), dict):
        is_["duzen"] = {k: v["duzen"].get(k) for k in ("format", "zoom", "isim_bandi", "studyo", "tekrar", "altyazisiz", "emoji", "muzik", "konusana", "arka")}
    for k in ("altyazi_stil", "altyazi_font", "altyazi_renk"):
        if k in v:
            is_[k] = str(v[k] or "")[:40]
    if "ceviri_dil" in v:
        is_["ceviri_dil"] = v["ceviri_dil"] if re.match(r"^[a-z]{2}$", v.get("ceviri_dil") or "") else ""
    if "dublaj" in v:
        is_["dublaj"] = bool(v["dublaj"])
        is_["dublaj_dil"] = v.get("dublaj_dil") if re.match(r"^[a-z]{2}$", v.get("dublaj_dil") or "") else (is_.get("dublaj_dil") or "en")
    _kaydet()
    return jsonify({"tamam": True, "altyazili": is_.get("altyazili"), "dublaj": is_.get("dublaj"), "dublaj_dil": is_.get("dublaj_dil")})


@app.post("/api/dublaj/<temel>")
def dublaj_baslat(temel):
    """Sonuç sayfasından tek tık dublaj: çeviri yoksa önce çevirir, sonra seslendirme işi kuyruğa girer."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    dil = (request.get_json(silent=True) or {}).get("dil") or "en"
    onizleme = bool((request.get_json(silent=True) or {}).get("onizleme"))
    if not re.match(r"^[a-z]{2}$", dil):
        return jsonify({"hata": "Dil anlaşılamadı."}), 400
    veri = json.loads(tj.read_text(encoding="utf-8"))["veri"]

    def _calis():
        try:
            if dil not in (veri.get("ceviriler") or {}):
                _ceviri_calistir(temel, dil)
            with app.app_context():
                _baslat({"islem": "dublaj", "temel": temel, "dil": dil, "baslik": veri.get("baslik") or temel, "kapak": f"/kapak/{temel}.jpg",
                         "sure": veri.get("sure") or 0, "kanal": veri.get("kanal") or "", "onizleme": onizleme})
        except Exception as e:  # noqa: BLE001
            print(f"Dublaj başlatılamadı: {e}", flush=True)
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True, "ceviri": dil not in (veri.get("ceviriler") or {})})


@app.delete("/api/is/<is_id>")
def is_iptal(is_id):
    is_ = isler.get(is_id)
    if not is_:
        abort(404)
    if is_["durum"] in ("sirada", "calisiyor"):
        is_["durum"] = "iptal"
        is_["hata"] = "Durduruldu."
        p = is_.get("p")
        if p and p.poll() is None:
            try:
                pg = os.getpgid(p.pid)
                os.killpg(pg, 15)      # caffeinate + script + yt-dlp hepsi birlikte dursun

                def _zorla(pg=pg):     # 2026-10-24: dolu diskte asılı kalan ffmpeg kibar sinyali yuttu, 8,6 GB bellekle çalışmayı sürdürdü
                    time.sleep(5)
                    try:
                        os.killpg(pg, 9)
                    except Exception:  # noqa: BLE001
                        pass
                threading.Thread(target=_zorla, daemon=True).start()
            except Exception:  # noqa: BLE001
                try:
                    p.terminate()
                except Exception:  # noqa: BLE001
                    pass
    else:
        with kilit:
            isler.pop(is_id, None)                     # bitmiş/hatalı kart kapatıldı: listeden kalıcı olarak çıkar
    _kaydet()
    return jsonify({"tamam": True})


@app.get("/api/isler")
def is_listesi():
    simdi = time.time()
    return jsonify([_is_json(i) for i in sorted(isler.values(), key=lambda x: -x["olusturma"])
                    if simdi - i["olusturma"] < 86400])


@app.post("/api/guncelle")
def guncelle():
    tamam, cikti = _guncelle()
    return jsonify({"tamam": tamam, "cikti": cikti})


_gecmis_onbellek = {}


@app.get("/api/gecmis")
def gecmis():
    """Kitaplık listesi. Her dosyanın satırı değişiklik zamanına göre bellekte tutulur; yalnızca değişen dosyalar yeniden okunur
    (2026-10-19: eskiden her açılışta bütün transkript JSON'ları baştan okunuyordu)."""
    benim_adim_ilk = ((ayarlar_oku().get("benim_adim") or "").split() or [""])[0]
    sonuc = []
    gorulen = set()
    for js in KLASOR.glob("transkript_*.json"):
        gorulen.add(js)
        try:
            mt = js.stat().st_mtime
        except OSError:
            continue
        onb = _gecmis_onbellek.get(js)
        if onb and onb[0] == mt:
            sonuc.append(onb[1]); continue
        try:
            veri = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        temel = js.with_suffix("")
        sonuc.append({
            "temel": temel.name, "baslik": veri.get("baslik") or temel.name, "kanal": veri.get("kanal", ""),
            "link": veri.get("link", ""), "dil": veri.get("dil", ""), "sure": veri.get("sure", 0),
            "kaynak": veri.get("kaynak", ""), "model": veri.get("model", ""), "konusmacilar": veri.get("etiket", {}),
            "kapak": _kapak_yolu(temel.name, veri.get("kapak")), "platform": veri.get("platform", ""),
            "uyari": len(veri.get("uyarilar", [])), "ozet": bool(veri.get("ozet")), "goruntu": bool(veri.get("goruntu")),
            "senaryo": (temel.parent / f"{temel.name}.senaryo.docx").exists(), "takip": veri.get("takip", ""),
            "toplanti": bool(veri.get("toplanti")), "drive": veri.get("drive", ""), "musteri": veri.get("musteri", ""),
        "adsiz": len([a for a in (veri.get("etiket") or {}).values() if str(a).startswith("Konuşmacı ")]),
        "paylasim": len((veri.get("paylasim") or {}).get("taslaklar") or []),
        "marka": veri.get("marka", ""), "marka_paket": sorted((veri.get("marka_paket") or {}).get(veri.get("marka", ""), {}).get("secim") or []),
            "katilimcilar": veri.get("katilimcilar", []), "uygulama": veri.get("uygulama", ""), "misafir": veri.get("misafir") or "",
            "karar": len((veri.get("ozet") or {}).get("kararlar") or []), "yapilacak": len((veri.get("ozet") or {}).get("yapilacaklar") or []),
            "ceviriler": list((veri.get("ceviriler") or {}).keys()),
            "atolye": bool(veri.get("atolye") or veri.get("couple")), "koleksiyonlar": veri.get("koleksiyonlar", []),
            "olusturma": veri.get("olusturma") or js.stat().st_mtime,
            "docx": temel.with_suffix(".docx").exists(), "txt": temel.with_suffix(".txt").exists(),
        })
        if veri.get("toplanti"):                                 # Transcript ızgarası: kartta kısa özet ve açık işler
            ks = veri.get("kisaca") or {}
            kisa = (ks.get("ozet") or [""])[0] or ((veri.get("ozet") or {}).get("ozet") if isinstance(veri.get("ozet"), dict) else "") or ""
            ben = (benim_adim_ilk or "").lower()
            sonuc[-1].update({
                "kisa": kisa[:260], "danisman": bool(veri.get("danisman")), "sirket": veri.get("sirket") or "",
                "onay_bekliyor": bool(veri.get("onay_bekliyor")), "onay_neden": (veri.get("onay_bekliyor") or {}).get("neden", ""), "sesli_ozet": (veri.get("sesli_ozet") or {}).get("sn") or 0,
                "musteri_tahmin": veri.get("musteri_tahmin") or "",
                "acik_is": sum(1 for k in ks.get("kisiler") or [] for x in k.get("isler") or [] if not x.get("bitti")) + sum(1 for x in ks.get("belirsiz") or [] if not x.get("bitti")),
                "benim_is": sum(1 for k in ks.get("kisiler") or [] if ben and k.get("ad", "").lower().split()[:1] == [ben] for x in k.get("isler") or [] if not x.get("bitti")),
            })
        _gecmis_onbellek[js] = (mt, sonuc[-1])
    for eski_js in [k for k in _gecmis_onbellek if k not in gorulen]:
        _gecmis_onbellek.pop(eski_js, None)
    sonuc.sort(key=lambda x: -x["olusturma"])
    return jsonify(sonuc)


def _temel_dogrula(temel):
    if not re.match(r"^[\w\-]+$", temel) or not (KLASOR / f"{temel}.json").exists():
        abort(404)
    return KLASOR / temel


@app.get("/api/metin/<temel>")
def metin(temel):
    t = _temel_dogrula(temel)
    veri_tum = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))
    veri = dict(veri_tum["veri"])
    veri["kapak"] = _kapak_yolu(temel, veri.get("kapak"))
    paragraflar = paragrafla(veri_tum["segmentler"], veri_tum["veri"]["etiket"])
    saatli = any(p["bas"] >= 3600 for p in paragraflar)
    veri["ozet_hazir"] = ozet_modulu.hazir()
    veri["senaryo"] = (KLASOR / f"{temel}.senaryo.docx").exists()
    ceviriler = {}
    for dil, c in (veri.get("ceviriler") or {}).items():
        try:
            import ceviri as ceviri_modulu
            _, cpar = ceviri_modulu.paragraf_ceviri(veri_tum["segmentler"], veri_tum["veri"]["etiket"], c["segmentler"])
            ceviriler[dil] = {"paragraflar": cpar, "ozet": c.get("ozet"), "srt": (KLASOR / f"{temel}.{dil}.srt").exists(),
                              "docx": (KLASOR / f"{temel}.{dil}.docx").exists()}
        except Exception:  # noqa: BLE001
            continue
    veri["ceviriler"] = ceviriler
    kaynak, _ = _kaynak_video(temel)
    veri["kaynak_video"] = kaynak.name if kaynak else ""
    veri["turemisler"] = _turemisler(temel)
    veri["kunye"] = _kunye(temel, veri_tum["veri"])
    veri["ceviri_durum"] = ceviri_durum.get(temel)
    seg = veri_tum["segmentler"]
    # eski kayıtlar: düzeltmeler yalnız örnek listede ("eski → yeni"); yenilerde bölümün içinde
    duz = {}
    for o in (veri_tum["veri"].get("temizlik") or {}).get("ornekler") or []:
        if " → " in str(o):
            e_, y_ = str(o).split(" → ", 1)
            if y_.strip():
                duz[y_.strip().split()[0].strip(".,;:!?'\"").lower()] = e_.strip()
    return jsonify({"veri": veri, "paragraflar": [
        {"zaman": _zaman(p["bas"], saatli), "sn": int(p["bas"]), "bas": round(p["bas"], 2), "bit": p["bit"], "ad": p["ad"], "metin": p["metin"],
         "k": _kelime_zamanlari([seg[i] for i in p.get("si", [])], duz),
         **({"belirsiz": True} if any(seg[i].get("k_belirsiz") for i in p.get("si", [])) else {})}
        for p in paragraflar]})


def _kelime_zamanlari(segler, duz=None):
    """Paragrafın kelimeleri [başlangıç sn, kelime(, işaret)]: kelime zamanı varsa o, yoksa segment süresi karakter oranıyla bölünür
    (okuma görünümünde çalan kelimeyi vurgulamak ve kelimeye tıklayınca o ana gitmek için). 23 Ekim (ChatGPT brifi, Studio 2): işaret 'd:<duyulan>'
    = yapay zekâ düzeltti (duyulan ham söz), 's' = ses modeli düşük güvenle duydu (ad ya da sayı; doğrulayın)."""
    duz = duz or {}
    out = []

    def isaret(w, s, i):
        anahtar = w.strip(".,;:!?'\"”“").lower()
        for d in s.get("duzeltmeler") or []:
            if anahtar and anahtar in str(d.get("yeni", "")).lower().split():
                if d.get("kaynak") in ("altyazi", "baglam"):       # Meet (2026-10-25): toplantı altyazısından ya da Claude'un bağlam tahmininden
                    return "d:" + str(d.get("eski", "")).replace("|", " ") + "|" + d["kaynak"] + "|" + str(d.get("neden") or "").replace("|", " ")
                return "d:" + str(d.get("eski", ""))
        if not s.get("duzeltmeler") and anahtar in duz:
            return "d:" + duz[anahtar]
        g = s.get("guven")
        if g and i is not None and i < len(g) and g[i] < 0.45 and (w[:1].isupper() or any(c.isdigit() for c in w)):
            return "s"
        return ""
    for s in segler:
        kel = s.get("kelimeler")
        if kel and " ".join(w for _b, _e, w in kel).split() == s["metin"].split():
            for i, (b, _e, w) in enumerate(kel):
                f = isaret(w, s, i)
                out.append([round(b, 2), w, f] if f else [round(b, 2), w])
            continue
        sozler = s["metin"].split()
        toplam = sum(len(w) + 1 for w in sozler) or 1
        t, sure = s["bas"], max(0.01, s["bit"] - s["bas"])
        for w in sozler:
            f = isaret(w, s, None)
            out.append([round(t, 2), w, f] if f else [round(t, 2), w])
            t += sure * (len(w) + 1) / toplam
    i = 0                                                  # aynı zamana yığılmış kelimeler (Whisper kesit başında 0,0 verebiliyor) aralığa yayılır
    while i < len(out):
        j = i
        while j + 1 < len(out) and out[j + 1][0] <= out[i][0]:
            j += 1
        if j > i:
            son = out[j + 1][0] if j + 1 < len(out) else out[i][0] + 0.3 * (j - i + 1)
            for n in range(i, j + 1):
                out[n][0] = round(out[i][0] + (son - out[i][0]) * (n - i) / (j - i + 1), 2)
        i = j + 1
    return out


@app.post("/api/isimlendir/<temel>")
def isimlendir(temel):
    t = _temel_dogrula(temel)
    v = request.get_json(force=True) or {}
    komut = [PYTHON, str(ISIMLENDIR), str(t.with_suffix(".json"))]
    for ad in v.get("sil", []):
        komut += ["--sil", ad]
    for eski, yeni in (v.get("degisim") or {}).items():
        eski, yeni = eski.strip(), yeni.strip()
        if yeni and eski != yeni:
            komut.append(f"{eski}={yeni}")
    if len(komut) == 3:
        return jsonify({"tamam": True})
    with kilit:
        yedek = t.with_suffix(".json").read_text(encoding="utf-8")
        (COP / f"{temel}.onceki.json").parent.mkdir(exist_ok=True)
        (COP / f"{temel}.onceki.json").write_text(yedek, encoding="utf-8")
        p = subprocess.run(komut, cwd=str(KLASOR), capture_output=True, text=True)
    if p.returncode != 0:
        return jsonify({"hata": (p.stdout + p.stderr).strip().splitlines()[-1]}), 400
    veri = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))["veri"]
    return jsonify({"tamam": True, "konusmacilar": veri["etiket"], "ogrenilen": _ses_ogren(veri)})


def _ses_ogren(veri):
    try:
        import sesler as sesler_modulu
        return sesler_modulu.ogren(veri)
    except Exception:  # noqa: BLE001
        return []


@app.get("/api/sesler")
def sesler_listesi():
    import sesler as sesler_modulu
    return jsonify([{"ad": a, "sayac": v.get("sayac", 1)} for a, v in sesler_modulu.oku().items()])


@app.delete("/api/sesler/<ad>")
def sesler_sil(ad):
    import sesler as sesler_modulu
    return jsonify({"tamam": sesler_modulu.sil(ad)})


@app.post("/api/geri-al/<temel>")
def geri_al(temel):
    """Son ad/birleştirme işlemini geri alır."""
    t = _temel_dogrula(temel)
    y = COP / f"{temel}.onceki.json"
    if not y.exists():
        return jsonify({"hata": "Geri alınacak bir şey yok."}), 400
    d = json.loads(y.read_text(encoding="utf-8"))
    with kilit:
        ciktilari_yaz(t, d["veri"], d["segmentler"])
    y.unlink()
    return jsonify({"tamam": True})


@app.post("/api/segment/<temel>")
def segment_degistir(temel):
    """Bir paragrafın (zaman aralığının) konuşmacısını değiştirir."""
    t = _temel_dogrula(temel)
    v = request.get_json(force=True) or {}
    bas, bit, ad = float(v.get("bas", -1)), float(v.get("bit", -1)), (v.get("ad") or "").strip()
    d = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))
    etiket = d["veri"]["etiket"]
    k = next((kk for kk, vv in etiket.items() if vv == ad), None)
    if k is None:
        if not ad:
            return jsonify({"hata": "Ad boş olamaz."}), 400
        k = str(max([int(x) for x in etiket] + [-1]) + 1)       # yeni konuşmacı
        etiket[k] = ad
    n = 0
    for s in d["segmentler"]:
        if s["bas"] >= bas - 0.05 and s["bit"] <= bit + 0.05:
            s["k"] = k; n += 1
    if not n:
        return jsonify({"hata": "Paragraf bulunamadı."}), 400
    kullanilan = {s["k"] for s in d["segmentler"]}
    for kk in list(etiket):
        if kk not in kullanilan:
            del etiket[kk]
    with kilit:
        COP.mkdir(exist_ok=True)
        (COP / f"{temel}.onceki.json").write_text(t.with_suffix(".json").read_text(encoding="utf-8"), encoding="utf-8")
        ciktilari_yaz(t, d["veri"], d["segmentler"])
    _ses_ogren(d["veri"])
    return jsonify({"tamam": True, "konusmacilar": etiket})


ozet_kilit = threading.Lock()
ozet_calisan = set()


def _yz_baglam(veri):
    """Toplantı içeriğiyse Claude çağrıları toplantı iznine tabi olur (Ayarlar → Toplantılarda da Claude)."""
    import claude_yaz
    from contextlib import nullcontext
    return claude_yaz.toplanti() if veri.get("toplanti") else nullcontext()


@app.post("/api/ozet/<temel>")
def ozet_cikar(temel):
    """Var olan bir transkript için özet üretir (ya da yeniler). 2026-10-27: {bicim: kisa|ayrintili|madde|"", not, varsayilan}
    eski özet `veri.ozet_gecmis`'e (en çok 5) girer; `varsayilan` seçilen biçimi sonraki videolar için Ayarlar'a yazar."""
    t = _temel_dogrula(temel)
    if not ozet_modulu.hazir():
        return jsonify({"hata": "Özet modeli hazır değil. Kurulum sürüyor olabilir; biraz sonra tekrar deneyin."}), 503
    if temel in ozet_calisan:
        return jsonify({"hata": "Bu transkriptin özeti zaten çıkarılıyor."}), 409
    g = request.get_json(silent=True) or {}
    hedef = g.get("dil") or _ozet_dili()
    bicim = g.get("bicim")
    if bicim is not None:
        bicim = str(bicim) if str(bicim) in ozet_modulu.BICIMLER else ""
    ozet_calisan.add(temel)
    try:
        d = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))
        with _yz_baglam(d["veri"]):
            o = ozet_modulu.ozet_uret(paragrafla(d["segmentler"], d["veri"]["etiket"]), d["veri"].get("dil", "tr"), hedef,
                                      log=lambda *_: None, bicim=bicim, istek=str(g.get("not") or "")[:400])
        if not o:
            return jsonify({"hata": "Özet üretilemedi."}), 500
        with kilit:
            d = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))   # model çalışırken yapılan ad/çeviri değişiklikleri kaybolmasın
            if d["veri"].get("ozet"):
                eski = dict(d["veri"]["ozet"]); eski.setdefault("zaman", time.time())
                d["veri"]["ozet_gecmis"] = ([eski] + list(d["veri"].get("ozet_gecmis") or []))[:5]
            o["zaman"] = time.time()
            d["veri"]["ozet"] = o
            ciktilari_yaz(t, d["veri"], d["segmentler"])
            if g.get("varsayilan") and bicim is not None and not (globals().get("_misafir_istek") and _misafir_istek()):   # davetli sahibin ayarını değiştirmesin
                a = ayarlar_oku(); a["ozet_bicim"] = bicim; ayarlar_yaz(a)
        return jsonify({"tamam": True, "ozet": o, "ozet_gecmis": d["veri"].get("ozet_gecmis") or []})
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": f"Özet çıkarılamadı: {e}"}), 500
    finally:
        ozet_calisan.discard(temel)


@app.post("/api/ozet/<temel>/geri")
def ozet_geri(temel):
    """Önceki özet sürümüne dön: seçilen sürüm özet olur, şimdiki geçmişe girer."""
    t = _temel_dogrula(temel)
    i = int((request.get_json(silent=True) or {}).get("i", 0))
    with kilit:
        d = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))
        gecmis = list(d["veri"].get("ozet_gecmis") or [])
        if not 0 <= i < len(gecmis):
            return jsonify({"hata": "Bu sürüm yok."}), 404
        secilen = gecmis.pop(i)
        if d["veri"].get("ozet"):
            gecmis.insert(0, d["veri"]["ozet"])
        d["veri"]["ozet"], d["veri"]["ozet_gecmis"] = secilen, gecmis[:5]
        ciktilari_yaz(t, d["veri"], d["segmentler"])
    return jsonify({"tamam": True, "ozet": secilen, "ozet_gecmis": gecmis[:5]})


@app.post("/api/ceviri/<temel>")
def ceviri_baslat(temel):
    _temel_dogrula(temel)
    dil = ((request.get_json(silent=True) or {}).get("dil") or "").lower()
    if not re.match(r"^[a-z]{2,3}$", dil):
        return jsonify({"hata": "Dil seçin."}), 400
    if not ozet_modulu.hazir():
        return jsonify({"hata": "Çeviri modeli hazır değil (Ollama kapalı olabilir)."}), 503
    if ceviri_durum.get(temel, {}).get("calisiyor"):
        return jsonify({"hata": "Bu transkript zaten çevriliyor."}), 409
    threading.Thread(target=_ceviri_calistir, args=(temel, dil), daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/ceviri-durum/<temel>")
def ceviri_durumu(temel):
    return jsonify(ceviri_durum.get(temel) or {"calisiyor": False})


@app.get("/api/ara")
def ara():
    q = (request.args.get("q") or "").strip()
    temel = request.args.get("temel") or None
    return jsonify(sor_modulu.ara(q, limit=60, temel=temel))


@app.post("/api/koleksiyon/<temel>")
def koleksiyon_kaydet(temel):
    """Transkriptin koleksiyonları (etiketler): {"koleksiyonlar": ["Bebek", "Müşteri araştırması"]}."""
    t = _temel_dogrula(temel)
    L = (request.get_json(force=True) or {}).get("koleksiyonlar") or []
    temiz = []
    for x in L:
        x = re.sub(r"\s+", " ", str(x)).strip()[:40]
        if x and x.lower() not in [y.lower() for y in temiz]:
            temiz.append(x)
    vt = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))
    vt["veri"]["koleksiyonlar"] = temiz[:12]
    t.with_suffix(".json").write_text(json.dumps(vt, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify({"koleksiyonlar": temiz[:12]})


@app.get("/api/anlam")
def anlam_ara():
    """Anlam üzerinden arama (anlam.py); kelime aramasının yanında 'Anlamca yakın' sonuçları."""
    import anlam
    q = (request.args.get("q") or "").strip()
    temel = request.args.get("temel") or None
    try:
        hits = anlam.ara(q, limit=10, temel=temel)
    except Exception as e:  # noqa: BLE001
        return jsonify([]) if "No module" in str(e) else (jsonify({"hata": str(e)[:200]}), 500)
    par = {(p["temel"], p["sn"] if not p.get("ozet") else -1): p for p in sor_modulu.dizin()}
    out = []
    for puan, t, sn in hits:
        p = par.get((t, sn))
        if p:
            out.append({"temel": t, "sn": sn, "baslik": p["baslik"], "ad": p["ad"], "metin": p["metin"], "puan": round(puan, 3)})
    return jsonify(out)


def _anlam_dongu():
    """Yeni ya da değişen transkriptleri anlam dizinine ekler: 10 dk'da bir, yalnız sırada iş yokken, düşük öncelikli alt süreçte."""
    import anlam
    while True:
        time.sleep(600)
        try:
            d = anlam.durum()
            if d["hazir"] < d["toplam"] and not mesgul_nedenler():
                subprocess.run(["/usr/bin/nice", "-n", "15", sys.executable, str(KLASOR / "anlam.py"), "--guncelle"],
                               capture_output=True, timeout=3600, cwd=str(KLASOR))
        except Exception:  # noqa: BLE001
            pass
threading.Thread(target=_anlam_dongu, daemon=True).start()


@app.post("/api/sor")
def sor_():
    v = request.get_json(force=True) or {}
    soru = (v.get("soru") or "").strip()
    if not soru:
        return jsonify({"hata": "Soru boş."}), 400
    if not ozet_modulu.hazir():
        return jsonify({"hata": "Yanıt modeli hazır değil (Ollama kapalı olabilir)."}), 503
    temel = v.get("temel") or None
    if temel and not re.match(r"^[\w\-]+$", temel):
        temel = None
    kapsam = str(v.get("kapsam") or "")[:60] or None
    try:
        return jsonify(sor_modulu.sor(soru, temel, kapsam=kapsam))
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": f"Yanıt alınamadı: {e}"}), 500


@app.get("/api/dolgu/<temel>")
def dolgu(temel):
    """Duraksama seslerinin (ee, ıı, hmm) zaman aralıkları; metinden kesme için. Whisper bunları çoğu zaman yazmadığı için ilk
    istekte şüpheli parçalar arka planda yeniden dinlenir (dolgu.py); o sürerken taraniyor: true döner."""
    import dolgu as dolgu_modulu
    t = _temel_dogrula(temel)
    d = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))
    ar = dolgu_modulu.birlesik(d)
    kelime_var = any(s_.get("kelimeler") for s_ in d["segmentler"])
    tarandi = (d["veri"].get("dolgu") or {}).get("imza") == dolgu_modulu.imza(d["segmentler"])
    ad = f"dolgu:{temel}"
    is_ = (globals().get("studio_durum") or {}).get(ad) or {}
    taraniyor = bool(is_.get("calisiyor"))
    misafir = globals().get("_misafir_istek")
    if not tarandi and not taraniyor and kelime_var and request.args.get("tara", "1") != "0" and not is_.get("hata") \
            and not (misafir and misafir()) and float(d["veri"].get("sure") or 0) <= 7200:   # davetli sırasız iş başlatmasın; 2 sa üstü çok uzun
        kaynak, _ = _kaynak_video(temel)
        if kaynak is None and d["veri"].get("kayit") and Path(d["veri"]["kayit"]).is_file():
            kaynak = Path(d["veri"]["kayit"])
        baslat = globals().get("_studio_is")
        if kaynak and baslat:
            def _tara(log, _k=kaynak):
                r = subprocess.run([str(KLASOR / ".venv/bin/python"), "-u", str(KLASOR / "dolgu.py"), temel, str(_k)], cwd=str(KLASOR), env=_env(),
                                   capture_output=True, text=True, timeout=3 * 3600)
                if r.returncode != 0:
                    raise RuntimeError((r.stderr or r.stdout or "").strip()[-300:] or "Duraksamalar aranamadı.")
            taraniyor = bool(baslat(ad, _tara))
    return jsonify({"aralıklar": ar, "kelime_zamani_var": kelime_var, "taraniyor": taraniyor, "tarandi": tarandi,
                    "hata": is_.get("hata") or ""})


klip_calisan = set()


@app.post("/api/klipler/<temel>")
def klipler_sec(temel):
    t = _temel_dogrula(temel)
    if not ozet_modulu.hazir():
        return jsonify({"hata": "Yapay zekâ modeli hazır değil."}), 503
    if temel in klip_calisan:
        return jsonify({"hata": "Zaten seçiliyor."}), 409
    klip_calisan.add(temel)
    try:
        import klipler as klipler_modulu
        with kilit, _yz_baglam(json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))["veri"]):
            secilen = klipler_modulu.sec(t.with_suffix(".json"), log=lambda *_: None)
        return jsonify({"klipler": secilen})
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": f"Seçilemedi: {e}"}), 500
    finally:
        klip_calisan.discard(temel)


@app.get("/api/kaynak-video/<temel>")
def kaynak_video(temel):
    _temel_dogrula(temel)
    k, v = _kaynak_video(temel)
    return jsonify({"var": bool(k), "ad": k.name if k else "", "link": (v or {}).get("link", "")})



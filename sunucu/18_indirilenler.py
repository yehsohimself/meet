# sunucu/18_indirilenler.py — indirilenler, kapaklar, açılış temizliği.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- indirilenler
MEDYA_UZ = (".mp4", ".mp3", ".mkv", ".webm", ".m4a", ".mov")


def _indirilen_dogrula(dosya):
    if "/" in dosya or dosya.startswith(".") or not dosya.lower().endswith(MEDYA_UZ):
        abort(404)
    yol = INDIRILENLER / dosya
    if not yol.is_file():
        abort(404)
    return yol


@app.get("/api/indirilenler")
def indirilenler():
    if not INDIRILENLER.exists():
        return jsonify([])
    dizin = _dizin_oku()
    sonuc = []
    for f in INDIRILENLER.iterdir():
        if not f.is_file() or f.name.startswith(".") or not f.name.lower().endswith(MEDYA_UZ):
            continue
        d = dizin.get(f.name, {})
        kap = INDIRILENLER / ".kapaklar" / f"{f.stem}.jpg"
        sonuc.append({"ad": f.name, "yol": str(f), "boyut": f.stat().st_size, "baslik": d.get("baslik") or f.stem,
                      "kanal": d.get("kanal", ""), "link": d.get("link", ""), "kalite": d.get("kalite", ""),
                      "kesit": d.get("kesit", ""), "sure": d.get("sure", 0), "cozunurluk": d.get("cozunurluk", ""),
                      "platform": d.get("platform", ""), "olusturma": d.get("olusturma") or f.stat().st_mtime,
                      "dil": d.get("dil", ""), "temel": d.get("temel", ""), "misafir": d.get("misafir", ""), "kaynak_durum": _kaynak_durumu(d.get("temel", ""), d.get("kaynak_imza", "")),
                      "kapak": f"/indirilen-kapak/{f.stem}.jpg" if kap.exists() else "",
                      "ses": f.suffix.lower() in (".mp3", ".m4a")})
    sonuc.sort(key=lambda x: -x["olusturma"])
    return jsonify(sonuc)


@app.get("/indirilen/<path:dosya>")
def indirilen(dosya):
    _indirilen_dogrula(dosya)
    oynat = request.args.get("oynat") == "1"
    return send_from_directory(str(INDIRILENLER), dosya, as_attachment=not oynat, conditional=True)


@app.get("/indirilen-kapak/<path:dosya>")
def indirilen_kapak(dosya):
    if "/" in dosya or not dosya.lower().endswith(".jpg") or not (INDIRILENLER / ".kapaklar" / dosya).is_file():
        abort(404)
    return send_from_directory(str(INDIRILENLER / ".kapaklar"), dosya, max_age=86400)


@app.delete("/api/indirilen/<path:dosya>")
def indirilen_sil(dosya):
    yol = _indirilen_dogrula(dosya)
    COP.mkdir(exist_ok=True)
    shutil.move(str(yol), str(COP / f"indirilen__{yol.name}"))
    jpg = INDIRILENLER / f"{yol.stem}.jpg"
    if jpg.exists():
        shutil.move(str(jpg), str(COP / f"indirilen__{jpg.name}"))
    return jsonify({"tamam": True})


@app.get("/api/dudak/tahmin/<path:dosya>")
def dudak_tahmin(dosya):
    """Dudak senkronu öncesi onay penceresi için: süre ve tahmini üst sınır ücret (sync.so lipsync-2-pro)."""
    import dudak as dudak_modulu
    yol = _indirilen_dogrula(dosya)
    sn = dudak_modulu.sure(yol)
    return jsonify({"sure": sn, "maliyet": dudak_modulu.maliyet(sn), "bagli": dudak_modulu.hazir(), "model": dudak_modulu.MODEL})


@app.post("/api/indirilen-geri/<path:dosya>")
def indirilen_geri(dosya):
    if "/" in dosya or dosya.startswith("."):
        abort(404)
    geldi = 0
    for ad in (dosya, Path(dosya).stem + ".jpg"):
        f = COP / f"indirilen__{ad}"
        if f.exists():
            INDIRILENLER.mkdir(exist_ok=True)
            shutil.move(str(f), str(INDIRILENLER / ad)); geldi += 1
    return jsonify({"tamam": geldi > 0})


@app.post("/api/indirilenler-goster")
def indirilenler_goster():
    if not INDIRILENLER.exists():
        return jsonify({"hata": "Klasör henüz yok."}), 404
    subprocess.Popen(["/usr/bin/open", str(INDIRILENLER)])
    return jsonify({"tamam": True})


@app.post("/api/indirilen-goster/<path:dosya>")
def indirilen_goster(dosya):
    yol = _indirilen_dogrula(dosya)
    subprocess.Popen(["/usr/bin/open", "-R", str(yol)])
    return jsonify({"tamam": True})


@app.get("/kare/<temel>/<dosya>")
def kare(temel, dosya):
    if not re.match(r"^[\w\-]+$", temel) or not re.match(r"^k_\d+\.jpg$", dosya):
        abort(404)
    yol = KLASOR / "kareler" / temel
    if not (yol / dosya).exists():
        abort(404)
    return send_from_directory(str(yol), dosya, max_age=86400)


@app.get("/medya/<temel>")
def medya(temel):
    """Okuma görünümündeki oynatıcı için yerel ses/video (toplantı kaydı, yüklenen dosya ya da indirilmiş kopya). Range destekli."""
    if not re.match(r"^[\w\-]+$", temel):
        abort(404)
    yol, v = _kaynak_video(temel)
    if not yol and v:
        link = v.get("link") or ""
        if link and not re.match(r"^https?://", link) and Path(link).is_file():
            yol = Path(link)
    if not yol or not Path(yol).is_file():
        abort(404)
    from flask import send_file
    return send_file(str(yol), conditional=True, max_age=3600)


_ornek_kilit = threading.Lock()


@app.get("/altyazi-ornek/<stil>.mp4")
def altyazi_ornek(stil):
    """Altyazı stilinin 6 sn'lik sessiz örneği; ?font=&renk= verilirse o seçimle bir kez üretilir ve saklanır (aynı anda tek üretim)."""
    if stil not in ("kutu", "sade", "karaoke", "pop", "vurgu"):
        abort(404)
    font = re.sub(r"[^a-z]", "", request.args.get("font") or "")[:12]
    renk = re.sub(r"[^0-9a-fA-F]", "", request.args.get("renk") or "")[:6].lower()
    ornek = KLASOR / "static" / "altyazi_ornek"
    if not font and not renk:
        return send_from_directory(str(ornek), f"{stil}.mp4", max_age=86400)
    on = KLASOR / ".onbellek" / "altyazi_ornek"
    on.mkdir(parents=True, exist_ok=True)
    hedef = on / f"{stil}_{font or 'sistem'}_{renk or 'x'}.mp4"
    with _ornek_kilit:
        if not hedef.exists():
            ham = on / f"_ham_{hedef.name}"
            komut = ["/usr/bin/nice", "-n", "10", PYTHON, str(YAKMA_SCRIPT), str(ornek / "kaynak.json"), "--video", str(ornek / "kaynak.mp4"),
                     "--stil", stil, "--kesit", "0:00-0:07", "--cikti", str(ham)]
            if font:
                komut += ["--font", font]
            if len(renk) == 6:
                komut += ["--renk", renk]
            subprocess.run(komut, capture_output=True, timeout=120, cwd=str(KLASOR))
            if not ham.exists():
                abort(500)
            if subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(ham), "-an", "-vf", "scale=1280:-2", "-c:v", "h264_videotoolbox", "-b:v", "4M",
                               "-movflags", "+faststart", str(hedef)], capture_output=True, timeout=120).returncode != 0:
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(ham), "-an", "-vf", "scale=1280:-2", "-c:v", "libx264", "-crf", "21",
                                "-preset", "veryfast", "-movflags", "+faststart", str(hedef)], capture_output=True, timeout=120)
            ham.unlink(missing_ok=True)
    return send_from_directory(str(on), hedef.name, max_age=86400)


@app.get("/kapak/<dosya>")
def kapak(dosya):
    """?w=320: kitaplık kartı için küçük kopya (.onbellek/kapak_k/; 2026-10-25: 200 px'lik kart 1280 px / 120 KB görsel yüklüyordu)."""
    if not re.match(r"^[\w\-]+\.jpg$", dosya) or not (KLASOR / dosya).exists():
        abort(404)
    if request.args.get("w") == "320":
        kl = KLASOR / ".onbellek" / "kapak_k"; kl.mkdir(parents=True, exist_ok=True)
        kucuk = kl / dosya
        if not kucuk.exists() or kucuk.stat().st_mtime < (KLASOR / dosya).stat().st_mtime:
            subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(KLASOR / dosya), "-vf", "scale=320:-2", "-q:v", "6", str(kucuk)], capture_output=True, timeout=30)
        if kucuk.exists():
            return send_from_directory(str(kl), dosya, max_age=604800)
    return send_from_directory(str(KLASOR), dosya, max_age=86400)


_cop_temizle()


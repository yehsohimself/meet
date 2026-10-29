# sunucu/25_sahip_uzak.py — Meet'e dışarıdan kendi telefonunuzla (2026-10-25; kullanıcı: "Meet'i mobil app veya mobil browserda da denemek istiyorum ama
# dışarıdayken, kendi wifi'ımda olmasa da"; seçim: kurulumsuz, eşleştirilmiş telefon).
# Davet linklerinin Cloudflare tüneli (127.0.0.1:8770) kullanılır; tünelin öbür ucu herkese açık bir adres olduğu için sahibin girişi bir PAROLA değil,
# Mac'teki Meet'te gösterilen tek kullanımlık QR ile eşleştirilmiş CİHAZDIR: QR (10 dk, tek kullanım) → telefona kalıcı, httponly, secure çerez `vh_sahip`
# (yalnız izi saklanır). Eşleştirilmiş cihaz 8770'te sahip sayılır (`_misafir_istek` sarmalanır → davetli kapısı devreye girmez) ama bazı işlemler
# yalnızca Mac'ten yapılabilir (UZAK_YASAK). Mac yeniden başlayınca tünelin adresi değişir: eşleştirilmiş telefon varsa yeni adres için tek kullanımlık
# giriş linki (24 sa) sahibin e-postasına gönderilir. Ana ekrana eklenen uygulama (iOS'ta Safari'den ayrı çerez kutusu) cihaza özel `start_url` ile girer.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
import secrets

SAHIP_DOSYA = MISAFIR_KLASOR / "sahip_cihazlar.json"
UYANIK_ETIKET = "com.yehso.transkript.uyanik"
_sahip_kilit = threading.Lock()
UZAK_YASAK = ("/api/davetler", "/api/sahip-cihaz", "/api/guncelle", "/api/model-indir", "/api/claude/baglan", "/api/drive/baglan", "/api/drive-oku/baglan",
              "/api/studio-gelisim/guncelle", "/d/")
AYAR_YASAK = ("ag_paylasimi", "erisim_pin")                      # uzaktan değiştirilemeyen ayarlar


def _sahip_oku():
    try:
        return json.loads(SAHIP_DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"cihazlar": [], "esles": {}}


def _sahip_yaz(d):
    MISAFIR_KLASOR.mkdir(exist_ok=True)
    tmp = SAHIP_DOSYA.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(SAHIP_DOSYA)


def _siz(s):
    return hashlib.sha256(("vh-sahip|" + s).encode()).hexdigest()


def _tunel_portu():
    try:
        return str(request.environ.get("SERVER_PORT")) == str(MISAFIR_PORT)
    except RuntimeError:
        return False


def _sahip_cihaz():
    """Bu istek eşleştirilmiş sahip telefonundan mı (8770 + geçerli `vh_sahip` çerezi)? Döner: cihaz kaydı ya da None. İstek başına bir kez bakılır."""
    if not _tunel_portu():
        return None
    if "sahip_cihaz" in g:
        return g.sahip_cihaz
    c = request.cookies.get("vh_sahip", "")
    k = None
    if len(c) >= 30:
        iz = _siz(c)
        k = next((x for x in _sahip_oku()["cihazlar"] if iz in (x.get("izler") or [x.get("iz")]) and x.get("aktif", True)), None)
        if k and time.time() - (k.get("son_giris") or 0) > 300:
            with _sahip_kilit:
                d = _sahip_oku()
                for x in d["cihazlar"]:
                    if x["id"] == k["id"]:
                        x["son_giris"] = time.time()
                _sahip_yaz(d)
    g.sahip_cihaz = k
    return k


_misafir_istek_davetli = _misafir_istek


def _misafir_istek():   # noqa: F811 — eşleştirilmiş sahip telefonu davetli değildir; eşleştirme adresleri kendi denetimini yapar (tek kullanımlık anahtar)
    if not _misafir_istek_davetli():
        return False
    try:
        if request.path.startswith("/s/"):
            return False
    except RuntimeError:
        pass
    return not _sahip_cihaz()


def _sahip_sayfa(urun):
    html = (Path(app.static_folder) / "index.html").read_text(encoding="utf-8")
    html = html.replace("<html", f'<html data-urun="{urun}" data-uzak="1"', 1)
    html = html.replace('<link rel="manifest" href="/static/manifest.webmanifest">', '<link rel="manifest" href="/sahip-manifest.webmanifest">', 1)
    html = html.replace("</body>", '<script src="/static/sahip_uzak.js?v=1"></script></body>', 1)
    r = make_response(html)
    r.headers["Cache-Control"] = "no-store"
    return r


def _sahip_uzak_kapi():
    """Tünel portunda, davetli kapısından ÖNCE çalışır: eşleştirilmiş telefona sahip sayfası; yasaklı işlemler yalnızca Mac'ten."""
    if not _tunel_portu() or request.path.startswith("/s/") or request.path == "/sahip-manifest.webmanifest":
        return None
    k = _sahip_cihaz()
    if not k:
        return None
    if request.path.startswith(UZAK_YASAK):
        return _red(403, "Bu işlem yalnızca Mac'ten yapılabilir.")
    if request.method == "POST" and request.path == "/api/ayarlar" and any(a in (request.get_json(silent=True) or {}) for a in AYAR_YASAK):
        return _red(403, "Ağ paylaşımı ve PIN yalnızca Mac'ten değiştirilebilir.")
    if request.path in ("/", "/index.html"):
        return _sahip_sayfa("transcript" if request.args.get("u") == "studio" else "note")
    return None


app.before_request_funcs.setdefault(None, []).insert(0, _sahip_uzak_kapi)


# ---------------------------------------------------------------------------- eşleştirme (telefon)
def _cihaz_cerezi(r, sir):
    https = request.headers.get("X-Forwarded-Proto") == "https" or request.host.endswith(".trycloudflare.com")
    r.set_cookie("vh_sahip", sir, max_age=400 * 86400, httponly=True, samesite="Lax", secure=https)
    return r


def _esles_onay_sayfasi(urun):
    """Tek kullanımlık link GET'te harcanmaz: mesaj uygulamalarının bağlantı önizlemesi (iMessage, WhatsApp, Mail) linki kullanıcıdan önce açıp
    hakkı harcıyordu (2026-10-28: telefon 'eşleşti' göründü ama sayfa açılmadı). Eşleşme yalnız bu sayfadaki düğmeyle (POST) olur."""
    import html as _h
    ad = "PT" if urun == "pt" else "Meet"
    eylem = _h.escape(request.full_path.rstrip("?"))
    return (f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{ad}</title><style>body{{font-family:-apple-system,Manrope,sans-serif;background:#08080a;color:#eee;display:grid;
place-items:center;min-height:100vh;margin:0;padding:24px;box-sizing:border-box}}div{{max-width:420px;text-align:center}}h1{{font-size:34px;margin:0 0 12px}}
p{{color:#a1a1a6;line-height:1.5;margin:0 0 24px}}button{{font:inherit;font-weight:700;font-size:17px;border:0;border-radius:14px;padding:15px 28px;width:100%;
background:{'#C4F23A' if urun == 'pt' else '#FF5F1F'};color:{'#142004' if urun == 'pt' else '#fff'}}}</style></head>
<body><div><h1>{ad}</h1><p>Bu telefonu {ad}'ye bağlamak için dokunun.</p><form method="post" action="{eylem}"><button type="submit">Bu telefonu bağla</button></form></div></body></html>""",
            200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})


@app.route("/s/<token>", methods=["GET", "POST"])
def sahip_esles(token):
    if not _tunel_portu():
        abort(404)
    if request.method == "GET":
        with _sahip_kilit:
            e = _sahip_oku()["esles"].get(_siz(token)) if len(token) >= 30 else None
        if not e or e.get("bitis", 0) < time.time():
            return _sayfa("Meet", "Bu eşleştirme linki geçersiz ya da süresi dolmuş. Mac'teki Meet'te Ayarlar → Telefonum'dan yeni bir QR alın.", 403)
        return _esles_onay_sayfasi(request.args.get("u"))
    with _sahip_kilit:
        d = _sahip_oku()
        e = d["esles"].pop(_siz(token), None) if len(token) >= 30 else None
        d["esles"] = {k: v for k, v in d["esles"].items() if v.get("bitis", 0) > time.time()}
        if not e or e.get("bitis", 0) < time.time():
            _sahip_yaz(d)
            return _sayfa("Meet", "Bu eşleştirme linki geçersiz ya da süresi dolmuş. Mac'teki Meet'te Ayarlar → Telefonum'dan yeni bir QR alın.", 403)
        sir = secrets.token_urlsafe(32); giris = secrets.token_urlsafe(32)
        ad = e.get("ad") or "Telefon"
        if e.get("yenile"):                                    # adres değişince e-postayla gelen link: aynı adlı eski kayıt yenilenir
            d["cihazlar"] = [x for x in d["cihazlar"] if x.get("ad") != ad]
        d["cihazlar"].append({"id": secrets.token_hex(4), "ad": ad, "izler": [_siz(sir)], "giris": giris, "olusturma": time.time(), "son_giris": time.time(), "aktif": True})
        _sahip_yaz(d)
    _bildir("Meet: telefon eşleştirildi", f"{ad} artık Meet'e dışarıdan girebilir.", url=MEET_ADRES)
    return _cihaz_cerezi(make_response(redirect("/", 303)), sir)


@app.get("/s/g/<giris>")
def sahip_giris(giris):
    """Ana ekrana eklenen uygulamanın başlangıç adresi (iOS'ta ana ekran uygulaması Safari'nin çerezini görmez)."""
    if not _tunel_portu() or len(giris) < 30:
        abort(404)
    with _sahip_kilit:
        d = _sahip_oku()
        k = next((x for x in d["cihazlar"] if x.get("giris") == giris and x.get("aktif", True)), None)
        if not k:
            return _sayfa("Meet", "Bu telefonun girişi kaldırılmış. Mac'teki Meet'te Ayarlar → Telefonum'dan yeniden eşleştirin.", 403)
        sir = secrets.token_urlsafe(32); k["son_giris"] = time.time()
        k["izler"] = ((k.get("izler") or ([k["iz"]] if k.get("iz") else [])) + [_siz(sir)])[-4:]   # Safari ve ana ekran uygulaması ayrı çerez tutar (iOS)
        k.pop("iz", None)
        _sahip_yaz(d)
    return _cihaz_cerezi(make_response(redirect("/")), sir)


@app.get("/sahip-manifest.webmanifest")
def sahip_manifest():
    k = _sahip_cihaz()
    if not k:
        abort(404)
    m = json.loads((Path(app.static_folder) / "manifest.webmanifest").read_text(encoding="utf-8"))
    m.update({"name": "Meet", "short_name": "Meet", "start_url": f"/s/g/{k['giris']}", "scope": "/", "theme_color": "#08080a", "background_color": "#08080a"})
    r = make_response(json.dumps(m, ensure_ascii=False))
    r.headers.update({"Content-Type": "application/manifest+json", "Cache-Control": "no-store"})
    return r


# ---------------------------------------------------------------------------- sahibin uçları (Mac'ten; tünelde UZAK_YASAK ve davetli kapısı kapalı tutar)
def _yalniz_mac():
    if _tunel_portu():
        abort(403)


def _uyanik_calisiyor():
    try:
        r = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{UYANIK_ETIKET}"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and "state = running" in r.stdout
    except Exception:  # noqa: BLE001
        return False


@app.get("/api/sahip-cihaz")
def sahip_cihaz_listesi():
    _yalniz_mac()
    ay = ayarlar_oku()
    return jsonify({"cihazlar": [{k: x.get(k) for k in ("id", "ad", "olusturma", "son_giris")} for x in _sahip_oku()["cihazlar"] if x.get("aktif", True)],
                    "tunel": _tunel_calisiyor(), "adres": tunel_adresi() if _tunel_calisiyor() else "",
                    "eposta": ay.get("sahip_eposta", True), "alici": (ay.get("benim_epostalar") or [""])[0], "uyanik": _uyanik_calisiyor()})


@app.post("/api/sahip-cihaz/esles")
def sahip_cihaz_esles():
    """Tek kullanımlık eşleştirme QR'ı (10 dk). Döner: link ve QR (SVG)."""
    _yalniz_mac()
    if not _tunel_calisiyor() or not tunel_adresi():
        return _red(400, "Dış bağlantı kapalı; önce açın.")
    ad = re.sub(r"\s+", " ", str((request.get_json(silent=True) or {}).get("ad") or "Telefon")).strip()[:30] or "Telefon"
    token = secrets.token_urlsafe(24)
    with _sahip_kilit:
        d = _sahip_oku()
        d["esles"] = {k: v for k, v in d["esles"].items() if v.get("bitis", 0) > time.time()}
        d["esles"][_siz(token)] = {"ad": ad, "bitis": time.time() + 600}
        _sahip_yaz(d)
    link = f"{tunel_adresi()}/s/{token}"
    import io
    import segno
    b = io.BytesIO(); segno.make(link, error="m").save(b, kind="svg", scale=6, border=2, dark="#000", light="#fff")
    return jsonify({"link": link, "qr": b.getvalue().decode("utf-8"), "bitis": time.time() + 600})


@app.delete("/api/sahip-cihaz/<cid>")
def sahip_cihaz_sil(cid):
    _yalniz_mac()
    with _sahip_kilit:
        d = _sahip_oku()
        d["cihazlar"] = [x for x in d["cihazlar"] if x.get("id") != cid]
        _sahip_yaz(d)
    return jsonify({"tamam": True})


@app.post("/api/sahip-cihaz/ayar")
def sahip_cihaz_ayar():
    """{eposta}: adres değişince yeni giriş linki e-postaya; {uyanik}: prizdeyken Mac uyumasın (caffeinate -s giriş ajanı; kapak kapalıyken yine uyur)."""
    _yalniz_mac()
    v = request.get_json(silent=True) or {}
    if "eposta" in v:
        ay = ayarlar_oku(); ay["sahip_eposta"] = bool(v["eposta"]); ayarlar_yaz(ay)
    if "uyanik" in v:
        uid = os.getuid(); plist = Path.home() / "Library" / "LaunchAgents" / f"{UYANIK_ETIKET}.plist"
        subprocess.run(["/bin/launchctl", "bootout", f"gui/{uid}/{UYANIK_ETIKET}"], capture_output=True, timeout=20)
        if v["uyanik"]:
            plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{UYANIK_ETIKET}</string>
<key>ProgramArguments</key><array><string>/usr/bin/caffeinate</string><string>-s</string><string>-i</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>""", encoding="utf-8")
            r = subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                return _red(500, "Açılamadı: " + (r.stderr or r.stdout).strip()[:160])
        else:
            plist.unlink(missing_ok=True)
    return jsonify({"tamam": True, "uyanik": _uyanik_calisiyor()})


# ---------------------------------------------------------------------------- tünel bekçisi
_tunel_adresi_davet = tunel_adresi


def tunel_adresi():   # noqa: F811 — adres yalnız açılışta bir kez yazılır; kayıt dosyası büyüyünce son 200 KB'ta kalmıyordu: bütün dosya
    a = _tunel_adresi_davet()
    if a:
        return a
    try:
        m = re.findall(r"https://[a-z0-9\-]+\.trycloudflare\.com", TUNEL_LOG.read_text(encoding="utf-8", errors="ignore"))
        return m[-1] if m else ""
    except Exception:  # noqa: BLE001
        return ""


def _tunel_bekci():
    """Hesapsız tünel Cloudflare tarafında kapanabiliyor (25 Ekim: saatlerce 'Unauthorized: Tunnel not found', davet linkleri ve telefon girişi ölüydü).
    Kaydın sonunda bu hata sürüyorsa tünel yeniden başlatılır; yeni adres _adres_izle / _sahip_adres_izle ile bildirilir."""
    try:
        if not _tunel_calisiyor():
            return
        with open(TUNEL_LOG, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 6000))
            son = f.read().decode("utf-8", "ignore")
        if son.count("Tunnel not found") >= 3 and "Registered tunnel connection" not in son.split("Tunnel not found")[-1]:
            TUNEL_LOG.write_text("", encoding="utf-8")
            subprocess.run(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{TUNEL_ETIKET}"], capture_output=True, timeout=20)
            print("Tünel Cloudflare'de kapanmıştı; yeniden başlatıldı", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"Tünel bekçisi: {e}", flush=True)


# ---------------------------------------------------------------------------- adres değişince: tek kullanımlık giriş linki e-postaya
def _sahip_adres_izle():
    iz = MISAFIR_KLASOR / ".sahip_son_adres"
    time.sleep(90)
    while True:
        _tunel_bekci()
        try:
            a = tunel_adresi() if _tunel_calisiyor() else ""
            eski = iz.read_text(encoding="utf-8").strip() if iz.exists() else ""
            if a and a != eski:
                MISAFIR_KLASOR.mkdir(exist_ok=True); iz.write_text(a, encoding="utf-8")
                cihazlar = [x for x in _sahip_oku()["cihazlar"] if x.get("aktif", True)]
                ay = ayarlar_oku(); alici = (ay.get("benim_epostalar") or [""])[0]
                if eski and cihazlar and ay.get("sahip_eposta", True) and alici:
                    son = max(cihazlar, key=lambda x: x.get("son_giris") or 0)
                    token = secrets.token_urlsafe(24)
                    with _sahip_kilit:
                        d = _sahip_oku(); d["esles"][_siz(token)] = {"ad": son.get("ad") or "Telefon", "bitis": time.time() + 86400, "yenile": True}; _sahip_yaz(d)
                    import notlar as notlar_modulu
                    hata = notlar_modulu.gonder("Meet: telefonunuz için yeni giriş",
                                                "Mac yeniden başladığı için Meet'in dış adresi değişti. Telefonunuzda bu linke bir kez dokunun; Meet yeniden açılır:\n\n"
                                                f"{a}/s/{token}\n\nLink 24 saat geçerli ve tek kullanımlıktır. Başkasıyla paylaşmayın.", alici, alici)
                    _bildir("Meet'in dış adresi değişti", "Telefonunuz için yeni giriş linki e-postanıza gönderildi." if not hata else "Yeni girişi Mac'teki Meet → Ayarlar → Telefonum'dan alın.")
        except Exception as e:  # noqa: BLE001
            print(f"Sahip adres izleme: {e}", flush=True)
        time.sleep(120)


threading.Thread(target=_sahip_adres_izle, daemon=True).start()

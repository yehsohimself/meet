# sunucu/05_asana.py — Asana.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- Asana (yalnızca kendi görevleri)
asana_onbellek = {}


def _asana(yol, method="GET", govde=None):
    """Asana REST çağrısı; kişisel erişim belirteci ayarlardan. Döner: data (dict/list)."""
    import urllib.request
    tok = ayarlar_oku().get("asana_token")
    if not tok:
        raise RuntimeError("Asana bağlı değil")
    req = urllib.request.Request("https://app.asana.com/api/1.0" + yol, method=method,
                                 data=json.dumps({"data": govde}).encode("utf-8") if govde is not None else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("data")
    except urllib.error.HTTPError as e:
        try:
            mesaj = json.load(e).get("errors", [{}])[0].get("message", "")
        except Exception:  # noqa: BLE001
            mesaj = ""
        raise RuntimeError(f"Asana {e.code}: {mesaj or e.reason}")


def _asana_ben():
    """Kullanıcı ve çalışma alanı (10 dk önbellek)."""
    if asana_onbellek.get("zaman", 0) > time.time() - 600:
        return asana_onbellek["ben"]
    me = _asana("/users/me?opt_fields=name,email,workspaces.name")
    ws = me.get("workspaces") or []
    secili = ayarlar_oku().get("asana_ws") or ASANA_CL_WS
    alan = next((w for w in ws if w.get("gid") == secili), ws[0] if ws else None)
    ben = {"ad": me.get("name"), "eposta": me.get("email"), "gid": me.get("gid"),
           "alan": alan, "alanlar": [{"gid": w.get("gid"), "ad": w.get("name")} for w in ws]}
    asana_onbellek.update({"zaman": time.time(), "ben": ben})
    return ben


@app.get("/api/asana")
def asana_get():
    if not ayarlar_oku().get("asana_token"):
        return jsonify({"bagli": False})
    try:
        ben = _asana_ben()
        return jsonify({"bagli": True, "kullanici": ben["ad"], "eposta": ben["eposta"],
                        "alan": (ben["alan"] or {}).get("name"), "alan_gid": (ben["alan"] or {}).get("gid"), "alanlar": ben["alanlar"]})
    except Exception as e:  # noqa: BLE001
        return jsonify({"bagli": False, "hata": str(e)})


@app.post("/api/asana/gorev/<temel>")
def asana_gorev(temel):
    """Seçilen yapılacakları Asana'da KENDİNE atanmış görev olarak açar (başkasına atama yok)."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    v = request.get_json(force=True) or {}
    maddeler = [str(m).strip() for m in (v.get("maddeler") or []) if str(m).strip()][:30]
    if not maddeler:
        return jsonify({"hata": "Seçili madde yok."}), 400
    try:
        ben = _asana_ben()
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": str(e)}), 400
    if not ben["alan"]:
        return jsonify({"hata": "Asana hesabında çalışma alanı bulunamadı."}), 400
    d = json.loads(tj.read_text(encoding="utf-8"))
    veri = d["veri"]; mevcut = veri.setdefault("asana", {})
    baslik = veri.get("baslik") or temel
    tarih = time.strftime("%d.%m.%Y", time.localtime(veri.get("olusturma") or time.time()))
    sonuc, hatalar = [], []
    for m in maddeler:
        if m in mevcut:
            sonuc.append({"madde": m, **mevcut[m]}); continue
        try:
            g = _asana("/tasks", "POST", {"name": m[:250], "assignee": "me", "workspace": ben["alan"]["gid"],
                                           "notes": f"Toplantı: {baslik} ({tarih})\nKaynak: Transkript"})
            kayit = {"gid": g.get("gid"), "url": g.get("permalink_url") or f"https://app.asana.com/0/0/{g.get('gid')}", "tarih": time.time()}
            mevcut[m] = kayit; sonuc.append({"madde": m, **kayit})
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{m[:40]}: {e}")
    tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify({"eklenen": sonuc, "hatalar": hatalar})


@app.post("/api/notlar/<temel>")
def notlar_post(temel):
    """Toplantı notlarını (yoksa) üretir ve istenirse e-postayla gönderir."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    v = request.get_json(silent=True) or {}
    import notlar as notlar_modulu
    d = json.loads(tj.read_text(encoding="utf-8")); veri = d["veri"]
    if not veri.get("notlar") or v.get("yenile"):
        n = notlar_modulu.uret(veri, d["segmentler"], temel, log=lambda *_: None)
        if not n:
            return jsonify({"hata": "Notlar üretilemedi (özet modeli hazır mı?)."}), 500
        veri["notlar"] = n
        (KLASOR / f"{temel}.notlar.txt").write_text(notlar_modulu.metin(veri, n), encoding="utf-8")
    sonuc = {"notlar": veri["notlar"], "metin": notlar_modulu.metin(veri, veri["notlar"])}
    ay = ayarlar_oku()
    if v.get("gonder"):
        alici = (v.get("alici") or "").strip() or notlar_modulu.alici_sec(veri, ay)
        hata = notlar_modulu.gonder(f"Toplantı notları · {veri.get('baslik')}", sonuc["metin"], alici, alici) if alici else "alıcı adresi yok"
        veri["notlar_gonderim"] = {"alici": alici, "zaman": time.time(), "hata": hata}
        sonuc["gonderim"] = veri["notlar_gonderim"]
    with kilit:
        tj.write_text(json.dumps({"veri": veri, "segmentler": d["segmentler"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify(sonuc)


@app.get("/api/takvim")
def takvim_get():
    ay = ayarlar_oku()
    if not ay.get("takvim_ics"):
        return jsonify({"bagli": False})
    try:
        import takvim as takvim_modulu
        metin = takvim_modulu.ics_getir(zorla=bool(request.args.get("yenile")))
        if not metin:
            return jsonify({"bagli": True, "hata": "Takvim adresine ulaşılamadı."})
        return jsonify({"bagli": True, "yaklasan": takvim_modulu.yaklasan(metin, saat=24)[:6], "etkinlik": len(takvim_modulu.etkinlikler(metin)),
                        "takvimler": takvim_modulu.durum()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"bagli": True, "hata": str(e)})


@app.post("/api/takvim/ekle")
def takvim_ekle():
    """Var olanları silmeden bir takvim daha ekler (2026-10-23: iş takvimleri; eskiden ikinciyi eklemek için hepsini kaldırmak gerekiyordu)."""
    import takvim as takvim_modulu
    url = str((request.get_json(silent=True) or {}).get("url") or "").strip()
    try:
        ad, n = takvim_modulu.dogrula(url)
    except ValueError as e:
        print(f"Takvim eklenemedi: {e} (adres {urllib.parse.urlparse(url).netloc or 'geçersiz'})", flush=True)   # gizli adresin kendisi yazılmaz
        return jsonify({"hata": str(e)}), 400
    d = ayarlar_oku()
    var = takvim_modulu.adresler(d.get("takvim_ics") or "")
    if url in var:
        return jsonify({"hata": "Bu takvim zaten bağlı"}), 400
    d["takvim_ics"] = "\n".join(var + [url])
    ayarlar_yaz(d)
    takvim_modulu.ONBELLEK.unlink(missing_ok=True)
    return jsonify({"tamam": True, "ad": ad, "etkinlik": n, "takvimler": takvim_modulu.durum()})


@app.post("/api/takvim/kaldir")
def takvim_kaldir():
    import takvim as takvim_modulu
    try:
        no = int((request.get_json(silent=True) or {}).get("no"))
    except (TypeError, ValueError):
        return jsonify({"hata": "geçersiz"}), 400
    d = ayarlar_oku()
    var = takvim_modulu.adresler(d.get("takvim_ics") or "")
    if not 0 <= no < len(var):
        return jsonify({"hata": "bulunamadı"}), 404
    var.pop(no)
    d["takvim_ics"] = "\n".join(var)
    ayarlar_yaz(d)
    takvim_modulu.ONBELLEK.unlink(missing_ok=True)
    return jsonify({"tamam": True, "takvimler": takvim_modulu.durum() if var else []})


@app.get("/api/takvim/gun")
def takvim_gun_get():
    """Bugünün takvim etkinlikleri (Transcript 'Bugün' akışı); takvim bağlı değilse boş liste."""
    if not ayarlar_oku().get("takvim_ics"):
        return jsonify({"bagli": False, "etkinlikler": []})
    try:
        import takvim as takvim_modulu
        metin = takvim_modulu.ics_getir()
        return jsonify({"bagli": True, "etkinlikler": takvim_modulu.gun(metin), "siradaki": takvim_modulu.siradaki(metin), "suren": SUREN_GORUSME.get("e")})
    except Exception as e:  # noqa: BLE001
        return jsonify({"bagli": True, "etkinlikler": [], "hata": str(e)})



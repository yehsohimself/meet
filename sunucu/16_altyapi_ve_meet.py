# sunucu/16_altyapi_ve_meet.py — altyapı (yedek, sistem durumu), sohbet, haftalık özet, kanal takibi, ayarlar, sil/geri. Meet uçları 16_meet.py'de (2026-10-25).
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- altyapı: yedek, kayıt döndürme, sistem durumu
def _kayit_dondur(sinir_mb=5):
    """Büyüyen kayıt dosyalarını kopyalayıp sıfırlar (launchd dosyayı açık tuttuğu için taşımak yerine kopyala + kes); son 2 eski tutulur."""
    adaylar = [KLASOR / "site.log", KLASOR / "kaydedici" / "kaydedici.log"] + list((KAYIT / ".canli").glob("*.log"))
    for f in adaylar:
        try:
            if f.exists() and f.stat().st_size > sinir_mb * 1e6:
                eski1, eski2 = f.with_name(f.name + ".1"), f.with_name(f.name + ".2")
                if eski1.exists():
                    eski1.replace(eski2)
                shutil.copy2(f, eski1)
                with open(f, "r+b") as h:
                    h.truncate(0)
        except Exception as e:  # noqa: BLE001
            print(f"Kayıt döndürme hatası ({f.name}): {e}", flush=True)


def _altyapi_dongu():
    """15 dk'da bir: kayıt döndürme; gece 03.00'ten sonra günde bir yedek (yedek.py → Drive/Video Hub Yedek, son 10)."""
    time.sleep(60)
    while True:
        try:
            _kayit_dondur()
            try:
                import atolye_kaynak                       # Couple kurulu değilse yok (2026-10-25)
                atolye_kaynak.onbellek_temizle()
            except ImportError:
                pass
            # yarım kalmış yazıya dökme işlerinin ara dosyaları ("Kaldığı yerden dene" için) 7 gün saklanır
            for d in (KLASOR / ".onbellek" / "is").glob("*"):
                if d.is_dir() and time.time() - d.stat().st_mtime > 7 * 86400 and not any(
                        x.get("durum") in ("sirada", "calisiyor") for x in isler.values()):
                    shutil.rmtree(d, ignore_errors=True)
            import yedek as yedek_modulu
            son = yedek_modulu.son().get("zaman") or 0
            if time.localtime().tm_hour >= 3 and time.strftime("%Y-%m-%d", time.localtime(son)) != time.strftime("%Y-%m-%d"):
                yedek_modulu.yedekle(log=lambda m: print(m, flush=True))
            if time.localtime().tm_hour >= 3:                  # ödüllü işler arşivi Drive'dan haftada bir yenilenir (reklam_arsivi.py; Ghost/Couple kurulu değilse yok)
                try:
                    import reklam_arsivi
                    reklam_arsivi.tazele()
                except ImportError:
                    pass
        except Exception as e:  # noqa: BLE001
            print(f"Altyapı döngüsü hatası: {e}", flush=True)
        time.sleep(900)


threading.Thread(target=_altyapi_dongu, daemon=True).start()


@app.post("/api/yedek")
def yedek_simdi():
    import yedek as yedek_modulu
    try:
        return jsonify(yedek_modulu.yedekle(log=lambda m: None))
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": f"Yedeklenemedi: {str(e)[:150]}"}), 500


@app.post("/api/duman")
def duman_simdi():
    """Duman testi (derleme, birim, canlı uçlar); ayrı süreçte, ~30 sn."""
    r = subprocess.run([PYTHON, str(KLASOR / "duman_testi.py"), "hizli,birim,canli"], capture_output=True, text=True, timeout=300, cwd=str(KLASOR))
    return jsonify({"basarili": r.returncode == 0, "cikti": r.stdout.strip()[-1500:]})


@app.get("/api/sistem-durum")
def sistem_durum():
    """Gözlem paneli: disk, son yedek, son duman testi, arka plan öğrenmesi, son 7 günün işleri (adet, hata, ortalama süre), Claude kullanımı."""
    import yedek as yedek_modulu
    bos = shutil.disk_usage(str(KLASOR)).free / 1e9
    try:
        duman = json.loads((KAYIT / ".duman.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        duman = {}
    sinir = time.time() - 7 * 86400
    son_isler = [i for i in list(isler.values()) if (i.get("baslangic") or i.get("olusturma") or 0) > sinir]
    biten = [i for i in son_isler if i.get("durum") == "bitti" and i.get("baslangic") and i.get("bitis")]
    try:
        import claude_yaz
        claude = claude_yaz.kullanim_ozeti(7)
    except Exception:  # noqa: BLE001
        claude = {}
    import kalite
    try:
        import claude_yaz as _cy
        butce = {"son5saat": _cy.son_cagri_sayisi(5), "esik": int(ayarlar_oku().get("claude_arka_plan_esik") or _cy.ARKA_PLAN_ESIK),
                 "arka_plan_uygun": _cy.arka_plan_uygun()}
    except Exception:  # noqa: BLE001
        butce = {}
    return jsonify({"disk_bos_gb": round(bos, 1), "yedek": yedek_modulu.son(), "duman": duman, "kalite": kalite.ozet(30),
                    "ozellik": ozellik_kullanimi(30), "butce": butce, "pin": bool(ayarlar_oku().get("erisim_pin")),
                    "ag": bool(ayarlar_oku().get("ag_paylasimi")),
                    "bakim": {k: globals().get("bakim_durum", {}).get(k) for k in ("calisiyor", "kategori", "son_hata")},
                    "isler": {"toplam": len(son_isler), "hata": sum(1 for i in son_isler if i.get("durum") in ("hata", "kesildi")),
                              "ort_sn": round(sum(i["bitis"] - i["baslangic"] for i in biten) / len(biten)) if biten else None},
                    "claude": claude})


@app.get("/api/haftalik")
def haftalik_get():
    import haftalik
    return jsonify({"liste": haftalik.liste()[::-1][:12], "durum": haftalik_durum})


@app.get("/api/haftalik/<ad>")
def haftalik_oku(ad):
    import haftalik
    return jsonify({"md": haftalik.oku(ad)})


@app.post("/api/haftalik/<tur>")
def haftalik_uret(tur):
    if tur not in ("takip", "musteri"):
        abort(404)
    if haftalik_durum["calisiyor"]:
        return jsonify({"hata": "Bir özet zaten hazırlanıyor."}), 409
    gonder = bool((request.get_json(silent=True) or {}).get("gonder"))
    threading.Thread(target=_haftalik_calistir, args=(tur, gonder), daemon=True).start()
    return jsonify({"tamam": True})


@app.post("/api/haftalik-gonder/<ad>")
def haftalik_gonder(ad):
    import haftalik
    md = haftalik.oku(ad)
    if not md:
        abort(404)
    h = haftalik.eposta_gonder({"md": md, "baslik": ad})
    return jsonify({"hata": h}) if h else jsonify({"tamam": True})


@app.get("/ozet-indir/<ad>")
def ozet_indir(ad):
    if not re.match(r"^[\w ĞÜŞİÖÇğüşıöç\-]+\.docx$", ad) or not (OZETLER / ad).exists():
        abort(404)
    return send_from_directory(str(OZETLER), ad, as_attachment=True)


brief_durum = {}


@app.route("/api/sohbet/<temel>", methods=["GET", "POST", "DELETE"])
def toplanti_sohbet(temel):
    """Seçili toplantı/videoyla sohbet (sohbet.py). GET geçmiş, POST {soru} → yanıt, DELETE sohbeti temizler."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    if request.method == "GET":
        return jsonify(json.loads(tj.read_text(encoding="utf-8"))["veri"].get("sohbet") or [])
    if request.method == "DELETE":
        with kilit:
            d = json.loads(tj.read_text(encoding="utf-8")); d["veri"].pop("sohbet", None)
            tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return jsonify({"tamam": True})
    soru = str((request.get_json(silent=True) or {}).get("soru") or "").strip()[:2000]
    if not soru:
        return jsonify({"hata": "Soru boş"}), 400
    import sohbet
    gecmis = json.loads(tj.read_text(encoding="utf-8"))["veri"].get("sohbet") or []

    def _akis():
        # Yanıt yazıldıkça düz metin parçaları gider (Claude ekranı gibi); hata olursa "\x00HATA:" ile başlayan son parça
        parcalar = []
        try:
            for p in sohbet.cevapla_akis(tj, soru, gecmis):
                parcalar.append(p); yield p
        except Exception as e:  # noqa: BLE001
            yield "\x00HATA:" + str(e); return
        cevap = "".join(parcalar).strip()
        if not cevap:
            yield "\x00HATA:Yanıt alınamadı."; return
        with kilit:
            d = json.loads(tj.read_text(encoding="utf-8"))
            g = d["veri"].setdefault("sohbet", [])
            g += [{"rol": "ben", "metin": soru, "zaman": time.time()}, {"rol": "claude", "metin": cevap, "zaman": time.time()}]
            d["veri"]["sohbet"] = g[-200:]
            tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return Response(stream_with_context(_akis()), mimetype="text/plain; charset=utf-8", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


def _belge_yenile(temel):
    """txt/docx/srt yeniden yazılır; toplantı Drive'daysa Word ve metin kopyası da güncellenir (Kısaca/danışman sonradan eklenince)."""
    tj = KLASOR / f"{temel}.json"
    d = json.loads(tj.read_text(encoding="utf-8")); veri = d["veri"]
    with kilit:
        ciktilari_yaz(KLASOR / temel, veri, d["segmentler"])
    hedef = Path(veri.get("drive") or "")
    if veri.get("drive") and hedef.is_dir() and "_drive_kopya" in globals():
        for uz in ("docx", "txt"):
            if (KLASOR / f"{temel}.{uz}").exists():
                _drive_kopya(KLASOR / f"{temel}.{uz}", hedef / f"{hedef.name}.{uz}")


danisman_durum = {}


def _takip_json(k):
    return {kk: vv for kk, vv in k.items() if kk != "bilinen"} | {"bilinen_sayi": len(k.get("bilinen", []))}


@app.get("/api/takip")
def takip_listesi():
    return jsonify([_takip_json(k) for k in takip_modulu.oku()["kanallar"]])


@app.post("/api/takip")
def takip_ekle():
    v = request.get_json(force=True) or {}
    url = (v.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return jsonify({"hata": "Kanal ya da oynatma listesi linki girin."}), 400
    islem = v.get("islem") if v.get("islem") in ("ozet", "transkript") else "ozet"
    geriye = int(v.get("geriye") or 0) if str(v.get("geriye") or "0").isdigit() else 0
    try:
        kanal, hemen = takip_modulu.ekle(url, islem, min(geriye, 10))
    except Exception as e:  # noqa: BLE001
        m = str(e)
        if "404" in m or "does not exist" in m.lower() or "not found" in m.lower():
            m = "Kanal bulunamadı. Linki kanal sayfasından kopyalayın (örn. youtube.com/@kanal)."
        return jsonify({"hata": m.replace("ERROR:", "").strip()[:200]}), 400
    _takip_isle(kanal, hemen)
    return jsonify({"tamam": True, "kanal": _takip_json(kanal), "baslatilan": len(hemen)})


@app.post("/api/takip/<kid>/kontrol")
def takip_kontrol(kid):
    try:
        kanal, yeni = takip_modulu.kontrol(kid)
    except Exception as e:  # noqa: BLE001
        return jsonify({"hata": str(e)[:200]}), 400
    _takip_isle(kanal, yeni)
    return jsonify({"tamam": True, "yeni": len(yeni), "kanal": _takip_json(kanal)})


@app.post("/api/takip/<kid>")
def takip_guncelle(kid):
    v = request.get_json(force=True) or {}
    takip_modulu.guncelle(kid, **{k: v[k] for k in ("islem", "otomatik", "ad") if k in v})
    return jsonify({"tamam": True})


@app.delete("/api/takip/<kid>")
def takip_sil(kid):
    takip_modulu.sil(kid)
    return jsonify({"tamam": True})


@app.get("/api/ozet-durum/<temel>")
def ozet_durum(temel):
    return jsonify({"calisiyor": temel in ozet_calisan})


@app.get("/api/ayarlar")
def ayarlar_get():
    d = ayarlar_oku()
    d["ip"] = yerel_ip(); d["port"] = PORT; d["ozet_hazir"] = ozet_modulu.hazir()
    d.pop("asana_token", None)
    d["pexels_bagli"] = bool(d.get("pexels_anahtar")); d.pop("pexels_anahtar", None)
    d["sync_bagli"] = bool(d.get("sync_anahtar")); d.pop("sync_anahtar", None)
    d["youtube_api_bagli"] = bool(d.get("youtube_api_anahtar")); d.pop("youtube_api_anahtar", None)
    d["pin_var"] = bool(d.get("erisim_pin")); d.pop("erisim_pin", None)
    d["takvim_sayisi"] = len([u for u in (d.get("takvim_ics") or "").split("\n") if u.strip()])
    d["takvim_bagli"] = d["takvim_sayisi"] > 0; d["takvim_ics"] = f"{d['takvim_sayisi']} takvim" if d["takvim_bagli"] else ""
    d["ozet_model"] = ozet_modulu.MODEL
    try:
        import claude_yaz
        d["claude_durum"] = claude_yaz.durum(); d["claude_model"] = claude_yaz.model()
    except Exception:  # noqa: BLE001
        d["claude_durum"] = {"program": False, "giris": False, "kullanim": False}
    d["claude"] = d.get("claude", True); d["claude_toplanti"] = d.get("claude_toplanti", True); d["danisman"] = d.get("danisman", True)
    try:
        import ceviri as ceviri_modulu
        d["ceviri_model"] = ceviri_modulu._ceviri_modeli() or ozet_modulu.MODEL
    except Exception:  # noqa: BLE001
        d["ceviri_model"] = ozet_modulu.MODEL
    d["model_var"] = {m: _model_var(m) for m in MODEL_KLASORLERI}
    d["model_iniyor"] = {m: bool(model_iniyor.get(m)) for m in MODEL_KLASORLERI}
    return jsonify(d)


@app.post("/api/ayarlar")
def ayarlar_post():
    v = request.get_json(force=True) or {}
    d = ayarlar_oku()
    eski_ag = d.get("ag_paylasimi", False)
    if "ozet" in v:
        d["ozet"] = bool(v["ozet"])
    if v.get("ozet_dili") in ("tr", "auto"):
        d["ozet_dili"] = v["ozet_dili"]
    if v.get("dil") in ("tr", "en"):                      # arayüz dili (2026-10-25)
        d["dil"] = v["dil"]
    if "ag_paylasimi" in v:
        d["ag_paylasimi"] = bool(v["ag_paylasimi"])
    if "drive" in v:
        d["drive"] = bool(v["drive"])
    if "oto_kayit" in v:
        d["oto_kayit"] = bool(v["oto_kayit"])
    if "claude" in v:
        d["claude"] = bool(v["claude"])
    if "claude_toplanti" in v:
        d["claude_toplanti"] = bool(v["claude_toplanti"])
    if "danisman" in v:
        d["danisman"] = bool(v["danisman"])
    for k in ("canli_asistan", "oto_gorev", "toplanti_kapisi", "ghost_konu_toplantisi"):
        if k in v:
            d[k] = bool(v[k])
    if "gun_ucreti" in v:
        try:
            d["gun_ucreti"] = max(0, float(v["gun_ucreti"] or 0))
        except (TypeError, ValueError):
            pass
    if "para_birimi" in v:
        d["para_birimi"] = str(v["para_birimi"] or "€")[:4]
    if "haftalik_eposta" in v:
        d["haftalik_eposta"] = bool(v["haftalik_eposta"])
    if "atolye_bakim" in v:
        d["atolye_bakim"] = bool(v["atolye_bakim"])
    for k in ("on_brifing", "on_brifing_eposta", "marka_shorts_oto"):
        if k in v:
            d[k] = bool(v[k])
    if v.get("drive_yol") is not None:
        d["drive_yol"] = str(v["drive_yol"]).strip() or VARSAYILAN_AYARLAR["drive_yol"]
    if isinstance(v.get("sozluk"), list):
        d["sozluk"] = [re.sub(r"[^\w '’\-&.]+", "", str(m)).strip()[:40] for m in v["sozluk"] if str(m).strip()][:80]
    if "pexels_anahtar" in v:
        d["pexels_anahtar"] = str(v.get("pexels_anahtar") or "").strip()[:120]
    if "sync_anahtar" in v:
        d["sync_anahtar"] = str(v.get("sync_anahtar") or "").strip()[:200]
    if "erisim_pin" in v:
        pin = re.sub(r"\D", "", str(v.get("erisim_pin") or ""))
        if pin and not 4 <= len(pin) <= 8:
            return jsonify({"hata": "PIN 4-8 rakam olmalı."}), 400
        d["erisim_pin"] = pin
    if "youtube_api_anahtar" in v:
        d["youtube_api_anahtar"] = re.sub(r"[^\w\-]", "", str(v.get("youtube_api_anahtar") or ""))[:80]
    if "takvim_ics" in v:
        d["takvim_ics"] = "\n".join(u.strip() for u in re.split(r"[\s,]+", str(v.get("takvim_ics") or "")) if u.strip().startswith("http"))[:3000]
        try:
            (KAYIT / ".takvim.ics").unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    if isinstance(v.get("benim_epostalar"), list):
        d["benim_epostalar"] = [str(x).strip().lower()[:80] for x in v["benim_epostalar"] if "@" in str(x)][:5]
    if "notlar_gonder" in v:
        d["notlar_gonder"] = bool(v["notlar_gonder"])
    if "benim_adim" in v:
        d["benim_adim"] = re.sub(r"[^\w .'’\-]+", "", str(v.get("benim_adim") or "")).strip()[:40]
    if isinstance(v.get("musteriler"), list):
        # "Ajans: Ayşe, Ali" biçimi → müşteri adı + o müşteriyle görüşülen kişiler
        adlar, kisiler = [], {}
        for m in v["musteriler"]:
            m = str(m).strip()
            if not m:
                continue
            ad, _, kisi = m.partition(":")
            ad = re.sub(r'[\\/:*?"<>|]+', " ", ad).strip()[:40]
            if not ad:
                continue
            adlar.append(ad)
            kisiler[ad] = [k.strip()[:40] for k in re.split(r"[,/]", kisi) if k.strip()][:20]
        d["musteriler"] = adlar[:30]; d["musteri_kisiler"] = kisiler
    if "asana_token" in v:
        tok = str(v.get("asana_token") or "").strip()
        if tok:
            d["asana_token"] = tok; globals().get("asana_onbellek", {}).clear()
            if "_asana_bekleyenleri_gonder" in globals():
                threading.Timer(5, _asana_bekleyenleri_gonder).start()
        else:
            d.pop("asana_token", None); d.pop("asana_ws", None); globals().get("asana_onbellek", {}).clear()
    if v.get("asana_ws"):
        d["asana_ws"] = str(v["asana_ws"])[:40]
    if v.get("drive_klasor") is not None:
        d["drive_klasor"] = re.sub(r"[^\w /\-ıİğüşöçĞÜŞÖÇ.]+", "", str(v["drive_klasor"])).strip(" /") or "Transkript/Toplantılar"
    ayarlar_yaz(d)
    yeniden = d.get("ag_paylasimi", False) != eski_ag
    bekleyen = mesgul_nedenler() if yeniden else []
    if yeniden:
        guvenli_yeniden_baslat()
    d["ip"] = yerel_ip(); d["port"] = PORT; d["yeniden_baslatiliyor"] = yeniden; d["yeniden_bekliyor"] = bekleyen
    return jsonify(d)


@app.delete("/api/sil/<temel>")
def sil(temel):
    t = _temel_dogrula(temel)
    COP.mkdir(exist_ok=True)
    for f in list(KLASOR.glob(f"{temel}.*")):
        if f.is_file():
            shutil.move(str(f), str(COP / f.name))
    kk = KLASOR / "kareler" / temel
    if kk.exists():
        hedef = COP / f"kareler_{temel}"
        shutil.rmtree(hedef, ignore_errors=True); shutil.move(str(kk), str(hedef))
    return jsonify({"tamam": True, "turemis": len(_turemisler(temel))})   # bu kayıttan üretilmiş videolar silinmez, İndirilenler'de "kaynağı silindi" görünür


@app.post("/api/geri/<temel>")
def geri(temel):
    if not re.match(r"^[\w\-]+$", temel):
        abort(404)
    geldi = 0
    for f in list(COP.glob(f"{temel}.*")):
        if f.is_file():
            shutil.move(str(f), str(KLASOR / f.name)); geldi += 1
    kk = COP / f"kareler_{temel}"
    if kk.exists():
        (KLASOR / "kareler").mkdir(exist_ok=True)
        shutil.move(str(kk), str(KLASOR / "kareler" / temel))
    return jsonify({"tamam": geldi > 0})


def _cop_temizle():
    try:
        if COP.exists():
            for f in COP.iterdir():
                if time.time() - f.stat().st_mtime > 86400:
                    shutil.rmtree(f, ignore_errors=True) if f.is_dir() else f.unlink()
    except Exception:  # noqa: BLE001
        pass


@app.post("/api/goster/<temel>")
def goster(temel):
    t = _temel_dogrula(temel)
    subprocess.Popen(["/usr/bin/open", "-R", str(t.with_suffix(".docx"))])
    return jsonify({"tamam": True})


# ----------------------------------------------------------------------------- Claude bağlantısı (2026-10-27: 07_ghost.py'den taşındı; tek başına
# kurulan Studio'da yoktu, Ayarlar'daki "Claude'a bağlan" ve kullanım satırı 404 alıyordu)
@app.get("/api/claude")
def claude_get():
    import claude_yaz
    return jsonify({**claude_yaz.durum(zorla=True), "model": claude_yaz.model()})


@app.get("/api/claude/kullanim")
def claude_kullanim():
    import claude_yaz
    gun = min(31, max(1, int(request.args.get("gun") or 7)))
    return jsonify(claude_yaz.kullanim_ozeti(gun))


@app.post("/api/claude/baglan")
def claude_baglan():
    """Giriş penceresini Terminal'de açar; kullanıcı tarayıcıda onaylar. 2026-10-27: betik kurulum klasörüne göre her seferinde yazılır
    (eski 'Claude'a Giriş.command' ev klasöründeki sabit yolu kullanıyordu; GitHub'dan başka yere kurulan Studio'da yoktu)."""
    import claude_yaz
    prog = claude_yaz.program()
    if not prog:
        return jsonify({"hata": "Claude programı bulunamadı. Claude masaüstü uygulamasını ya da Claude Code'u kurun.",
                        "hata_en": "Claude was not found. Install the Claude desktop app or Claude Code."}), 404
    komut = KAYIT / ".claude_giris.command"
    durum = KAYIT / ".claude_durum.json"
    komut.write_text("#!/bin/zsh\nclear\necho ''\necho '  Claude · giriş / sign in'\necho '  Tarayıcıda açılan sayfada onaylayın, sonra bu pencereyi kapatın.'\n"
                     "echo '  Approve in the browser page that opens, then close this window.'\necho ''\n"
                     f"'{prog}' auth login\nrm -f '{durum}'\n", encoding="utf-8")
    komut.chmod(0o700)
    subprocess.Popen(["/usr/bin/open", str(komut)])
    return jsonify({"tamam": True})

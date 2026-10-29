# sunucu/09_meet.py — Meet: canlı yazıya dökme ucu ve döngüleri, canlı öneriler, toplantı öncesi hazırlık notu, takvimde süren görüşme (2026-10-29:
# 09_atolye.py'den ayrıldı). site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.


@app.get("/api/canli")
def canli_get():
    """En güncel canlı durum: sürüyor ya da son 10 dakikada bitmiş."""
    if not CANLI.exists():
        return jsonify({"aktif": False})
    adaylar = sorted((p for p in CANLI.glob("*.json") if not p.name.endswith((".mik.json", ".asistan.json"))), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in adaylar[:3]:
        try:
            v = json.loads(d.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if v.get("bitti") and time.time() - v.get("guncelleme", 0) > 600:
            continue
        if not v.get("bitti"):
            # Canlı süreç yarıda kesildiyse (ör. site yeniden başladı) durum dosyası "bitmedi" diye kalıyordu ve kart sonsuza dek
            # "Toplantı sürüyor" diyordu (20 Ekim). Kayıt dosyası yoksa ya da 3 dakikadır büyümüyorsa sürmüyor say.
            kaynak = Path(v.get("kaynak") or v.get("dosya", ""))
            try:
                if kaynak.suffix == ".json":                       # 27 Ekim: kayıt sürerken kaydedicinin parçalarından (kayitlar/.kayit_canli.json)
                    kk = meet_kayit_canli() if "meet_kayit_canli" in globals() else None
                    buyuyor = bool(kk) and kk.get("ad") == d.stem
                else:
                    buyuyor = kaynak.exists() and time.time() - kaynak.stat().st_mtime < 180
            except OSError:
                buyuyor = False
            if not buyuyor:
                continue
        v["aktif"] = not v.get("bitti")
        try:
            v["asistan"] = json.loads(d.with_name(d.stem + ".asistan.json").read_text(encoding="utf-8")).get("kartlar", [])[-8:]
        except Exception:  # noqa: BLE001
            v["asistan"] = []
        v["segmentler"] = v.get("segmentler", [])[-40:]
        v["ad"] = Path(v.get("dosya", "")).stem
        return jsonify(v)
    return jsonify({"aktif": False})


threading.Thread(target=_canli_dongu, daemon=True).start()


def _canli_asistan_dongu():
    """Canlı toplantıda ~45 sn'de bir anlık hatırlatma ve mentörlük kartı (canli_asistan.py); yalnızca yeni konuşma birikince."""
    son = {}
    while True:
        time.sleep(45)
        try:
            if ayarlar_oku().get("canli_asistan", True) is False or not CANLI.exists():
                continue
            for d in sorted((p for p in CANLI.glob("*.json") if not p.name.endswith((".mik.json", ".asistan.json"))), key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
                if time.time() - d.stat().st_mtime > 120:
                    continue
                v = json.loads(d.read_text(encoding="utf-8"))
                if v.get("bitti"):
                    continue
                n = len(v.get("segmentler") or [])
                if n - son.get(d.name, 0) < 3:
                    continue
                son[d.name] = n
                af = d.with_name(d.stem + ".asistan.json")
                eski = json.loads(af.read_text(encoding="utf-8")).get("kartlar", []) if af.exists() else []
                import canli_asistan
                yeni = canli_asistan.uret(v, eski, log=lambda m: print(m, flush=True)) or []
                if yeni:
                    af.write_text(json.dumps({"kartlar": (eski + yeni)[-12:]}, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"canlı asistan hatası: {e}", flush=True)


threading.Thread(target=_canli_asistan_dongu, daemon=True).start()


def _on_brifing_dongu():
    """Takvimde 5-15 dk içinde başlayacak toplantı için hazırlık notu + bildirim (haftada değil, her dakika bakar)."""
    while True:
        time.sleep(60)
        try:                                               # söz takibi: her sabah 09.00'dan sonra bir kez hatırlatma
            gun = time.strftime("%Y-%m-%d"); isaret = KAYIT / ".soz_hatirlatma"
            # 22 Ekim: kullanıcı işleri ana sayfada görmek istemiyor ("zaten yapmış oluyorum"); sabah bildirimi de varsayılan kapalı (ayar soz_bildirim)
            if ayarlar_oku().get("soz_bildirim", False) and time.localtime().tm_hour >= 9 and (not isaret.exists() or isaret.read_text(encoding="utf-8") != gun):
                isaret.write_text(gun, encoding="utf-8")
                import sozler
                h = sozler.hatirlatma_metni()
                if h:
                    _bildir(h[0], h[1])
        except Exception as e:  # noqa: BLE001
            print(f"Söz hatırlatma hatası: {e}", flush=True)
        try:
            ay = ayarlar_oku()
            if not ay.get("takvim_ics") or ay.get("on_brifing") is False:
                continue
            import onbrifing
            for e in onbrifing.adaylar(5, 15):
                if onbrifing.hazir_mi(e):
                    continue
                k = onbrifing.hazirla(e, log=lambda m: print(m, flush=True))
                dk = max(1, int((k["bas"] - time.time()) // 60))
                ilk = re.sub(r"\*\*", "", (k.get("metin") or "").split("\n")[0])[:120]
                _bildir(f"{dk} dk sonra: {k['ad']}", ilk or "Hazırlık notu Meet'te")
                if ay.get("on_brifing_eposta"):
                    import notlar as notlar_modulu
                    import marka as marka_modulu
                    adres = (ay.get("benim_epostalar") or [""])[0]
                    if adres:
                        notlar_modulu.gonder(f"Hazırlık · {k['ad']} · {time.strftime('%H:%M', time.localtime(k['bas']))}", marka_modulu._md_duz(k["metin"]), adres, adres)
        except Exception as e:  # noqa: BLE001
            print(f"Ön hazırlık hatası: {e}", flush=True)


threading.Thread(target=_on_brifing_dongu, daemon=True).start()
threading.Thread(target=_yarim_toplantilari_bitir, daemon=True).start()


SUREN_GORUSME = {"e": None}


def _takvim_arama_dongu():
    """Takvimde şu an süren çevrimiçi görüşme varsa kaydediciye işaret (kayitlar/.takvim_arama); Chrome uzantısı susarsa tarayıcı kaydı bununla başlar."""
    while True:
        try:
            if ayarlar_oku().get("takvim_ics"):
                import takvim
                e = takvim.suren()
                SUREN_GORUSME["e"] = e
                if e:
                    (KAYIT / ".takvim_arama").write_text(e["ad"], encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"Takvim kontrolü: {e}", flush=True)
        time.sleep(30)


threading.Thread(target=_takvim_arama_dongu, daemon=True).start()


@app.get("/api/on-brifing")
def on_brifing_get():
    import onbrifing
    sonuc = {"kayitlar": onbrifing.son_kayitlar(1, 24), "siradaki": None, "suren": None,
             "bekleme": bool(uzanti_durum.get("bekleme")) and time.time() - (uzanti_durum.get("zaman") or 0) < 30,   # giriş ekranındasınız
             "hazirlaniyor": bool(CANLI_BRIF.get("calisiyor"))}
    k = CANLI_BRIF.get("kayit")
    if k and time.time() - (uzanti_durum.get("zaman") or 0) < 120 and time.time() - k.get("bas", 0) < 4 * 3600:
        sonuc["suren"] = {"ad": k.get("ad"), "bas": k.get("bas"), "kisiler": k.get("kisiler") or [], "id": k.get("id"), "metin": k.get("metin", ""), "hazir": True}
    try:
        e = onbrifing.siradaki(24)
        if e:
            sonuc["siradaki"] = {"ad": e.get("ad"), "bas": e["bas"], "kisiler": [k["ad"] for k in onbrifing._baskalari(e)], "hazir": onbrifing.hazir_mi(e),
                                 "id": onbrifing._kimlik(e)}
    except Exception:  # noqa: BLE001
        pass
    return jsonify(sonuc)


@app.post("/api/on-brifing/hazirla")
def on_brifing_hazirla():
    import onbrifing
    e = onbrifing.siradaki(24)
    if not e:
        return jsonify({"hata": "Önümüzdeki 24 saatte başkalarının da davetli olduğu bir toplantı yok."}), 404
    return jsonify(onbrifing.hazirla(e))

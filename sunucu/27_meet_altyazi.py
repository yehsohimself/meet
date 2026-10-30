# Meet: toplantı altyazıları (2026-10-25; Google Meet notları / Tactiq gibi). Uzantı 3.11 altyazı satırlarını konuşmacı ve zamanla gönderir;
# toplantı bitince _toplanti_bitir_ic başında meet_altyazi_uygula: konuşmacılar düzelir, Claude ses yazısını altyazı ve bağlamla düzeltir.
# Toplantı sohbetine bildirim YAZILMAZ (kullanıcı kararı, 2026-10-25).


@app.post("/api/uzanti/altyazi")
def uzanti_altyazi():
    import meet_altyazi
    v = request.get_json(silent=True) or {}
    return jsonify({"tamam": True, "n": meet_altyazi.kaydet(v.get("satirlar"), v.get("platform") or "")})


def meet_altyazi_dosyasi(yol, bas, bit):
    """Kayıt aralığının altyazısını kayıt dosyasının yanına yazar (iş kaydı büyümesin). Döner: dosya yolu ya da ''."""
    import meet_altyazi
    satirlar = meet_altyazi.aralik(bas, bit)
    if not satirlar:
        return ""
    hedef = KAYIT / ".altyazi" / (Path(yol).stem + ".json")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps({"bas": bas, "bit": bit, "satirlar": satirlar}, ensure_ascii=False), encoding="utf-8")
    return str(hedef)


def meet_altyazi_uygula(is_):
    """Toplantı sonrası akışın ilk adımı: altyazıyla konuşmacıları düzeltir, Claude ses yazısını altyazıya ve bağlama bakarak düzeltir
    ("muhtemelen şunu demiştir"); segmentler kilit altında yazılır, altyazının konuşanları ad eşleme olaylarına eklenir.
    Altyazı yoksa da bağlam düzeltmesi çalışır (Claude ve toplantı izni varsa). Davetli kayıtlarında çalışmaz (uzantı yok)."""
    if is_.get("altyazi_uygulandi") or is_.get("misafir"):
        return
    import kayit_json
    import meet_altyazi
    satirlar = []
    yol = is_.get("altyazi_dosya")
    kayit = is_.get("kayit_dosya") or is_.get("link") or ""
    if (not yol or not Path(yol).exists()) and kayit:           # 26 Ekim: yeniden kurulan iş kaydında yol yoktu, 595 satır kullanılmadı
        aday = KAYIT / ".altyazi" / (Path(kayit).stem + ".json")
        if aday.exists():
            yol = str(aday)
        elif is_.get("kayit_baslangic"):
            try:
                yol = meet_altyazi_dosyasi(Path(kayit), float(is_["kayit_baslangic"]), float(is_["kayit_baslangic"]) + _kayit_suresi(kayit))
            except Exception:  # noqa: BLE001
                yol = ""
    if yol and Path(yol).exists():
        try:
            satirlar = json.loads(Path(yol).read_text(encoding="utf-8")).get("satirlar") or []
        except ValueError:
            satirlar = []
    import meet_gelisim
    ben = meet_gelisim.ben_tam_ad()
    meet_altyazi.kendini_adlandir(satirlar, ben)
    if ben and is_.get("konusmaci_olaylari"):                   # uzantının konuşan olaylarında da kullanıcı "You"
        is_["konusmaci_olaylari"] = [dict(o, ad=ben) if str(o.get("ad") or "").strip().casefold() in meet_altyazi.KENDI else o
                                     for o in is_["konusmaci_olaylari"]]
    js = KLASOR / f"{is_['temel']}.json"
    log = is_.setdefault("log", []).append
    d0 = json.loads(js.read_text(encoding="utf-8"))
    segler = d0["segmentler"]
    ozet = meet_altyazi.uygula(segler, satirlar, dil=d0["veri"].get("dil") or "tr", log=log, adlar=is_.get("katilimcilar") or [],
                               etiket=d0["veri"].get("etiket") or {})
    yeni_ad = ozet.pop("etiket", None) or {}
    if yeni_ad:
        log("      Altyazıdan konuşanlar: " + ", ".join(sorted(set(yeni_ad.values()))))

    def yaz(d):
        d["segmentler"] = segler                                       # bu adım akışın en başında: arada kullanıcı düzeltmesi beklenmez
        d["veri"]["altyazi"] = ozet
        if yeni_ad:
            d["veri"].setdefault("etiket", {}).update(yeni_ad)
        if is_.get("birlesik") and is_.get("kayit_baslangic"):          # bağlantı kopup gelmiş toplantı (28): kayıtta olmayan aralıklar sayfada görünsün
            b0 = float(is_["kayit_baslangic"]); P = sorted(is_["birlesik"], key=lambda x: x["bas"])
            d["veri"]["kayit_bosluklari"] = [{"bas": round(P[i]["bit"] - b0, 1), "bit": round(P[i + 1]["bas"] - b0, 1)}
                                             for i in range(len(P) - 1) if P[i + 1]["bas"] - P[i]["bit"] > 20]
    with kilit:
        kayit_json.guncelle(js, yaz)
    if satirlar:
        try:
            (KLASOR / f"{is_['temel']}.altyazi.json").write_text(json.dumps(satirlar, ensure_ascii=False), encoding="utf-8")   # sil/yedek <temel>.* ile
        except OSError:
            pass
        is_["konusmaci_olaylari"] = list(is_.get("konusmaci_olaylari") or []) + meet_altyazi.olaylar(satirlar)
    is_["altyazi_uygulandi"] = True


# ----------------------------------------------------------------------------- kayıt sürerken (2026-10-27)
# Kullanıcı: "toplantının kayda alındığını göremiyorum, strese giriyorum" ve "toplantı sırasında öneriler gelecekti, göremiyorum".
# Kaydedici kayıt sürerken kayitlar/.kayit_canli.json yazar (parçalar, son ses anı, sorun). Bu döngü canlı yazıya dökmeyi o parçalardan başlatır
# (eskiden asıl m4a ancak toplantı bitince oluştuğu için canlı yazı ve fısıltı kartları gerçek toplantılarda hiç çalışmıyordu) ve kayıt başlayınca
# bildirim verir. Uzantı ve sayfalar durumu /api/kayit/canli-durum'dan okur.
MEET_KAYIT_CANLI = KAYIT / ".kayit_canli.json"
MEET_KAYIT_SON = {"ad": "", "bildirildi": ""}
MEET_CANLI_DENEME = {}


def meet_kayit_canli():
    """Kaydedicinin canlı durumu; kayıt yoksa ya da 30 sn'dir tazelenmediyse None."""
    try:
        k = json.loads(MEET_KAYIT_CANLI.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not k.get("kayit") or time.time() - float(k.get("guncelleme", 0)) > 30 or not k.get("ad"):
        return None
    return k


def _meet_disk_gb():
    try:
        return shutil.disk_usage(str(KLASOR)).free / 1e9
    except Exception:  # noqa: BLE001
        return 99.0


def _meet_disk_gunluk():
    """10 GB altında 12 saatte bir bildirim (toplantı kaydı için yer kalmasın diye; 26-27 Ekim'de disk iki kez doldu)."""
    if time.time() - MEET_KAYIT_SON.get("disk_gunluk", 0) < 600:
        return
    MEET_KAYIT_SON["disk_gunluk"] = time.time()
    bos = _meet_disk_gb()
    isaret = KAYIT / ".disk_uyari"
    try:
        son = float(isaret.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        son = 0
    if bos < 10 and time.time() - son > 12 * 3600:
        isaret.write_text(str(time.time()), encoding="utf-8")
        _bildir("Diskte yer azaldı", f"{bos:.1f} GB boş. Toplantı kayıtları için en az 10 GB önerilir; Çöp'ü boşaltın.", url="http://127.0.0.1:8766/")


def _meet_kayit_dongu():
    while True:
        time.sleep(5)
        try:
            _meet_disk_gunluk()
        except Exception as e:  # noqa: BLE001
            print(f"Disk denetimi: {e}", flush=True)
        try:
            k = meet_kayit_canli()
            if not k:
                continue
            ad = k["ad"]
            if _kayit_disi_eslesen(k.get("pencere")):         # kaydedilmeyen toplantı (30): bildirim ve canlı yazıya dökme yok
                p = canli_surecler.get(ad)
                if p is not None and p.poll() is None:
                    p.terminate()
                continue
            if MEET_KAYIT_SON["bildirildi"] != ad:
                MEET_KAYIT_SON["bildirildi"] = ad
                bos = _meet_disk_gb()
                if bos < 3:                                    # 2026-10-28: disk %98 doluydu; kayıt yarıda kalmasın diye hemen söylenir
                    _bildir("Toplantı kaydediliyor · disk dolmak üzere", f"Diskte {bos:.1f} GB kaldı; kayıt yarıda kalabilir. Çöp'ü boşaltın.", url="http://127.0.0.1:8766/")
                    MEET_KAYIT_SON["disk_uyari"] = time.time()
                else:
                    _bildir("Toplantı kaydediliyor", "Menü çubuğundaki kırmızı nokta kaydın sürdüğünü gösterir", url="http://127.0.0.1:8766/")
            if time.time() - MEET_KAYIT_SON.get("disk_bak", 0) > 60:   # kayıt sürerken dakikada bir: 1,5 GB altı
                MEET_KAYIT_SON["disk_bak"] = time.time()
                bos = _meet_disk_gb()
                if bos < 1.5 and time.time() - MEET_KAYIT_SON.get("disk_uyari", 0) > 900:
                    MEET_KAYIT_SON["disk_uyari"] = time.time()
                    _bildir("Disk doldu, kayıt durabilir", f"Diskte {bos:.1f} GB kaldı. Hemen Çöp'ü boşaltın ya da büyük bir dosyayı silin.", url="http://127.0.0.1:8766/")
            if not ayarlar_oku().get("oto_kayit", True) or not (k.get("parcalar") or []):
                continue
            p = canli_surecler.get(ad)
            if p is not None and p.poll() is None:
                continue
            dn = MEET_CANLI_DENEME.setdefault(ad, {"n": 0, "son": 0.0})                 # hemen çöken süreç her 5 sn'de yeniden açılmasın (2026-10-27 incelemesi)
            if p is not None and time.time() - dn["son"] < 90:
                dn["n"] += 1
            if dn["n"] and time.time() - dn["son"] < min(600, 30 * 2 ** dn["n"]):
                continue
            durum = CANLI / f"{ad}.json"
            if durum.exists():
                try:
                    dv = json.loads(durum.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    dv = {}
                if dv.get("bitti") or time.time() - dv.get("guncelleme", 0) < 45:
                    continue
            CANLI.mkdir(parents=True, exist_ok=True)
            with open(CANLI / f"{ad}.log", "a", encoding="utf-8") as log_dosya:                # alt süreç kendi kopyasını tutar; burada kapanır
                canli_surecler[ad] = subprocess.Popen([PYTHON, "-u", str(CANLI_SCRIPT), str(MEET_KAYIT_CANLI), str(durum)],
                                                      stdout=log_dosya, stderr=subprocess.STDOUT, cwd=str(KLASOR), env=_env())
            dn["son"] = time.time()
            print(f"Canlı yazıya dökme (kayıt sürerken) başladı: {ad}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"kayıt izleme hatası: {e}", flush=True)


threading.Thread(target=_meet_kayit_dongu, daemon=True).start()


@app.get("/api/kayit/canli-durum")
def meet_kayit_canli_durum():
    """Kayıt sürüyor mu, ses geliyor mu, canlı yazı nerede, son öneriler (Chrome uzantısının toplantı sekmesindeki göstergesi ve Meet sayfası)."""
    k = meet_kayit_canli()
    if not k:
        return jsonify({"kayit": False})
    simdi = time.time()
    v = {"kayit": True, "ad": k["ad"], "sure": int(simdi - float(k.get("baslangic", simdi))), "sorun": k.get("sorun") or "", "kapaniyor": k.get("kapaniyor"),
         "ses_yas": int(simdi - float(k.get("son_ses", simdi))), "uygulama": k.get("uygulama", ""), "parca": len(k.get("parcalar") or [])}
    if v["ses_yas"] > 20 and not v["sorun"]:
        v["sorun"] = "Ses gelmiyor"
    try:
        c = json.loads((CANLI / f"{k['ad']}.json").read_text(encoding="utf-8"))
        v["canli"] = {"islenen": int(c.get("islenen_sn") or 0), "gecikme": c.get("gecikme"), "segment": len(c.get("segmentler") or []),
                      "son": [s.get("metin", "") for s in (c.get("segmentler") or [])[-2:]]}
    except Exception:  # noqa: BLE001
        v["canli"] = None
    try:
        v["kartlar"] = json.loads((CANLI / f"{k['ad']}.asistan.json").read_text(encoding="utf-8")).get("kartlar", [])[-6:]
    except Exception:  # noqa: BLE001
        v["kartlar"] = []
    v["pay"] = _meet_canli_pay(k["ad"])
    try:                                                                   # uzantı toplantıda ama Meet/Teams altyazısı kapalı: adlar ve keskin metin gelmez
        t = json.loads((KAYIT / ".uzanti_tani.json").read_text(encoding="utf-8"))
        v["altyazi_kapali"] = bool(t.get("aramada") and t.get("altyazi") is False and t.get("sure", 0) > 90 and time.time() - t.get("zaman", 0) < 60)
    except Exception:  # noqa: BLE001
        v["altyazi_kapali"] = False
    taze = time.time() - uzanti_durum.get("zaman", 0) < 120               # uzantının okuduğu sekme başlığı ve katılımcılar (yan panel başlığı)
    v["baslik"] = (_toplanti_adi_temizle(uzanti_durum.get("baslik", "")) if taze else "") or _pencere_toplanti_adi(k.get("pencere"), k.get("uygulama")) or ""
    import kisiler as kisiler_modulu
    v["katilimcilar"] = [x for x in (uzanti_durum.get("katilimcilar") or []) if kisiler_modulu.ad_mi(x)][:12] if taze else []
    return jsonify(v)


MEET_PAY = {}


def _meet_canli_pay(ad):
    """Canlı konuşma payları {ad: yüzde} ve kullanıcının adı; hesap (mikrofon parçalarında sessizlik ölçümü) arka planda, 45 sn önbellek."""
    o = MEET_PAY.get(ad)
    if (not o or time.time() - o[0] > 45) and not (o and o[2]):
        MEET_PAY[ad] = (o[0] if o else 0, o[1] if o else None, True)

        def _hesap():
            sonuc = None
            try:
                import canli_asistan
                c = json.loads((CANLI / f"{ad}.json").read_text(encoding="utf-8"))
                _, pay, toplam = canli_asistan.konusmacilar(c)
                if toplam >= 60:
                    ben = (ayarlar_oku().get("benim_adim") or "").strip().split(" ")[0]
                    sonuc = {"paylar": {a: round(100 * sn / toplam) for a, sn in sorted(pay.items(), key=lambda x: -x[1])[:6]}, "ben": ben,
                             "yaklasik": "Diğerleri" in pay}
            except FileNotFoundError:                         # canlı yazı henüz başlamadı (kaydın ilk dakikası)
                pass
            except Exception as e:  # noqa: BLE001
                print(f"canlı konuşma payı: {e}", flush=True)
            MEET_PAY[ad] = (time.time(), sonuc, False)
        threading.Thread(target=_hesap, daemon=True).start()
    return (MEET_PAY.get(ad) or (0, None, False))[1]


@app.post("/api/kayit/kart")
def meet_kayit_kart():
    """Yan paneldeki canlı öneriye geri bildirim {ad, zaman, geri: iyi|kotu}; kartta saklanır, toplantı bitince danışman notuna gider."""
    v = request.get_json(silent=True) or {}
    ad = str(v.get("ad") or ""); geri = v.get("geri")
    if not ad or "/" in ad or geri not in ("iyi", "kotu", None):
        return jsonify({"hata": "Geçersiz."}), 400
    yol = CANLI / f"{ad}.asistan.json"
    if not yol.exists():
        return jsonify({"hata": "Öneri bulunamadı."}), 404
    with kilit:
        d = json.loads(yol.read_text(encoding="utf-8"))
        for kt in d.get("kartlar", []):
            if abs(float(kt.get("zaman", 0)) - float(v.get("zaman") or 0)) < 0.01:
                if geri:
                    kt["geri"] = geri
                else:
                    kt.pop("geri", None)
        yol.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return jsonify({"tamam": True})

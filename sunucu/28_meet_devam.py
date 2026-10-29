# Meet: aynı toplantının bölünmüş kayıtları (2026-10-27). Kullanıcı: "İnternetim kopup geldi ama aynı toplantı devam ediyordu; sistem bunu
# anlamalı, raporu, transkripti birleştirmeli." Bağlantı kopunca Google Meet mikrofonu bırakır, kaydedici kaydı kapatır; yeniden bağlanınca ikinci bir
# kayıt başlar. Kaydedicinin bildirdiği yeni kayıt, aynı uygulamanın önceki kaydının bitişinden en çok MEET_DEVAM_ARA sn sonra başlıyorsa ve toplantı
# adı tutuyorsa (ad yoksa çok kısa arayla) devam sayılır: sesler gerçek zaman çizgisinde (arada sessizlik) tek dosyada birleşir, önceki parçanın işi
# durdurulur ya da çıktıları (transkript, Drive klasörü) kaldırılır ve birleşik kayıt baştan işlenir. Özgün parçalar kayitlar/.parcalar/<ad>/ altında.
# Aynı gün güvenlik/dayanıklılık incelemesinden sonra: önce ses birleştirilir (olmazsa öncekine dokunulmaz), bekleyen birleştirme diske yazılır ve
# açılışta sürer, yeniden başlatma onu bekler, silinmiş/"toplantı değil" kayıtlar aday olmaz, adsız kayıtlarda ara 90 sn.
MEET_DEVAM_ARA = 20 * 60          # sn; bundan uzun ara yeni toplantıdır
MEET_DEVAM_ADSIZ = 90             # sn; iki taraftan birinin adı yoksa (Meet kodu boş sayılır) yalnız bu kadar kısa arada devam sayılır
MEET_DEVAM = {}                   # önceki iş kimliği -> {"parcalar": [...], "bitis", "baslik", "durum": bekliyor|birlestiriliyor, "gec": [...]}
MEET_DEVAM_DOSYA = KAYIT / ".devam_bekleyen.json"


def _kayit_suresi(yol):
    try:
        return float(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(yol)],
                                    capture_output=True, text=True, timeout=60).stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _ad_anahtari(s):
    return re.sub(r"\W+", " ", str(s or "").casefold()).strip()


def _meet_devam_yaz():
    try:
        MEET_DEVAM_DOSYA.write_text(json.dumps(MEET_DEVAM, ensure_ascii=False), encoding="utf-8") if MEET_DEVAM else MEET_DEVAM_DOSYA.unlink(missing_ok=True)
    except OSError as e:
        print(f"Bekleyen birleştirme yazılamadı: {e}", flush=True)


def _is_gecerli_toplanti(is_):
    """Aday iş hâlâ geçerli bir toplantı mı: kaldırılmış ("Listeden kaldır") ya da "toplantı değil" denmiş kayıt birleştirmeye girmez."""
    if is_.get("silindi") or is_.get("birlestirildi"):
        return False
    t = is_.get("temel")
    if not t:
        return is_.get("durum") in ("sirada", "calisiyor")           # henüz yazıya dökülüyor
    if (COP / f"{t}.json").exists() or not (KLASOR / f"{t}.json").exists():
        return False
    try:
        return not (kitaplik_onbellek_veri(t) or {}).get("onay_bekliyor")
    except Exception:  # noqa: BLE001
        return True


def kitaplik_onbellek_veri(t):
    import kitaplik_onbellek
    return kitaplik_onbellek.veri(t)


def _onceki_parca(bas, baslik, uygulama):
    """Bu kaydın devamı olduğu önceki toplantı işi (yoksa None). Arada bekleyen bir birleştirme varsa onun işi döner."""
    for pid, d in list(MEET_DEVAM.items()):
        if 0 <= bas - d["bitis"] <= MEET_DEVAM_ARA and (not baslik or not d.get("baslik") or _ad_anahtari(baslik) == _ad_anahtari(d["baslik"])):
            return isler.get(pid) or {"id": pid}
    aday = None
    for is_ in list(isler.values()):
        if not is_.get("toplanti") or is_.get("misafir") or not is_.get("kayit_baslangic") or is_.get("durum") in ("iptal",) or not _is_gecerli_toplanti(is_):
            continue
        if uygulama and is_.get("uygulama") and is_.get("uygulama") != uygulama:
            continue
        ib = float(is_["kayit_baslangic"])
        bit = float(is_.get("kayit_bitis") or 0) or ib + _kayit_suresi(is_.get("kayit_dosya") or "")
        ara = bas - bit
        if ara < -60 or ara > MEET_DEVAM_ARA or bas <= ib:
            continue
        b1, b2 = _ad_anahtari(is_.get("toplanti_baslik")), _ad_anahtari(baslik)
        if (b1 and b2 and b1 != b2) or ((not b1 or not b2) and ara > MEET_DEVAM_ADSIZ):
            continue
        if not aday or ib > float(aday["kayit_baslangic"]):
            aday = is_
    return aday


def _ses_birlestir(parcalar, hedef):
    """[(dosya, baslangic)] -> geçici dosya; her parça ilk parçanın başlangıcına göre gerçek yerine konur (aradaki kopukluk sessizlik)."""
    bas0 = parcalar[0][1]
    komut = ["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error"]
    for f, _ in parcalar:
        komut += ["-i", str(f)]
    filtre = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(max(0.0, b - bas0) * 1000)}:all=1[a{i}];"
                     for i, (_, b) in enumerate(parcalar))
    filtre += "".join(f"[a{i}]" for i in range(len(parcalar))) + f"amix=inputs={len(parcalar)}:duration=longest:normalize=0[o]"
    gecici = hedef.with_name("." + hedef.stem + ".birlesik.m4a")    # nokta: canlı yazıya dökme büyüyen "Toplantı *.m4a" sanmasın
    p = subprocess.run(komut + ["-filter_complex", filtre, "-map", "[o]", "-c:a", "aac", "-b:a", "128k", str(gecici)], capture_output=True, text=True, timeout=3600)
    if p.returncode != 0 or not gecici.exists() or _kayit_suresi(gecici) <= 0:
        gecici.unlink(missing_ok=True)
        raise RuntimeError((p.stderr or "ses birleştirilemedi").strip().splitlines()[-1][:200] if (p.stderr or "").strip() else "ses birleştirilemedi")
    return gecici


def _onceki_ciktilari_kaldir(is_, kayit_yolu):
    """Önceki parçanın işi: sürüyorsa durdurulur ve süreci bitene dek beklenir; bitmişse toplantı sonrası adımlar bitene dek beklenir. Sonra onun
    transkript çıktıları (adıyla ya da yarıda kalmış çıktıysa kayıt yoluyla bulunur) .cop'a, Drive klasörü Çöp'e."""
    bas_zaman = float(is_.get("olusturma") or 0) - 60
    if is_.get("durum") in ("sirada", "calisiyor"):
        is_["birlestirildi"] = True
        with app.test_request_context():
            is_iptal(is_["id"])
        is_["hata"] = "Toplantı devam etti; sonraki kayıtla birleştirildi."
        p = is_.get("p")
        for _ in range(60):
            if not p or p.poll() is not None:
                break
            time.sleep(1)
    son = time.time() + 2 * 3600
    time.sleep(5)
    while is_.get("temel") in toplanti_bitiren and time.time() < son:
        time.sleep(5)
    adaylar = {is_.get("temel")} if is_.get("temel") else set()
    for js in KLASOR.glob("transkript_*.json"):                  # yarıda kesilen iş çıktıyı yazmış olabilir (adı işe hiç geçmedi)
        try:
            if js.stat().st_mtime < bas_zaman:
                continue
            v = (kitaplik_onbellek_veri(js.stem) or {})
            if str(v.get("link") or v.get("kayit") or "") == str(kayit_yolu):
                adaylar.add(js.stem)
        except Exception:  # noqa: BLE001
            continue
    COP.mkdir(exist_ok=True)
    for temel in [t for t in adaylar if t and (KLASOR / f"{t}.json").exists()]:
        try:
            veri = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8")).get("veri") or {}
        except Exception:  # noqa: BLE001
            veri = {}
        for f in list(KLASOR.glob(f"{temel}.*")):
            if f.is_file():
                shutil.move(str(f), str(COP / f.name))
        kk = KLASOR / "kareler" / temel
        if kk.exists():
            shutil.rmtree(COP / f"kareler_{temel}", ignore_errors=True); shutil.move(str(kk), str(COP / f"kareler_{temel}"))
        d = Path(veri.get("drive") or "")
        if veri.get("drive") and d.is_dir():
            try:
                _drive_cope(d)
            except Exception as e:  # noqa: BLE001
                print(f"Önceki parçanın Drive klasörü kaldırılamadı: {e}", flush=True)
        is_["onceki_notlar_gonderildi"] = bool(veri.get("notlar_gonderim") and not (veri.get("notlar_gonderim") or {}).get("hata"))
    is_["birlestirildi"] = True


def _parcayi_tek_isle(x):
    _baslat({"link": x["dosya"], "ozet": True, "konusmaci": True, "altyazi": False, "toplanti": True, "toplanti_baslik": x.get("baslik") or "",
             "kayit_dosya": x["dosya"], "mik_dosya": x.get("mik") or "", "uygulama": x.get("uygulama") or "", "kayit_baslangic": x["bas"],
             "katilimcilar": x.get("katilimcilar") or [], "takvim": x.get("takvim"),
             "konusmaci_olaylari": _uzanti_olaylari(x["bas"], x["bit"]), "altyazi_dosya": meet_altyazi_dosyasi(Path(x["dosya"]), x["bas"], x["bit"])})


def _meet_devam_birlestir(pid, bekle=20):
    """Bekleyen birleştirme: 1) sesler geçici dosyada birleşir (olmazsa önceki toplantıya dokunulmaz, yeni parça kendi başına işlenir);
    2) önceki iş durdurulur/beklenir, çıktıları kaldırılır; 3) özgünler arşive, birleşik ses ilk parçanın adına; 4) tek iş."""
    time.sleep(bekle)                                             # hemen ardından üçüncü bir parça gelirse aynı birleştirmeye girsin
    with kilit:
        d = MEET_DEVAM.get(pid)
        if not d:
            return
        d["durum"] = "birlestiriliyor"; _meet_devam_yaz()
    onceki = isler.get(pid) or {}
    P = sorted(d["parcalar"], key=lambda x: x["bas"])
    hedef = KAYIT / Path(P[0]["dosya"]).name
    try:
        birlesik = _ses_birlestir([(x["dosya"], x["bas"]) for x in P], hedef)
        mikler = [(x["mik"], x["bas"]) for x in P if x.get("mik") and Path(x["mik"]).is_file()]
        mik_birlesik = _ses_birlestir(mikler, hedef.with_name(hedef.stem + ".mik.m4a")) if len(mikler) == len(P) else None
    except Exception as e:  # noqa: BLE001
        print(f"Toplantı kayıtları birleştirilemedi ({e}); yeni parçalar ayrı işleniyor", flush=True)
        with kilit:
            MEET_DEVAM.pop(pid, None); _meet_devam_yaz()
        for x in P[1:] + d.get("gec", []):
            if Path(x["dosya"]).is_file():
                _parcayi_tek_isle(x)
        return
    try:
        _onceki_ciktilari_kaldir(onceki, P[0]["dosya"])
        arsiv = KAYIT / ".parcalar" / hedef.stem
        arsiv.mkdir(parents=True, exist_ok=True)
        for x in P:
            for f in (x["dosya"], x.get("mik")):
                if f and Path(f).is_file() and Path(f).parent == KAYIT:
                    shutil.move(str(f), str(arsiv / Path(f).name))
        shutil.move(str(birlesik), str(hedef))
        mik = ""
        if mik_birlesik:
            mik = str(hedef.with_name(hedef.stem + ".mik.m4a")); shutil.move(str(mik_birlesik), mik)
        bas, bit = P[0]["bas"], max(x["bit"] for x in P)
        katilimcilar = []
        for kl in [onceki.get("katilimcilar") or []] + [x.get("katilimcilar") or [] for x in P]:
            katilimcilar += [k for k in kl if k not in katilimcilar]
        takvim_e = onceki.get("takvim") or next((x.get("takvim") for x in P if x.get("takvim")), None)
        r = _baslat({"link": str(hedef), "ozet": True, "konusmaci": True, "altyazi": False, "toplanti": True,
                     "toplanti_baslik": onceki.get("toplanti_baslik") or d.get("baslik") or "",
                     "kayit_dosya": str(hedef), "mik_dosya": mik, "uygulama": onceki.get("uygulama") or P[-1].get("uygulama") or "",
                     "kayit_baslangic": bas, "katilimcilar": katilimcilar, "takvim": takvim_e,
                     "konusmaci_olaylari": _uzanti_olaylari(bas, bit), "altyazi_dosya": meet_altyazi_dosyasi(hedef, bas, bit)})
        j = r.get_json() if hasattr(r, "get_json") else {}
        yeni = isler.get((j or {}).get("id") or "")
        if yeni is not None:
            yeni["kayit_bitis"] = bit; yeni["birlesik"] = [{"bas": x["bas"], "bit": x["bit"]} for x in P]
            if onceki.get("onceki_notlar_gonderildi"):
                yeni["notlar_gonderildi"] = True                   # notlar e-postası ilk parçadan gitti; birleşik toplantı ikinci kez göndermez
        with kilit:
            isler.pop(pid, None)                                  # önceki parçanın kartı listede "durduruldu" diye kalmasın
            MEET_DEVAM.pop(pid, None); _meet_devam_yaz()
        _kaydet()
        kop = sum(max(0, P[i + 1]["bas"] - P[i]["bit"]) for i in range(len(P) - 1))
        print(f"Toplantı devam etti: {len(P)} kayıt birleştirildi ({hedef.name}, kopukluk {int(kop)} sn)", flush=True)
        _bildir("Toplantının kayıtları birleştirildi", f"Bağlantı kopukluğundan sonraki kayıt aynı toplantıya eklendi ({max(1, int(kop // 60))} dk ara); notlar tek parça hazırlanıyor",
                url="http://127.0.0.1:8766/")
        for x in d.get("gec", []):                                # birleştirme sürerken gelenler: şimdi birleşik işin devamı olarak
            if Path(x["dosya"]).is_file() and not meet_devam_mi(Path(x["dosya"]), x["bas"], x["bit"], x.get("mik"), x.get("baslik"), x.get("uygulama"),
                                                                x.get("katilimcilar"), x.get("takvim")):
                _parcayi_tek_isle(x)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"Toplantı kayıtları birleştirilirken hata: {e}", flush=True)
        with kilit:
            MEET_DEVAM.pop(pid, None); _meet_devam_yaz()
        if Path(hedef).is_file():                                 # birleşik ya da ilk parça yerinde: kayıt kaybolmasın
            _parcayi_tek_isle({**P[0], "bit": max(x["bit"] for x in P)})


def meet_devam_mi(yol, bas, bit, mik, baslik, uygulama, katilimcilar, takvim_e):
    """Kaydedicinin bildirdiği kayıt önceki toplantının devamıysa birleştirmeyi kurar ve True döner (iş ayrıca başlatılmaz)."""
    onceki = _onceki_parca(bas, baslik, uygulama)
    if not onceki:
        return False
    pid = onceki["id"]
    yeni = {"dosya": str(yol), "mik": mik or "", "bas": bas, "bit": bit, "baslik": baslik, "uygulama": uygulama, "katilimcilar": katilimcilar, "takvim": takvim_e}
    with kilit:
        d = MEET_DEVAM.get(pid)
        if d:
            (d["parcalar"] if d.get("durum") != "birlestiriliyor" else d.setdefault("gec", [])).append(yeni)
            d["bitis"] = max(d["bitis"], bit); _meet_devam_yaz()
            return True
        ilk = {"dosya": onceki.get("kayit_dosya"), "mik": onceki.get("mik_dosya") or "", "bas": float(onceki["kayit_baslangic"]),
               "bit": float(onceki.get("kayit_bitis") or 0) or float(onceki["kayit_baslangic"]) + _kayit_suresi(onceki.get("kayit_dosya") or ""),
               "baslik": onceki.get("toplanti_baslik") or "", "uygulama": onceki.get("uygulama") or "", "katilimcilar": onceki.get("katilimcilar") or [],
               "takvim": onceki.get("takvim")}
        if not ilk["dosya"] or not Path(ilk["dosya"]).is_file():
            return False
        MEET_DEVAM[pid] = {"parcalar": [ilk, yeni], "bitis": bit, "baslik": ilk["baslik"] or baslik, "durum": "bekliyor"}
        _meet_devam_yaz()
    print(f"Yeni kayıt önceki toplantının devamı: {Path(ilk['dosya']).name} + {Path(yol).name} (ara {int(bas - ilk['bit'])} sn)", flush=True)
    threading.Thread(target=_meet_devam_birlestir, args=(pid,), daemon=True).start()
    return True


def _meet_devam_acilis():
    """Yeniden başlatmadan önce bekleyen birleştirme kaldıysa sürdürülür."""
    try:
        D = json.loads(MEET_DEVAM_DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    for pid, d in D.items():
        d["durum"] = "bekliyor"; MEET_DEVAM[pid] = d
        print(f"Yarım kalan toplantı birleştirmesi sürüyor: {len(d.get('parcalar', []))} parça", flush=True)
        threading.Thread(target=_meet_devam_birlestir, args=(pid, 5), daemon=True).start()


threading.Thread(target=lambda: (time.sleep(10), _meet_devam_acilis()), daemon=True).start()

_mesgul_onceki_devam = mesgul_nedenler


def mesgul_nedenler():   # noqa: F811 — bekleyen birleştirme ve süren masaüstü kaydı da yeniden başlatmayı bekletir
    n = _mesgul_onceki_devam()
    if MEET_DEVAM:
        n.append("Toplantı kayıtları birleştiriliyor")
    try:
        k = json.loads((KAYIT / ".kayit_canli.json").read_text(encoding="utf-8"))
        if k.get("kayit") and time.time() - float(k.get("guncelleme", 0)) < 60:
            n.append("Toplantı kaydediliyor")
    except Exception:  # noqa: BLE001
        pass
    return n


# İş kartlarındaki toplantı adı (2026-10-27): toplantı sonradan yeniden adlandırılınca iş kaydı eski adla ("underbelly", "StatusIndicator") kalıyordu.
def _meet_is_basliklari_esitle():
    import kitaplik_onbellek
    degisti = False
    for is_ in list(isler.values()):
        if not is_.get("toplanti") or is_.get("durum") != "bitti" or not is_.get("temel"):
            continue
        try:
            b = (kitaplik_onbellek.veri(is_["temel"]) or {}).get("baslik")
        except Exception:  # noqa: BLE001
            b = None
        if b and is_.get("baslik") != b:
            is_["baslik"] = b; degisti = True
    if degisti:
        _kaydet()


@app.after_request
def _meet_is_basligi_sonra(yanit):
    if request.method == "POST" and yanit.status_code < 400 and re.match(r"^/api/(toplanti/[^/]+/duzelt|isimlendir/)", request.path):
        threading.Thread(target=lambda: (time.sleep(3), _meet_is_basliklari_esitle()), daemon=True).start()
    return yanit


threading.Thread(target=lambda: (time.sleep(15), _meet_is_basliklari_esitle()), daemon=True).start()


# Listeden kaldırılan toplantının Drive klasörü (2026-10-27): "Listeden kaldır" yalnız Mac'teki dosyaları .cop'a taşıyordu; Drive'da sahipsiz
# klasörler kalıyordu (22 Ekim "OOO", 15 Ekim "Raum 7"). Şimdi Drive klasörü de Çöp'e gider; bir kopyası .cop/drive__<temel>'de bir gün durur,
# "Geri al" onu yerine koyar.
def _meet_sil_drive(temel):
    try:
        veri = json.loads((COP / f"{temel}.json").read_text(encoding="utf-8")).get("veri") or {}
    except Exception:  # noqa: BLE001
        return
    d = Path(veri.get("drive") or "")
    if not veri.get("toplanti") or not veri.get("drive") or not d.is_dir():
        return
    yedek = COP / f"drive__{temel}"
    try:
        shutil.rmtree(yedek, ignore_errors=True); shutil.copytree(str(d), str(yedek))
        (yedek / ".yer").write_text(str(d), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"Drive klasörünün yedeği alınamadı: {e}", flush=True)
    if not _drive_cope(d):
        print(f"Drive klasörü kaldırılamadı: {d}", flush=True)


def _meet_geri_drive(temel):
    yedek = COP / f"drive__{temel}"
    try:
        yer = Path((yedek / ".yer").read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return
    if not yer.exists():
        (yedek / ".yer").unlink(missing_ok=True)
        yer.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(yedek), str(yer))


@app.after_request
def _meet_sil_geri_sonra(yanit):
    m = re.match(r"^/api/(sil|geri)/([\w\-]+)$", request.path)
    if m and yanit.status_code < 400 and request.method in ("DELETE", "POST"):
        hedef = _meet_sil_drive if m.group(1) == "sil" else _meet_geri_drive
        threading.Thread(target=hedef, args=(m.group(2),), daemon=True).start()
    return yanit


# Sahipsiz toplantı kaydı (2026-10-27 incelemesi): kaydedici kaydı bitirdiğinde site kapalıysa (yeniden başlıyorsa) bildirim kayboluyor, kayıt
# hiç işlenmiyordu. Açılışta ve 20 dk'da bir: son 20 saatte yazılmış, hiçbir işe, transkripte (çöpteki dahil) ya da bekleyen birleştirmeye ait olmayan
# "Toplantı *.m4a" kaydedicinin bildirimiyle aynı yoldan işe verilir.
def _sahipsiz_kayitlar():
    import kitaplik_onbellek
    simdi = time.time()
    adaylar = [f for f in KAYIT.glob("Toplantı *.m4a") if not f.name.endswith(".mik.m4a") and 180 < simdi - f.stat().st_mtime < 20 * 3600]
    if not adaylar:
        return []
    bilinen = {str(is_.get("kayit_dosya") or is_.get("link") or "") for is_ in list(isler.values())}
    for d in list(MEET_DEVAM.values()):
        bilinen |= {x["dosya"] for x in d.get("parcalar", []) + d.get("gec", [])}
    for x in kitaplik_onbellek.hepsi():
        v = x.get("veri") or {}
        bilinen |= {str(v.get("kayit") or ""), str(v.get("link") or "")}
    for js in COP.glob("transkript_*.json") if COP.exists() else []:
        v = kitaplik_onbellek.veri(js.stem, klasor=COP) or {}
        bilinen |= {str(v.get("kayit") or ""), str(v.get("link") or "")}
    try:
        k = json.loads((KAYIT / ".kayit_canli.json").read_text(encoding="utf-8"))
        if k.get("kayit"):
            bilinen.add(str(k.get("hedef") or ""))
    except Exception:  # noqa: BLE001
        pass
    return [f for f in adaylar if str(f) not in bilinen]


def _sahipsiz_isle():
    for f in _sahipsiz_kayitlar():
        sure = _kayit_suresi(f)
        if sure < 60:
            continue
        mik = f.with_name(f.stem + ".mik.m4a")
        print(f"İşlenmemiş toplantı kaydı bulundu, işe veriliyor: {f.name}", flush=True)
        with app.test_request_context("/api/kayit/dosya", method="POST",
                                      json={"dosya": str(f), "uygulama": "", "baslangic": f.stat().st_mtime - sure, "mik_dosya": str(mik) if mik.exists() else ""}):
            kayit_dosya()


def _sahipsiz_dongu():
    time.sleep(90)
    while True:
        try:
            _sahipsiz_isle()
        except Exception as e:  # noqa: BLE001
            print(f"Sahipsiz kayıt taraması: {e}", flush=True)
        time.sleep(20 * 60)


threading.Thread(target=_sahipsiz_dongu, daemon=True).start()

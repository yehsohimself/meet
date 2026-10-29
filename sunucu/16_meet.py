# sunucu/16_meet.py — Meet ve Couple uçları (2026-10-25: 16_altyapi_ve_meet.py'den ayrıldı; ürünler ayrı kurulabilsin diye).
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz. Bu dosya yoksa Meet/Couple kapalıdır.
# ----------------------------------------------------------------------------- atölye bilgi kartları (Couple)
@app.get("/api/atolye/bilgi")
def atolye_bilgi_durum():
    import atolye_bilgi
    return jsonify({"kategoriler": atolye_bilgi.durum(), "calisiyor": bakim_durum["calisiyor"], "kategori": bakim_durum["kategori"],
                    "son": (bakim_durum["log"] or [""])[-1], "oncelikli": bakim_durum["oncelikli"], "son_hata": bakim_durum["son_hata"],
                    "acik": ayarlar_oku().get("atolye_bakim", True)})


@app.get("/api/atolye/bilgi/<kkod>")
def atolye_bilgi_kart(kkod):
    import atolye_bilgi
    kat = next((k for k in atolye_bilgi.ana_kategoriler() if atolye_bilgi.atolye.kod(k) == kkod), None)
    kart = atolye_bilgi.kart_oku(kat) if kat else None
    if not kart:
        return jsonify({"hata": "Bu kategorinin bilgi kartı henüz yok."}), 404
    return jsonify({k: kart.get(k) for k in ("kategori", "guncelleme", "md", "olcu", "rakip", "gecmis", "bekleyen")}
                   | {"videolar": [{k: v.get(k) for k in ("kanal", "baslik", "url", "izlenme", "viral", "etkilesim", "tarih", "sure", "temel", "neden")}
                                   | {"kare": ((v.get("analiz") or {}).get("cekim") or {}).get("kanca_kare")} for v in kart.get("videolar") or []]})


@app.post("/api/atolye/bilgi/<kkod>/yenile")
def atolye_bilgi_yenile(kkod):
    import atolye_bilgi
    kat = next((k for k in atolye_bilgi.ana_kategoriler() if atolye_bilgi.atolye.kod(k) == kkod), None)
    if not kat:
        abort(404)
    if kat not in bakim_durum["oncelikli"] and not (bakim_durum["calisiyor"] and bakim_durum["kategori"] == kat):
        bakim_durum["oncelikli"].append(kat)
    return jsonify({"tamam": True})




# ----------------------------------------------------------------------------- Meet: danışman, şirketler, sözler, amaç, sinyaller, kişiler, Kısaca, tarifler, brief
@app.post("/api/danisman/<temel>")
def danisman_uret_api(temel):
    """Kariyer danışmanı notunu üretir (arka planda, ~1 dk); sonra Word belgesi ve Drive kopyası yenilenir."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    if danisman_durum.get(temel, {}).get("calisiyor"):
        return jsonify({"tamam": True})
    danisman_durum[temel] = {"calisiyor": True, "hata": ""}

    def _calis():
        import danisman
        try:
            d = json.loads(tj.read_text(encoding="utf-8"))
            dn = danisman.uret(d["veri"], d["segmentler"], log=lambda m: print(m, flush=True))
            if not dn:
                raise RuntimeError("Not üretilemedi (Claude kullanılamıyor olabilir)")
            with kilit:
                d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["danisman"] = dn
                tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            _belge_yenile(temel)
        except Exception as e:  # noqa: BLE001
            danisman_durum[temel]["hata"] = str(e)
        danisman_durum[temel]["calisiyor"] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/danisman-durum/<temel>")
def danisman_durum_get(temel):
    tj = _temel_dogrula(temel).with_suffix(".json")
    return jsonify({**(danisman_durum.get(temel) or {"calisiyor": False, "hata": ""}), "danisman": json.loads(tj.read_text(encoding="utf-8"))["veri"].get("danisman")})


sirket_durum = {"tarama": False, "yorum": {}}


@app.get("/api/sirketler")
def sirketler_get():
    import sirketler
    sirketler.logolari_uret()
    out = []
    for x in sirketler.liste() + [sirketler.GENEL]:
        y = sirketler.yorum_oku(x["kod"]) if x["kod"] != "genel" else None
        out.append({**x, "logo": sirketler.logo(x["kod"]), "yorum": y, "yorum_hazirlaniyor": bool(sirket_durum["yorum"].get(x["kod"])),
                    "musteri_logolari": {m: sirketler.logo(sirketler.kod_yap(m) + ("_urun" if sirketler.kod_yap(m) == x["kod"] else ""))
                                         for m in x.get("musteriler") or []}})
    return jsonify({"sirketler": out, "tarama": sirket_durum["tarama"]})


@app.post("/api/sirketler")
def sirketler_post():
    """Şirket tanımlarını kaydeder: {sirketler: [...]} (ad, musteriler, kisiler, alan, aciklama)."""
    import sirketler
    v = request.get_json(silent=True) or {}
    yeni = []
    for x in v.get("sirketler") or []:
        ad = str(x.get("ad") or "").strip()[:40]
        if not ad:
            continue
        yeni.append({"kod": x.get("kod") or sirketler.kod_yap(ad), "ad": ad, "aciklama": str(x.get("aciklama") or "")[:300],
                     "alan": [str(a).strip().lower() for a in x.get("alan") or [] if str(a).strip()][:5],
                     "musteriler": [str(m).strip()[:40] for m in x.get("musteriler") or [] if str(m).strip()][:80],
                     "kisiler": [str(m).strip()[:60] for m in x.get("kisiler") or [] if str(m).strip()][:200]})
    if yeni:
        sirketler.kaydet(yeni)
    return jsonify({"tamam": True})


@app.post("/api/sirketler/tara")
def sirketler_tara():
    """Şirketi olmayan (ya da {hepsi: true} ise tüm) toplantılara şirket atar (arka planda)."""
    if sirket_durum["tarama"]:
        return jsonify({"tamam": True})
    hepsi = bool((request.get_json(silent=True) or {}).get("hepsi"))
    sirket_durum["tarama"] = True

    def _calis():
        import sirketler
        try:
            for js in sorted(KLASOR.glob("transkript_*.json")):
                try:
                    d = json.loads(js.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                v = d["veri"]
                if not v.get("toplanti") or (v.get("sirket") and not hepsi):
                    continue
                sr = sirketler.sec(v, d["segmentler"], log=lambda m: print(m, flush=True))
                with kilit:
                    d = json.loads(js.read_text(encoding="utf-8"))
                    d["veri"]["sirket"] = sr["kod"]; d["veri"]["sirket_neden"] = sr.get("neden", "")
                    if (d["veri"].get("musteri") or "Diğer") == "Diğer" and sr.get("musteri"):
                        d["veri"]["musteri_tahmin"] = sr["musteri"]
                    js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
                sirketler.ogren(sr["kod"], d["veri"])
                print(f"Şirket: {v.get('baslik', '')[:50]} → {sr['kod']}", flush=True)
        finally:
            sirket_durum["tarama"] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.post("/api/sirket/<kod>/toplanti/<temel>")
def sirket_degistir(kod, temel):
    """Toplantıyı elle başka şirkete taşır; kişiler o şirkete öğrenilir."""
    import sirketler
    tj = _temel_dogrula(temel).with_suffix(".json")
    if kod not in {x["kod"] for x in sirketler.liste()} | {"genel"}:
        abort(404)
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["sirket"] = kod; d["veri"]["sirket_neden"] = "elle"
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    sirketler.ogren(kod, d["veri"])
    try:
        _drive_yerlestir(temel)
    except Exception as e:  # noqa: BLE001
        print(f"Drive taşıma hatası: {e}", flush=True)
    return jsonify({"tamam": True})


@app.post("/api/drive/duzenle")
def drive_duzenle():
    """Var olan toplantı klasörlerini şirket/müşteri düzenine taşır (bir kez; yeni toplantılar zaten bu düzende yüklenir)."""
    tasinan = []
    for js in sorted(KLASOR.glob("transkript_*.json")):
        try:
            if json.loads(js.read_text(encoding="utf-8"))["veri"].get("toplanti"):
                y = _drive_yerlestir(js.stem)
                if y:
                    tasinan.append(y)
        except Exception as e:  # noqa: BLE001
            print(f"Drive düzenleme hatası ({js.stem}): {e}", flush=True)
    return jsonify({"tasinan": tasinan})


@app.post("/api/sirket/<kod>/yorum")
def sirket_yorum(kod):
    """Şirketin son 45 günlük toplantılarından genel yorum (arka planda, ~40 sn)."""
    import sirketler
    if sirket_durum["yorum"].get(kod):
        return jsonify({"tamam": True})
    sirket_durum["yorum"][kod] = True

    def _calis():
        try:
            sinir = time.time() - 45 * 86400; vs = []
            for js in KLASOR.glob("transkript_*.json"):
                try:
                    v = json.loads(js.read_text(encoding="utf-8"))["veri"]
                except Exception:  # noqa: BLE001
                    continue
                if v.get("toplanti") and v.get("sirket") == kod and (v.get("olusturma") or 0) >= sinir:
                    vs.append(v)
            vs.sort(key=lambda v: -(v.get("olusturma") or 0))
            sirketler.yorum(kod, vs)
        except Exception as e:  # noqa: BLE001
            print(f"Şirket yorumu hatası: {e}", flush=True)
        sirket_durum["yorum"][kod] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/sozler")
def sozler_get():
    """Söz takibi: kullanıcının toplantılarda üstlendiği açık işler (+ başkalarından beklenenler), güne çevrilmiş son tarihle."""
    import sozler
    return jsonify(sozler.liste())


sinyal_durum = {"tarama": False}


@app.post("/api/amac")
def amac_kaydet_api():
    """Amaç kapısı: {anahtar ('<bas>|<ad>' ya da 'elle'), metin, ad, bas}."""
    import sinyaller
    v = request.get_json(silent=True) or {}
    sinyaller.amac_kaydet(str(v.get("anahtar") or "elle")[:200], v.get("metin"), str(v.get("ad") or "")[:120], v.get("bas") or 0)
    return jsonify({"tamam": True})


@app.get("/api/amac")
def amac_oku_api():
    import sinyaller
    return jsonify({"metin": sinyaller.amac_oku(request.args.get("anahtar", "elle"))})


def _sinyal_isle(tj):
    import sinyaller
    d = json.loads(tj.read_text(encoding="utf-8"))
    sy = sinyaller.uret(d["veri"], d["segmentler"], tj.stem, log=lambda m: print(m, flush=True))
    if sy:
        with kilit:
            d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["sinyaller"] = sy
            if sy.get("amac"):
                d["veri"]["amac"] = sy["amac"]
            tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return sy


@app.post("/api/sinyaller/tara")
def sinyaller_tara():
    """Sinyali olmayan toplantılar (eskiden yeniye: çelişki ve kırılmalar için geçmiş sırayla oluşsun), arka planda."""
    if sinyal_durum["tarama"]:
        return jsonify({"tamam": True})
    sinyal_durum["tarama"] = True

    def _calis():
        try:
            adaylar = []
            for js in KLASOR.glob("transkript_*.json"):
                try:
                    v = json.loads(js.read_text(encoding="utf-8"))["veri"]
                except Exception:  # noqa: BLE001
                    continue
                if v.get("toplanti") and not v.get("sinyaller") and (v.get("sirket") or "") != "genel":
                    adaylar.append((v.get("olusturma") or 0, js))
            for _z, js in sorted(adaylar):
                try:
                    _sinyal_isle(js)
                except Exception as e:  # noqa: BLE001
                    print(f"Sinyal hatası ({js.stem}): {e}", flush=True)
        finally:
            sinyal_durum["tarama"] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/tahminler")
def tahminler_get():
    import sinyaller
    return jsonify(sinyaller.defter())


@app.post("/api/tahmin/<tid>")
def tahmin_post(tid):
    import sinyaller
    sinyaller.tahmin_sonuc(tid, str((request.get_json(silent=True) or {}).get("sonuc") or ""))
    return jsonify({"tamam": True})


@app.get("/api/kapsam")
def kapsam_get():
    """Kapsam kayması: şirket şirket son N günün kapsam dışı istekleri; gün ücreti ayarlıysa tutar."""
    import sinyaller
    ay = ayarlar_oku()
    return jsonify({"sirketler": sinyaller.kapsam_ozeti(int(request.args.get("gun", 31))), "gun_ucreti": ay.get("gun_ucreti") or 0,
                    "para": ay.get("para_birimi") or "€", "gun_saat": ay.get("gun_saat") or 8})


@app.post("/api/kapsam/eposta")
def kapsam_eposta():
    """Ek iş (change order) e-postası taslağı: Claude yazar, Mail'de GÖNDERİLMEMİŞ taslak açılır; metin de döner."""
    import sinyaller
    import claude_yaz
    v = request.get_json(silent=True) or {}
    kod = str(v.get("sirket") or "")
    oz = sinyaller.kapsam_ozeti(int(v.get("gun", 31))).get(kod)
    if not oz:
        return jsonify({"hata": "Bu şirkette kapsam dışı istek yok."}), 400
    ay = ayarlar_oku(); ucret = ay.get("gun_ucreti") or 0; para = ay.get("para_birimi") or "€"; gs = ay.get("gun_saat") or 8
    liste = "\n".join(f"- {x['istek']} ({x.get('kim') or ''}, {x['toplanti'][:40]}, ~{x['saat']} saat)" for x in oz["istekler"])
    tutar = f"Toplam ~{oz['saat']:.0f} saat" + (f" ≈ {oz['saat'] / gs * ucret:,.0f} {para} (gün ücreti {ucret} {para})" if ucret else "")
    istem = ("Kullanıcı serbest çalışan bir kreatif. Aşağıdaki ek istekler toplantılarda geldi ve anlaşılan işin dışında kalıyor. Ajans tarafındaki muhatabına "
             "gidecek KISA, kibar ama net bir e-posta yaz: teşekkür, ek işleri madde madde (süreyle), bunları ayrı bir iş kalemi olarak planlamak istediği, "
             "onay rica ettiği. Suçlayıcı değil; ilişkiyi koruyan, profesyonel. Türkçe, en fazla 140 kelime. İlk satır 'Konu: ...'.\n\n"
             f"İstekler:\n{liste}\n{tutar}")
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return jsonify({"hata": "Claude kullanılamıyor."}), 503
        metin = claude_yaz.sor(istem, "", zaman_asimi=180).strip()
    m = re.match(r"^\s*Konu:\s*(.+)", metin)
    konu = m.group(1).strip() if m else "Ek iş kalemleri"
    govde = metin[m.end():].strip() if m else metin
    hata = ""
    if v.get("ac"):
        import notlar as notlar_modulu
        hata = notlar_modulu.taslak_ac(konu, govde, [], (ay.get("benim_epostalar") or [""])[0]) or ""
    return jsonify({"konu": konu, "govde": govde, "hata": hata})


kisi_durum = {}


@app.get("/api/kisiler")
def kisiler_get():
    import kisiler
    return jsonify(kisiler.liste())


@app.get("/api/kisi/<kod>")
def kisi_get(kod):
    """Kişi profili + 'bilmen gereken' notu; not yoksa ya da yeni toplantı geldiyse arka planda tazelenir."""
    import kisiler
    kod = kisiler.cozumle(kod)
    p = kisiler.profil(kod); p.pop("_sozleri", None)
    n = kisiler.not_oku(kod)
    if p["toplantilar"] and (not n or n.get("toplanti") != len(p["toplantilar"])) and not kisi_durum.get(kod):
        kisi_durum[kod] = True

        def _calis():
            try:
                kisiler.not_uret(kod)
            except Exception as e:  # noqa: BLE001
                print(f"Kişi notu hatası: {e}", flush=True)
            kisi_durum[kod] = False
        threading.Thread(target=_calis, daemon=True).start()
    p["not"] = n; p["not_hazirlaniyor"] = bool(kisi_durum.get(kod))
    return jsonify(p)


kisaca_durum = {}


@app.post("/api/kisaca/<temel>")
def kisaca_uret_api(temel):
    """Toplantı kartı (1-2 paragraf özet + kişi kişi işler) yoksa ya da {yenile: true} ise arka planda üretir."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    if kisaca_durum.get(temel, {}).get("calisiyor"):
        return jsonify({"tamam": True})
    kisaca_durum[temel] = {"calisiyor": True, "hata": ""}

    def _calis():
        import kisaca
        try:
            d = json.loads(tj.read_text(encoding="utf-8"))
            k = kisaca.uret(d["veri"], d["segmentler"], log=lambda m: print(m, flush=True))
            if not k:
                raise RuntimeError("Özet üretilemedi")
            try:                                            # kararlar önceki toplantılarınkine bağlanır (karar_zinciri.py)
                import karar_zinciri
                karar_zinciri.zincirle({**d["veri"], "kisaca": k}, temel, kilit=kilit, log=lambda m: print(m, flush=True))
            except Exception as e:  # noqa: BLE001
                print(f"Karar zinciri kurulamadı ({e})", flush=True)
            with kilit:
                d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["kisaca"] = k
                tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            _belge_yenile(temel)
        except Exception as e:  # noqa: BLE001
            kisaca_durum[temel]["hata"] = str(e)
        kisaca_durum[temel]["calisiyor"] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/kisaca-durum/<temel>")
def kisaca_durum_get(temel):
    tj = _temel_dogrula(temel).with_suffix(".json")
    return jsonify({**(kisaca_durum.get(temel) or {"calisiyor": False, "hata": ""}), "kisaca": json.loads(tj.read_text(encoding="utf-8"))["veri"].get("kisaca")})


@app.post("/api/kisaca/<temel>/is")
def kisaca_is(temel):
    """Bir işi tamamlandı/tamamlanmadı işaretler: {k: kişi sırası ya da -1 (belirsiz), i: iş sırası, bitti}."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    v = request.get_json(silent=True) or {}
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); ks = d["veri"].get("kisaca") or {}
        try:
            k_ = int(v.get("k"))
            liste = ks["senden_karar"] if k_ == -2 else ks["belirsiz"] if k_ < 0 else ks["kisiler"][k_]["isler"]
            liste[int(v.get("i"))]["bitti"] = bool(v.get("bitti"))
        except (KeyError, IndexError, TypeError, ValueError):
            return jsonify({"hata": "İş bulunamadı"}), 404
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    threading.Thread(target=_belge_yenile, args=(temel,), daemon=True).start()   # Word'deki ☐/☑ da güncel kalsın
    return jsonify({"tamam": True})


tarif_durum = {}


@app.get("/api/tarifler")
def tarifler_get():
    import tarifler
    return jsonify(tarifler.liste())


@app.post("/api/tarifler")
def tarif_kaydet():
    """Kendi tarifiniz: {ad, istem} kaydeder; {sil: kod} siler."""
    import tarifler
    v = request.get_json(silent=True) or {}
    if v.get("sil"):
        tarifler.ozel_sil(str(v["sil"])); return jsonify({"tamam": True})
    try:
        return jsonify({"kod": tarifler.ozel_kaydet(v.get("ad"), v.get("istem"))})
    except ValueError as e:
        return jsonify({"hata": str(e)}), 400


@app.post("/api/tarif/<temel>")
def tarif_calistir(temel):
    """Tarifi toplantıya uygular (arka planda); sonuç veri["tarifler"][kod]. Durum: GET /api/tarif-durum/<temel>."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    kod = str((request.get_json(silent=True) or {}).get("kod") or "")
    anahtar = f"{temel}|{kod}"
    if tarif_durum.get(anahtar, {}).get("calisiyor"):
        return jsonify({"tamam": True})
    tarif_durum[anahtar] = {"calisiyor": True, "hata": ""}

    def _calis():
        import tarifler
        try:
            sonuc = tarifler.calistir(tj, kod, log=lambda m: print(m, flush=True))
            with kilit:
                d = json.loads(tj.read_text(encoding="utf-8"))
                d["veri"].setdefault("tarifler", {})[kod] = sonuc
                tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            tarif_durum[anahtar]["hata"] = str(e)
        tarif_durum[anahtar]["calisiyor"] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/tarif-durum/<temel>")
def tarif_durum_get(temel):
    tj = _temel_dogrula(temel).with_suffix(".json")
    kod = request.args.get("kod", "")
    veri = json.loads(tj.read_text(encoding="utf-8"))["veri"]
    return jsonify({**(tarif_durum.get(f"{temel}|{kod}") or {"calisiyor": False, "hata": ""}), "sonuc": (veri.get("tarifler") or {}).get(kod)})


@app.post("/api/brief/<temel>")
def brief_uret(temel):
    tj = _temel_dogrula(temel).with_suffix(".json")
    if brief_durum.get(temel, {}).get("calisiyor"):
        return jsonify({"hata": "Brief zaten hazırlanıyor."}), 409
    brief_durum[temel] = {"calisiyor": True, "hata": ""}

    def _calis():
        import haftalik
        try:
            haftalik.brief(tj)
        except Exception as e:  # noqa: BLE001
            brief_durum[temel]["hata"] = str(e)
        brief_durum[temel]["calisiyor"] = False
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.get("/api/brief-durum/<temel>")
def brief_durum_get(temel):
    tj = _temel_dogrula(temel).with_suffix(".json")
    veri = json.loads(tj.read_text(encoding="utf-8"))["veri"]
    return jsonify({**(brief_durum.get(temel) or {"calisiyor": False, "hata": ""}), "brief": veri.get("brief")})


@app.post("/api/takip-eposta/<temel>")
def takip_eposta(temel):
    """Katılımcılara takip e-postası taslağı: üretir (yoksa ya da yenile), ac=True ise Mail'de GÖNDERİLMEMİŞ taslak açar."""
    import haftalik
    import notlar as notlar_modulu
    tj = _temel_dogrula(temel).with_suffix(".json")
    v = request.get_json(silent=True) or {}
    veri = json.loads(tj.read_text(encoding="utf-8"))["veri"]
    e = veri.get("takip_eposta")
    try:
        if not e or v.get("yenile"):
            e = haftalik.takip_epostasi(tj)
    except Exception as ex:  # noqa: BLE001
        return jsonify({"hata": f"Taslak hazırlanamadı: {ex}"}), 500
    if v.get("ac"):
        h = notlar_modulu.taslak_ac(e["konu"], e["govde"], e.get("alicilar") or [], notlar_modulu.alici_sec(veri))
        if h:
            return jsonify({"hata": h, "eposta": e}), 500
    return jsonify({"tamam": True, "eposta": e})



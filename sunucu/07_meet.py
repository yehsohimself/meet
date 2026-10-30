# sunucu/07_meet.py — Meet: Chrome uzantısı ve kayıt uçları, toplantı adı düzeltme, Google Drive bağlantısı (2026-10-29: 07_ghost.py'den ayrıldı;
# Meet ayrı depo olarak kesilebilsin diye). site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.


@app.post("/api/toplanti/<temel>/duzelt")
def toplanti_duzelt(temel):
    """{konu, musteri}: toplantının adını/müşterisini düzeltir; belgeler yeniden yazılır, Drive klasörü yeni adla kurulur, eskisi Çöp'e taşınır."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    v = request.get_json(silent=True) or {}
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); veri = d["veri"]
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}\.\d{2})", veri.get("baslik") or "")
        zaman = m.group(1) if m else time.strftime("%Y-%m-%d %H.%M", time.localtime(veri.get("olusturma") or time.time()))
        konu = re.sub(r'[\\/:*?"<>|]+', " ", str(v.get("konu") or "")).strip()[:90] or re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", veri.get("baslik") or "").split(" · ")[0]
        musteri = str(v.get("musteri") or veri.get("musteri") or "Diğer").strip()[:40]
        if v.get("sirket"):
            veri["sirket"] = re.sub(r"[^a-z0-9_-]", "", str(v["sirket"]).lower())[:30]; veri["sirket_neden"] = "elle"
        veri["baslik"] = f"{zaman} · {konu}" + (f" · {musteri}" if musteri and musteri != "Diğer" else ""); veri["musteri"] = musteri; veri["baslik_kaynak"] = "elle"
        ciktilari_yaz(KLASOR / temel, veri, d["segmentler"])
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    eski = Path(veri.get("drive") or "")
    if not veri.get("drive"):                          # Drive'a hiç gitmemiş (kapalı ya da onay bekliyordu): yalnızca ad/şirket değişir
        return jsonify({"tamam": True, "baslik": veri["baslik"]})
    alt, dosyalar = _drive_dosyalari(temel, veri, zaman, konu, musteri, veri.get("kayit"))
    hedef, hata = _drive_kopyala(dosyalar, alt)
    if hata:
        return jsonify({"tamam": True, "baslik": veri["baslik"], "uyari": f"Drive güncellenemedi: {hata}"})
    if eski.is_dir() and eski != Path(hedef):
        _drive_cope(eski)
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["drive"] = str(hedef)
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify({"tamam": True, "baslik": veri["baslik"], "drive": str(hedef)})


_drive_memo = {"t": 0.0, "v": None}


def _drive_bagli_onbellekli():
    """Meet sayfası 15 sn'de bir soruyor; her soruda `rclone listremotes` alt süreci açılıyordu (4 günde 3.451). 10 dk geçerli (2026-10-25)."""
    if _drive_memo["v"] is None or time.time() - _drive_memo["t"] > 600:
        _drive_memo.update(t=time.time(), v=_drive_bagli())
    return _drive_memo["v"]


@app.get("/api/drive")
def drive_get():
    ay = ayarlar_oku()
    yol = _drive_klasor_yolu()
    return jsonify({"kurulu": RCLONE.exists(), "bagli": _drive_bagli_onbellekli(), "calisiyor": drive_durum["calisiyor"], "hata": drive_durum["hata"],
                    "acik": ay.get("drive", True), "klasor": ay.get("drive_klasor"), "yol": str(yol) if yol else "", "yol_ayar": ay.get("drive_yol", ""),
                    "oto_kayit": ay.get("oto_kayit", True), "musteriler": ay.get("musteriler", []), "kaydedici": (KLASOR / "kaydedici" / "kaydedici").exists()})


@app.post("/api/drive/baglan")
def drive_baglan():
    if not RCLONE.exists():
        return jsonify({"hata": "Drive aracı henüz kurulu değil."}), 503
    if drive_durum["calisiyor"]:
        return jsonify({"tamam": True, "calisiyor": True})
    threading.Thread(target=_drive_baglan, daemon=True).start()
    return jsonify({"tamam": True, "calisiyor": True})


@app.delete("/api/drive")
def drive_kopar():
    subprocess.run([str(RCLONE), "config", "delete", DRIVE_REMOTE], capture_output=True, timeout=20)
    return jsonify({"tamam": True})


@app.post("/api/drive/yukle/<temel>")
def drive_yukle_el(temel):
    """Var olan bir transkripti (belgeler + varsa kayıt) elle Drive'a yükler."""
    t = _temel_dogrula(temel)
    if not _drive_bagli():
        return jsonify({"hata": "Drive bağlı değil."}), 400
    veri = json.loads(t.with_suffix(".json").read_text(encoding="utf-8"))["veri"]
    ad = re.sub(r'[\\/:*?"<>|]+', " ", veri.get("baslik") or temel).strip()[:80]
    ay = ayarlar_oku(); klasor = f"{ay.get('drive_klasor') or 'Transkript/Toplantılar'}/{ad}"
    dosyalar = [(t.with_suffix(".docx"), f"{ad}.docx"), (t.with_suffix(".txt"), f"{ad}.txt")]
    if veri.get("kayit") and Path(veri["kayit"]).exists():
        dosyalar.append((Path(veri["kayit"]), f"{ad} (kayıt).m4a"))
    hata = _drive_yukle(dosyalar, klasor)
    if hata:
        return jsonify({"hata": hata}), 500
    veri["drive"] = klasor
    with kilit:
        d = json.loads(t.with_suffix(".json").read_text(encoding="utf-8")); d["veri"]["drive"] = klasor
        t.with_suffix(".json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify({"tamam": True, "klasor": klasor})


uzanti_durum = {"zaman": 0, "platform": "", "baslik": "", "katilimcilar": [], "kayit": "", "arama": False, "bekleme": False}
UZANTI_DURUM_DOSYASI = KAYIT / ".uzanti_durum.json"
try:                                                          # site yeniden başlasa da son durum kalsın
    uzanti_durum.update(json.loads(UZANTI_DURUM_DOSYASI.read_text(encoding="utf-8")))
except Exception:  # noqa: BLE001
    pass


def _katilimci_temizle(liste):
    """Meet düğme etiketlerinden ("Pin X to your main screen", "More options for X", "Mute") adları ayıklar."""
    sonuc = []
    for s in liste or []:
        s = re.sub(r"\s+", " ", str(s)).strip()
        m = (re.match(r"^(?:Pin|Unpin) (.+?) (?:to|from) your main screen$", s, re.I) or re.match(r"^More options for (.+)$", s, re.I)
             or re.match(r"^(.+?) (?:kişisini|adlı kişiyi) .*$", s, re.I) or re.match(r"^(.+?) için diğer seçenekler$", s, re.I))
        if m:
            s = m.group(1).strip()
        if not s or len(s) > 60 or re.fullmatch(r"(mute|unmute|pin|unpin|more options|remove|you|siz|sen|host|sunucu|presenting|sunuyor|sessize al|sesi aç|reframe|backgrounds and effects|apply visual effects|arka planlar ve efektler|görsel efektler)", s, re.I):
            continue
        if "." in s or "?" in s or "!" in s or len(s.split()) > 4 or not re.match(r"^[^\W\d_]", s):
            continue                                              # cümle/uyarı metni ("Others might still see your full video.")
        if re.search(r"to your main screen|options for|kişisini|seçenekler", s, re.I):
            continue
        if s not in sonuc:
            sonuc.append(s)
    return sonuc[:50]


@app.post("/api/uzanti/durum")
def uzanti_durum_post():
    """Chrome uzantısının nabzı: Meet sekmesi açıkken 10 sn'de bir gelir; kaydedici tarayıcıyı atlar."""
    v = request.get_json(silent=True) or {}
    baslik = str(v.get("baslik") or "")[:120]
    if v.get("platform") == "meet" and baslik and not re.search(r"^Meet - |- Google Meet$", baslik) and not v.get("toplanti_adi"):
        baslik = ""                                            # Meet sekmesinin başlığı toplantı adı değilse (ör. Gemini paneli) alma
    # 2026-10-30: uzantı iki gerçek görüşmede "aramada" diyemedi (düğme adları tutmadı) ama katılımcıları okuyordu; başlık Meet'in kendi biçimindeyse
    # ve en az iki katılımcı görülüyorsa görüşme sayılır (kaydedicinin uzantı kapısı ve hazırlık notu buna dayanır)
    if not v.get("aktif") and not v.get("bekleme") and v.get("platform") == "meet" and re.search(r"^Meet - |- Google Meet$", baslik) \
            and len(_katilimci_temizle(v.get("katilimcilar")) or []) >= 2:
        v["aktif"] = True
    bekleme = bool(v.get("bekleme")) and not v.get("aktif")      # giriş (bekleme) ekranı: yalnız o ekrandaki adlar, eski toplantının adları değil
    uzanti_durum.update({"zaman": time.time(), "platform": str(v.get("platform") or "")[:30], "baslik": baslik, "arama": bool(v.get("aktif")), "bekleme": bekleme,
                         "katilimcilar": _katilimci_temizle(v.get("katilimcilar")) or ([] if bekleme else uzanti_durum.get("katilimcilar", [])), "kayit": str(v.get("kayit") or ""),
                         "surum": str(v.get("surum") or uzanti_durum.get("surum") or "")[:12]})
    try:
        KAYIT.mkdir(exist_ok=True); UZANTI_DURUM_DOSYASI.write_text(json.dumps(uzanti_durum, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        UZANTI_NABIZ.write_text(str(v.get("surum") or "")[:12], encoding="utf-8")
    except OSError:
        pass
    if v.get("aktif") and globals().get("_kayit_disi_eslesen") and _kayit_disi_eslesen(str(v.get("baslik") or ""), baslik, v.get("toplanti_adi")):
        KAYIT.mkdir(exist_ok=True)                 # kaydedilmeyen toplantı (30, ör. haftalık kurs): kaydedici bu bayrağı görünce kayda başlamaz
        (KAYIT / ".kayit_disi_arama").write_text(str(time.time()), encoding="utf-8")
    elif v.get("aktif"):                           # uzantı "aramadayım" diyor: kaydedici tarayıcı kaydını ancak bu bayrak tazeyken başlatır
        KAYIT.mkdir(exist_ok=True)
        (KAYIT / ".uzanti_arama").write_text(str(time.time()), encoding="utf-8")
        _canli_brif_tetikle(uzanti_durum.get("baslik") or "", uzanti_durum.get("katilimcilar") or [], uzanti_durum.get("platform") or "")
    elif bekleme:
        _canli_brif_tetikle(baslik, uzanti_durum.get("katilimcilar") or [], uzanti_durum.get("platform") or "", bekleme=True)
    else:
        CANLI_BRIF["ilk"] = 0
    if v.get("aktif") and v.get("kayit"):          # yalnızca uzantı sesi kendisi kaydediyorsa masaüstü kaydedici tarayıcıyı atlar
        KAYIT.mkdir(exist_ok=True)
        (KAYIT / ".uzanti_aktif").write_text(str(time.time()), encoding="utf-8")
    return jsonify({"tamam": True, "oto_kayit": ayarlar_oku().get("oto_kayit", True)})


CANLI_BRIF = {"ilk": 0, "anahtar": "", "kisi": 0, "calisiyor": False, "kayit": None, "tekrar": False,
              "bekleme_anahtar": "", "bekleme_kisi": 0, "bekleme_t": 0, "bekleme_sayi": 0, "giristen": False}


def _canli_brif_tetikle(baslik, katilimcilar, platform, bekleme=False):
    """Takvimsiz hazırlık notu (2026-10-23): uzantı aramada dedikten 45 sn sonra (adlar toplansın) katılımcı adlarıyla önceki toplantılardan not;
    ilk 20 dakikada katılımcı sayısı 2 artarsa bir kez yenilenir. Takvim bağlı değilken yan panel ve canlı asistan boş kalıyordu.
    Giriş ekranı (2026-10-28, bekleme=True): kullanıcı görüşmeye girmeden, ekrandaki toplantı adı ya da içerideki kişilerle hemen yazılır; içeriye
    yeni biri girdikçe en çok iki kez tazelenir. Görüşmeye girilince aynı not sürer, yalnız 2+ yeni kişi gelirse bir kez yenilenir."""
    simdi = time.time()
    onceki, CANLI_BRIF["son_nabiz"] = CANLI_BRIF.get("son_nabiz", 0), simdi
    if bekleme and simdi - onceki > 120:                    # yeni bir giriş ekranı: önceki toplantının notu burada görünmesin
        CANLI_BRIF.update({"kayit": None, "bekleme_anahtar": "", "bekleme_sayi": 0, "bekleme_kisi": 0})
    benim = (ayarlar_oku().get("benim_adim") or "").strip().casefold()
    import kisiler as kisiler_modulu                       # İngilizce Meet arayüz yazıları ('Reframe', 'Zoom in'...) katılımcı sanılmasın
    kisiler = [k for k in katilimcilar if kisiler_modulu.ad_mi(k) and not (benim and str(k).casefold().startswith(benim))]
    if bekleme:
        ad = _toplanti_adi_temizle(baslik) or ""
        if CANLI_BRIF["calisiyor"] or (not kisiler and not ad):
            return
        anahtar = f"{platform}|{ad}|{time.strftime('%Y-%m-%d %H')}"
        if anahtar == CANLI_BRIF["bekleme_anahtar"]:
            if len(kisiler) <= CANLI_BRIF["bekleme_kisi"] or CANLI_BRIF["bekleme_sayi"] >= 3 or simdi - CANLI_BRIF["bekleme_t"] < 20:
                return
        else:
            CANLI_BRIF["bekleme_sayi"] = 0
        CANLI_BRIF.update({"bekleme_anahtar": anahtar, "bekleme_kisi": len(kisiler), "bekleme_t": simdi, "calisiyor": True,
                           "bekleme_sayi": CANLI_BRIF["bekleme_sayi"] + 1})
        _canli_brif_calistir(baslik, kisiler, platform, "giriş ekranı")
        return
    if not CANLI_BRIF["ilk"]:
        CANLI_BRIF.update({"ilk": simdi, "anahtar": "", "kisi": 0, "tekrar": False, "giristen": False})
        if CANLI_BRIF.get("kayit") and simdi - CANLI_BRIF["bekleme_t"] < 1800:   # not giriş ekranında yazıldı: 45 sn'de yeniden yazılmaz
            CANLI_BRIF.update({"giristen": True, "kisi": CANLI_BRIF["bekleme_kisi"]})
    if CANLI_BRIF["calisiyor"] or simdi - CANLI_BRIF["ilk"] < 45 or not kisiler:
        return
    anahtar = f"{platform}|{baslik}|{time.strftime('%Y-%m-%d')}|{int(CANLI_BRIF['ilk'])}"
    if anahtar == CANLI_BRIF["anahtar"] or CANLI_BRIF.get("giristen"):
        if CANLI_BRIF["tekrar"] or len(kisiler) < CANLI_BRIF["kisi"] + 2 or simdi - CANLI_BRIF["ilk"] > 1200:
            return
        CANLI_BRIF["tekrar"] = True
    CANLI_BRIF.update({"anahtar": anahtar, "kisi": len(kisiler), "calisiyor": True, "giristen": False})
    _canli_brif_calistir(baslik, kisiler, platform, "görüşme")


def _canli_brif_calistir(baslik, kisiler, platform, nerede):
    def _is():
        try:
            import onbrifing
            ad = _toplanti_adi_temizle(baslik) or ""
            CANLI_BRIF["kayit"] = onbrifing.canli_hazirla(ad, kisiler, platform, log=lambda m: print(m, flush=True))
            print(f"Canlı hazırlık notu ({nerede}): {ad or 'adsız toplantı'} · {', '.join(kisiler[:5])}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"Canlı hazırlık notu yazılamadı: {e}", flush=True)
        finally:
            CANLI_BRIF["calisiyor"] = False
    threading.Thread(target=_is, daemon=True).start()


@app.post("/api/uzanti/olaylar")
def uzanti_olaylar():
    """Uzantıdan mutlak zamanlı 'kim konuşuyor' olayları ([{ts, ad}]); masaüstü kaydedicinin kaydıyla sonradan eşlenir."""
    v = request.get_json(silent=True) or {}
    KAYIT.mkdir(exist_ok=True)
    with open(KAYIT / "uzanti_olaylar.jsonl", "a", encoding="utf-8") as f:
        for x in (v.get("olaylar") or [])[:500]:
            try:
                f.write(json.dumps({"ts": float(x.get("ts", 0)), "ad": str(x.get("ad") or "")[:60]}, ensure_ascii=False) + "\n")
            except (TypeError, ValueError):
                continue
    if v.get("katilimcilar"):
        uzanti_durum["katilimcilar"] = [str(x)[:60] for x in v["katilimcilar"]][:50]; uzanti_durum["zaman"] = time.time()
    if v.get("baslik"):
        uzanti_durum["baslik"] = str(v["baslik"])[:120]
    return jsonify({"tamam": True})


def _uzanti_olaylari(bas, bit):
    """Mutlak zamanlı uzantı olaylarını kayıt aralığına göre göreli saniyeye çevirir."""
    yol = KAYIT / "uzanti_olaylar.jsonl"
    if not yol.exists():
        return []
    out = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(satir)
            if bas - 5 <= o["ts"] <= bit + 5:
                out.append({"t": max(0.0, o["ts"] - bas), "ad": o["ad"]})
        except Exception:  # noqa: BLE001
            continue
    return out


@app.get("/api/canli/notlar")
def canli_notlar_get():
    import notlarim
    return jsonify(notlarim.son(4))


@app.post("/api/canli/not")
def canli_not_post():
    """Toplantı sırasında not ya da 'önemli an' işareti (Transcript canlı kartı, Chrome yan paneli). {tur: not|isaret, metin} ya da {sil: id}."""
    import notlarim
    v = request.get_json(silent=True) or {}
    if v.get("sil"):
        notlarim.sil(v["sil"]); return jsonify({"tamam": True})
    if v.get("tur") != "isaret" and not str(v.get("metin") or "").strip():
        return jsonify({"hata": "Not boş"}), 400
    return jsonify(notlarim.ekle(v.get("tur") or "not", v.get("metin") or ""))


UZANTI_NABIZ = KAYIT / ".uzanti_nabiz"


@app.post("/api/uzanti/canli")
def uzanti_canli():
    """Uzantının dakikalık 'canlıyım' nabzı (toplantı olmasa da). Susarsa Transcript sayfası uyarır (16-20 Ekim'de günlerce fark edilmedi)."""
    v = request.get_json(silent=True) or {}
    KAYIT.mkdir(exist_ok=True)
    UZANTI_NABIZ.write_text(str(v.get("surum") or "")[:12], encoding="utf-8")
    return jsonify({"tamam": True})


@app.get("/api/uzanti/durum")
def uzanti_durum_get():
    d = dict(uzanti_durum); d["aktif"] = time.time() - d["zaman"] < 30
    d["bekleme"] = d["aktif"] and bool(d.get("bekleme")); d["arama"] = d["aktif"] and bool(d.get("arama"))   # giriş ekranı / gerçekten görüşmede
    try:
        d["disk_gb"] = round(shutil.disk_usage(str(KLASOR)).free / 1e9, 1)                    # Meet durum satırı: 10 GB altında uyarı
    except Exception:  # noqa: BLE001
        d["disk_gb"] = None
    try:                                                   # kaydedicinin yazdığı: toplantı yokken tarayıcı mikrofonu ne zamandır tutuyor
        m = json.loads((KAYIT / ".mik_durum.json").read_text(encoding="utf-8"))
        d["mik"] = m if time.time() - m.get("zaman", 0) < 120 else None
    except Exception:  # noqa: BLE001
        d["mik"] = None
    try:
        d["son_nabiz"] = max(UZANTI_NABIZ.stat().st_mtime if UZANTI_NABIZ.exists() else 0, d.get("zaman") or 0)
        d["nabiz_surum"] = UZANTI_NABIZ.read_text(encoding="utf-8") if UZANTI_NABIZ.exists() else ""
    except OSError:
        d["son_nabiz"] = d.get("zaman") or 0
    return jsonify(d)


@app.post("/api/kayit/<kid>/konusmacilar")
def kayit_konusmacilar(kid):
    """Uzantıdan 'kim ne zaman konuştu' satırları: [{"t": kayıt saniyesi, "ad": "Ayşe"}] (ve katılımcı listesi)."""
    if not re.match(r"^[0-9a-f]{8}$", kid) or not (KAYIT / f"{kid}.webm").exists():
        abort(404)
    v = request.get_json(silent=True) or {}
    yol = KAYIT / f"{kid}.konusmacilar.jsonl"
    with open(yol, "a", encoding="utf-8") as f:
        for x in (v.get("olaylar") or [])[:500]:
            try:
                f.write(json.dumps({"t": round(float(x.get("t", 0)), 2), "ad": str(x.get("ad") or "")[:60]}, ensure_ascii=False) + "\n")
            except (TypeError, ValueError):
                continue
    if v.get("katilimcilar"):
        m = KAYIT / f"{kid}.json"
        try:
            meta = json.loads(m.read_text(encoding="utf-8")); meta["katilimcilar"] = [str(x)[:60] for x in v["katilimcilar"]][:50]
            if v.get("baslik") and not meta.get("baslik"):
                meta["toplanti_adi"] = str(v["baslik"])[:120]
            m.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return jsonify({"tamam": True})


def _adlari_esle(segmentler, etiket, olaylar, log=lambda *_: None):
    """Uzantının 'kim konuşuyor' olaylarıyla (kayıt saniyesi → ad) konuşmacı kümelerine ad verir.
    Her küme için en çok çakışan ad; çakışma payı %45'i geçmeli ve ad tek bir kümeye verilmeli."""
    if not olaylar or not segmentler:
        return {}
    olaylar = sorted(olaylar, key=lambda o: o["t"])
    araliklar = []                        # (bas, bit, ad): bir olay sonraki olaya kadar sürer (en çok 15 sn)
    for i, o in enumerate(olaylar):
        if not o["ad"]:
            continue
        bit = olaylar[i + 1]["t"] if i + 1 < len(olaylar) else o["t"] + 6
        araliklar.append((o["t"], min(bit, o["t"] + 15), o["ad"]))
    puan = {}                             # küme -> ad -> çakışma sn
    for sg in segmentler:
        k = str(sg["k"])
        for b, e, ad in araliklar:
            c = min(sg["bit"], e) - max(sg["bas"], b)
            if c > 0:
                puan.setdefault(k, {}).setdefault(ad, 0.0); puan[k][ad] += c
    sure = {}
    for sg in segmentler:
        sure[str(sg["k"])] = sure.get(str(sg["k"]), 0.0) + sg["bit"] - sg["bas"]
    adaylar = []
    for k, d in puan.items():
        ad, c = max(d.items(), key=lambda x: x[1])
        if sure.get(k, 0) and c / sure[k] >= 0.45:
            adaylar.append((c / sure[k], k, ad))
    adaylar.sort(reverse=True)
    sonuc, kullanilan = {}, set()
    for _, k, ad in adaylar:
        if k in sonuc or ad in kullanilan or ad in etiket.values():
            continue
        sonuc[k] = ad; kullanilan.add(ad)
    if sonuc:
        log("      Toplantıdan adlar eşlendi: " + ", ".join(sonuc.values()))
    return sonuc


@app.post("/api/kayit/baslat")
def kayit_baslat():
    v = request.get_json(silent=True) or {}
    KAYIT.mkdir(exist_ok=True)
    # Parça gelmeden yarım kalmış (boş) kayıtları temizle (uzantı denemeleri biriktirmesin)
    try:
        for eski in KAYIT.glob("*.webm"):
            if eski.stat().st_size == 0 and time.time() - eski.stat().st_mtime > 600:
                eski.unlink(missing_ok=True); eski.with_suffix(".json").unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    kid = uuid.uuid4().hex[:8]
    (KAYIT / f"{kid}.webm").write_bytes(b"")
    (KAYIT / f"{kid}.json").write_text(json.dumps({"baslik": (v.get("baslik") or "")[:120], "kaynak": v.get("kaynak") or "", "baslangic": time.time()}, ensure_ascii=False), encoding="utf-8")
    return jsonify({"id": kid})


@app.post("/api/kayit/<kid>/parca")
def kayit_parca(kid):
    if not re.match(r"^[0-9a-f]{8}$", kid) or not (KAYIT / f"{kid}.webm").exists():
        abort(404)
    with open(KAYIT / f"{kid}.webm", "ab") as f:
        f.write(request.get_data())
    return jsonify({"tamam": True, "boyut": (KAYIT / f"{kid}.webm").stat().st_size})


@app.post("/api/kayit/<kid>/bitir")
def kayit_bitir(kid):
    if not re.match(r"^[0-9a-f]{8}$", kid) or not (KAYIT / f"{kid}.webm").exists():
        abort(404)
    v = request.get_json(silent=True) or {}
    meta = json.loads((KAYIT / f"{kid}.json").read_text(encoding="utf-8"))
    baslik = (v.get("baslik") or meta.get("baslik") or "").strip()[:120]
    zaman = time.strftime("%Y-%m-%d %H.%M", time.localtime(meta.get("baslangic") or time.time()))
    webm = KAYIT / f"{kid}.webm"
    if webm.stat().st_size < 1000:
        webm.unlink(missing_ok=True); (KAYIT / f"{kid}.json").unlink(missing_ok=True)
        return jsonify({"hata": "Kayıt boş görünüyor; mikrofon izni verilmemiş olabilir."}), 400
    stem = re.sub(r'[\\/:*?"<>|]+', " ", f"Toplantı {zaman}" + (f" · {baslik}" if baslik else "")).strip()
    m4a = KAYIT / f"{stem}.m4a"
    n = 2
    while m4a.exists():
        m4a = KAYIT / f"{stem} ({n}).m4a"; n += 1
    p = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-i", str(webm), "-vn", "-c:a", "aac", "-b:a", "128k", str(m4a)],
                       capture_output=True, text=True, timeout=1800)
    if p.returncode != 0 or not m4a.exists():
        return jsonify({"hata": "Kayıt dosyası dönüştürülemedi."}), 500
    webm.unlink(missing_ok=True); (KAYIT / f"{kid}.json").unlink(missing_ok=True)
    zc = KAYIT / f"{kid}.konusmacilar.jsonl"
    olaylar = []
    if zc.exists():
        for satir in zc.read_text(encoding="utf-8").splitlines():
            try:
                olaylar.append(json.loads(satir))
            except Exception:  # noqa: BLE001
                continue
        zc.unlink(missing_ok=True)
    r = _baslat({"link": str(m4a), "ozet": True, "konusmaci": True, "altyazi": False, "toplanti": True, "toplanti_baslik": baslik or meta.get("toplanti_adi", ""),
                 "kayit_dosya": str(m4a), "musteri": (v.get("musteri") or "")[:40], "kayit_baslangic": meta.get("baslangic"),
                 "uygulama": meta.get("kaynak") or "", "katilimcilar": meta.get("katilimcilar") or v.get("katilimcilar") or [], "konusmaci_olaylari": olaylar})
    j = r.get_json() if hasattr(r, "get_json") else (r[0].get_json() if isinstance(r, tuple) else {})
    return jsonify({"id": (j or {}).get("id"), "dosya": str(m4a)})

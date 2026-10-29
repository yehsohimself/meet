# sunucu/20_meet_gelisim.py — Meet'in kendini besleyen gelişimi (meet_gelisim.py): sağlık, kendiliğinden onarım, düzeltmelerden öğrenme, yenilik radarı,
# haftalık değerlendirme; konuşmacı ses örneği, ekranda paylaşılanlar, karşı tarafın sözleri için hatırlatma.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
import urllib.parse

from flask import g

import meet_gelisim

MEET_ADRES = "http://127.0.0.1:8766/"
meet_gelisim_durum = {"calisiyor": "", "hata": "", "son_saglik": 0}
EKRAN = KAYIT / ".ekran"


def _meet_url(temel=""):
    return MEET_ADRES + (f"#t={urllib.parse.quote(temel)}" if temel else "")


# ----------------------------------------------------------------------------- toplantı bitince (04_toplanti._toplanti_bitir_ic çağırır)
def _meet_on_adim(is_, d, veri, temel):
    """Kısaca'dan önce: katılımcı listesiyle eleyerek / ad önerisini teyit ederek ad; kaydedicinin aldığı ekran karelerinden 'Ekranda paylaşılanlar'."""
    log = lambda m: is_["log"].append(m)  # noqa: E731
    geri = meet_gelisim.taninani_dogrula(veri, log)
    if geri:
        meet_gelisim.olay("ad", "Katılımcılarda olmayan ad geri alındı: " + ", ".join(geri), temel)
    es = meet_gelisim.eleme(veri, d["segmentler"], log)
    for k, ad in es.items():
        veri["etiket"][k] = ad
    if es:
        veri.setdefault("adlar_kaynak", "eleme")
        try:
            import sesler as sesler_modulu
            sesler_modulu.ogren(veri)
        except Exception:  # noqa: BLE001
            pass
        meet_gelisim.olay("ad", "Katılımcı listesinden ad verildi: " + ", ".join(es.values()), temel)
    try:
        kb = int(float(is_.get("kayit_baslangic") or 0))
        kl = EKRAN / str(kb) if kb else None
        if kl and kl.is_dir():
            ek = _ekran_isle(kl, temel, log)
            if ek:
                veri["ekran"] = ek
    except Exception as e:  # noqa: BLE001
        log(f"      Ekran kareleri işlenemedi ({e})")


def _ekran_isle(klasor, temel, log=print):
    """Kaydedicinin toplantı penceresinden aldığı kareler (`<sn>.jpg`): yazı tanıma ile okunur, yazısız (yalnız yüzler) ve birbirinin aynısı olanlar
    atılır, kalanlar `kareler/<temel>/e_<sn>.jpg`. Döner: [{sn, kare, yazi}] (en çok 40)."""
    import difflib
    dosyalar = sorted(klasor.glob("*.jpg"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
    if not dosyalar:
        shutil.rmtree(klasor, ignore_errors=True); return []
    r = subprocess.run([PYTHON, "-c", "import goruntu,json,sys; print(json.dumps({p: goruntu.yazi_oku(p) for p in sys.argv[1:]}, ensure_ascii=False))",
                        *[str(p) for p in dosyalar]], capture_output=True, text=True, timeout=900, cwd=str(KLASOR))
    yazilar = json.loads(r.stdout or "{}") if r.returncode == 0 else {}
    hedef = KLASOR / "kareler" / temel; hedef.mkdir(parents=True, exist_ok=True)
    out, son = [], ""
    for p in dosyalar:
        y = " ".join(yazilar.get(str(p)) or []).strip()
        if len(y.split()) < 6:                              # sunum/belge değil (yüz karoları, boş ekran)
            continue
        if son and difflib.SequenceMatcher(None, son, y).ratio() >= 0.85:
            continue
        son = y
        sn = int(p.stem) if p.stem.isdigit() else 0
        ad = f"e_{sn}.jpg"
        shutil.copy2(p, hedef / ad)
        out.append({"sn": sn, "kare": ad, "yazi": y[:600]})
        if len(out) >= 40:
            break
    shutil.rmtree(klasor, ignore_errors=True)
    if out:
        log(f"      Ekranda paylaşılanlar: {len(out)} kare")
    return out


@app.get("/meet-ekran/<temel>/<dosya>")
def meet_ekran(temel, dosya):
    if not re.match(r"^[\w\-.]+$", temel) or not re.match(r"^e_\d+\.jpg$", dosya) or not (KLASOR / "kareler" / temel / dosya).exists():
        abort(404)
    return send_from_directory(str(KLASOR / "kareler" / temel), dosya, max_age=86400)


# ----------------------------------------------------------------------------- konuşmacı ses örneği (adsız kişiyi dinleyip ad vermek için)
@app.get("/api/meet/ses/<temel>/<k>.m4a")
def meet_ses_ornek(temel, k):
    tj = _temel_dogrula(temel).with_suffix(".json")
    d = json.loads(tj.read_text(encoding="utf-8")); v = d["veri"]
    kaynak = Path(v.get("kayit") or "")
    if not kaynak.is_file():
        try:
            kaynak = Path(str(_medya_yolu(temel)))                    # yüklenen dosya / indirilmiş kopya
        except Exception:  # noqa: BLE001
            abort(404)
    segs = sorted((s for s in d["segmentler"] if str(s.get("k")) == str(k)), key=lambda s: -(s["bit"] - s["bas"]))
    if not segs or not kaynak.is_file():
        abort(404)
    onb = KLASOR / ".onbellek" / "ses_ornek"; onb.mkdir(parents=True, exist_ok=True)
    sb = f"{s0['bas']:.2f}" if (s0 := segs[0]) else ""                   # bölüm ve kayıt da anahtarda: birleşen toplantıda eski küme sesi çalmasın
    cikti = onb / f"{hashlib.sha1(f'{temel}|{k}|{sb}|{kaynak.stat().st_mtime:.0f}'.encode()).hexdigest()[:16]}.m4a"
    if not cikti.exists():
        s = segs[0]; bas = max(0.0, s["bas"] + 0.2); sure_ = min(8.0, max(2.0, s["bit"] - bas))
        r = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-ss", f"{bas:.2f}", "-t", f"{sure_:.2f}", "-i", str(kaynak),
                            "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "64k", str(cikti)], capture_output=True, timeout=60)
        if r.returncode != 0 or not cikti.exists():
            abort(404)
    return send_from_directory(str(onb), cikti.name, mimetype="audio/mp4", max_age=3600)


def _medya_yolu(temel):
    v = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"]
    for aday in (v.get("kayit"), v.get("link"), v.get("kaynak_dosya")):
        if aday and Path(str(aday)).is_file():
            return Path(str(aday))
    raise FileNotFoundError(temel)


@app.get("/api/meet/toplanti/<temel>")
def meet_toplanti(temel):
    """Toplantı sayfasının Meet eklentisi için: adsız kişiler (konuşma süresi, ses örneği var mı), ekranda paylaşılanlar."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    d = json.loads(tj.read_text(encoding="utf-8")); v = d["veri"]
    sure = meet_gelisim.konusma_sureleri(d["segmentler"])
    ornek = Path(v.get("kayit") or "").is_file()
    kisiler = [{"k": k, "ad": ad, "sure": round(sure.get(str(k), 0)), "adsiz": bool(meet_gelisim.ADSIZ.match(str(ad)))} for k, ad in (v.get("etiket") or {}).items()]
    # 2026-10-27: adsız kişiye tek dokunuşla ad: toplantıdaki katılımcılardan henüz kimseye verilmemiş adlar (uzantı/takvim) ve ad önerileri
    import kisiler as kisiler_modulu
    verilen = {meet_gelisim._ilk(x["ad"]) for x in kisiler if not x["adsiz"]}
    adaylar = []
    for a in list(v.get("katilimcilar") or []) + [k.get("ad") for k in ((v.get("takvim") or {}).get("katilimcilar") or []) if isinstance(k, dict)]:
        a = re.sub(r"\s+", " ", str(a or "")).strip()
        if a and kisiler_modulu.ad_mi(a) and meet_gelisim._ilk(a) not in verilen and a not in adaylar:
            adaylar.append(a)
    oneri = {str(o.get("etiket")): o.get("ad") for o in (v.get("ad_onerileri") or []) if o.get("ad")}
    return jsonify({"kisiler": kisiler, "ornek": ornek, "ekran": v.get("ekran") or [], "adaylar": adaylar[:10], "oneri": oneri})


# ----------------------------------------------------------------------------- ad değişikliğini yaymak ve öğrenmek
def _ad_degisti(temel, degisim, kaynak="elle"):
    """Konuşmacı adı değişti: türetilmiş alanlar (Kısaca, notlar, danışman...) da güncellenir, belgeler + Drive yenilenir; kullanıcının kendi adı
    yeni verildiyse ve toplantı son 7 gündeyse işleri Asana'ya gider. Ardından yeni sesle eski toplantılar taranır."""
    tj = KLASOR / f"{temel}.json"
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); v = d["veri"]
        for eski, yeni in degisim.items():
            meet_gelisim.etiket_yay(v, eski, yeni)
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    _belge_yenile(temel)
    ben = meet_gelisim._ilk(ayarlar_oku().get("benim_adim"))
    if v.get("toplanti") and not v.get("misafir") and kaynak != "misafir" and ben and any(meet_gelisim._ilk(y) == ben for y in degisim.values()) and time.time() - (v.get("olusturma") or 0) < 7 * 86400:
        try:
            _gorev_ve_sesli(temel, v, log=lambda m: print(m, flush=True), sesli=False)
            with kilit:
                d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["gorev_atama"] = v.get("gorev_atama", d["veri"].get("gorev_atama"))
                tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"Görevler eklenemedi: {e}", flush=True)


@app.before_request
def _meet_uzanti_tani():
    """Uzantının okuma sağlığı sinyali (altyazı bölgesi bulundu mu, son konuşmacı ne zaman okundu) meet_gelisim.saglik için saklanır."""
    if request.method == "POST" and request.path == "/api/uzanti/durum" and not _misafir_istek():
        try:
            t = (request.get_json(silent=True) or {}).get("tani")
            if isinstance(t, dict):
                (KAYIT / ".uzanti_tani.json").write_text(json.dumps({**t, "zaman": time.time()}, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return None


@app.before_request
def _meet_duzeltme_once():
    """Kullanıcının elle düzeltmelerini öğrenmek için eski değeri saklar (toplantı adı/müşteri/şirket, konuşmacı adı)."""
    p = request.path
    if request.method != "POST" or not (p.startswith("/api/toplanti/") and p.endswith("/duzelt") or p.startswith("/api/isimlendir/") or re.match(r"^/api/sirket/[^/]+/toplanti/", p)):
        return None
    try:
        temel = p.rstrip("/").split("/")[-2] if p.endswith("/duzelt") else p.rstrip("/").split("/")[-1]
        v = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"]
        g.meet_eski = {"temel": temel, "baslik": v.get("baslik") or "", "musteri": v.get("musteri") or "", "sirket": v.get("sirket") or "",
                       "etiket": dict(v.get("etiket") or {}), "toplanti": bool(v.get("toplanti")), "misafir": bool(v.get("misafir")) or _misafir_istek()}
    except Exception:  # noqa: BLE001
        g.meet_eski = None
    return None


@app.after_request
def _meet_duzeltme_sonra(yanit):
    eski = getattr(g, "meet_eski", None)
    if not eski or yanit.status_code != 200:
        return yanit
    try:
        temel = eski["temel"]
        v = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"]
        konu = lambda b: re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", b or "").split(" · ")[0]  # noqa: E731
        if eski["misafir"]:                                  # davetli: yalnız kendi toplantısında adı yay; sahibin öğrenmesi, Asana, ses taraması yok
            degisim = {a: (v.get("etiket") or {}).get(k) for k, a in eski["etiket"].items() if (v.get("etiket") or {}).get(k) not in (None, a)}
            if degisim and v.get("misafir"):
                threading.Thread(target=_ad_degisti, args=(temel, degisim, "misafir"), daemon=True).start()
            return yanit
        if eski["toplanti"]:
            if konu(eski["baslik"]) != konu(v.get("baslik")):
                meet_gelisim.duzeltme_kaydet("baslik", temel, konu(eski["baslik"]), konu(v.get("baslik")), (v.get("ozet") or {}).get("ozet", "")[:300] if isinstance(v.get("ozet"), dict) else "")
            if eski["musteri"] != (v.get("musteri") or ""):
                meet_gelisim.duzeltme_kaydet("musteri", temel, eski["musteri"], v.get("musteri"), konu(v.get("baslik")))
                if v.get("musteri_tahmin") and v.get("musteri_tahmin") != v.get("musteri"):      # elle seçilen müşteri, kartlardaki eski tahmini geçersiz kılar
                    with kilit:
                        d = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8")); d["veri"].pop("musteri_tahmin", None)
                        (KLASOR / f"{temel}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            if eski["sirket"] != (v.get("sirket") or ""):
                meet_gelisim.duzeltme_kaydet("sirket", temel, eski["sirket"], v.get("sirket"), konu(v.get("baslik")))
        degisim = {}
        for k, a in eski["etiket"].items():
            yeni = (v.get("etiket") or {}).get(k)
            if yeni and yeni != a:
                degisim[a] = yeni
                if eski["toplanti"]:
                    meet_gelisim.duzeltme_kaydet("konusmaci", temel, a, yeni)
        if degisim:
            def _arka():
                try:
                    _ad_degisti(temel, degisim)
                    if eski["toplanti"]:
                        _meet_geriye_donuk(log=lambda m: print(m, flush=True))
                except Exception as e:  # noqa: BLE001
                    print(f"Ad değişikliği yayılamadı: {e}", flush=True)
            threading.Thread(target=_arka, daemon=True).start()
    except Exception as e:  # noqa: BLE001
        print(f"Meet düzeltme kaydı: {e}", flush=True)
    return yanit


# ----------------------------------------------------------------------------- kendiliğinden onarım
def _meet_geriye_donuk(log=print):
    """Kayıtlı seslerle eski toplantılardaki adsız kişileri adlandırır (sıkı eşik). Döner: adlandırılan kişi sayısı."""
    n = 0
    for js, es, bn in meet_gelisim.geriye_donuk_tani():
        temel = js.stem
        with kilit:
            d = json.loads(js.read_text(encoding="utf-8")); v = d["veri"]
            degisim = {}
            for k, ad in es.items():
                if meet_gelisim.ADSIZ.match(str(v["etiket"].get(k, ""))):
                    degisim[v["etiket"][k]] = ad; v["etiket"][k] = ad
            if not degisim:
                continue
            v["adlar_kaynak"] = v.get("adlar_kaynak") or "ses"
            v.setdefault("geriye_donuk", []).append({"zaman": time.time(), "degisim": degisim, "benzerlik": bn})
            js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        _ad_degisti(temel, degisim, kaynak="ses")
        n += len(degisim)
        konu = re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", v.get("baslik") or temel)
        meet_gelisim.olay("ad", f"Sesinden tanındı ({konu[:50]}): " + ", ".join(f"{e} → {y}" for e, y in degisim.items()), temel, geri=degisim)
        log(f"Geriye dönük ses tanıma: {temel} {degisim}")
    return n


def _meet_basliklari_onar(log=print):
    """Ekrandan alınmış ama toplantı adı olmayan başlıklar ('Display 3 Backstop'): özetten yeni konu, belgeler ve Drive klasörü yeni adla."""
    n = 0
    for js, v, _s in meet_gelisim.toplantilar(30):
        konu = re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", v.get("baslik") or "").split(" · ")[0]
        if v.get("baslik_kaynak") not in ("toplantı",) or not konu or _toplanti_adi_temizle(konu):
            continue
        yeni = _toplanti_baslik(v)
        if not yeni:
            continue
        eski_klasor = Path(v.get("drive") or "")
        with app.test_request_context(f"/api/toplanti/{js.stem}/duzelt", method="POST", json={"konu": yeni}):
            toplanti_duzelt(js.stem)
        if eski_klasor.name and eski_klasor.is_dir() and eski_klasor != Path(json.loads(js.read_text(encoding="utf-8"))["veri"].get("drive") or ""):
            _drive_cope(eski_klasor)
        with kilit:
            d = json.loads(js.read_text(encoding="utf-8")); d["veri"]["baslik_kaynak"] = "tahmin"
            js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        meet_gelisim.olay("baslik", f"Toplantı adı düzeltildi: '{konu}' → '{yeni}' (Drive klasörü de)", js.stem, geri={"konu": konu})
        log(f"Toplantı adı onarıldı: {konu} → {yeni}"); n += 1
    return n


def _meet_katilimci_temizle(log=print):
    """Eski kayıtlardaki katılımcı listesinden arayüz yazılarını ('Enter Full Screen', 'Zoom in') siler; kisiler.ad_mi süzgeci geliştikçe geriye uygulanır."""
    import kisiler as kisiler_modulu
    n = 0
    for js, v, _s in meet_gelisim.toplantilar(60):
        L = v.get("katilimcilar") or []
        temiz = [a for a in L if kisiler_modulu.ad_mi(re.sub(r"\s*\(.*?\)\s*$", "", str(a)))]
        if len(temiz) == len(L):
            continue
        with kilit:
            d = json.loads(js.read_text(encoding="utf-8")); d["veri"]["katilimcilar"] = temiz
            js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        _belge_yenile(js.stem)
        meet_gelisim.olay("ad", "Katılımcı listesinden arayüz yazısı silindi: " + ", ".join(a for a in L if a not in temiz)[:120], js.stem); n += 1
    return n


def _meet_eksikleri_tamamla(log=print):
    """Son 10 günde Kısaca ya da sinyalleri eksik kalan toplantılar (yeniden başlatma, Claude sınırı)."""
    n = 0
    for js, v, _s in meet_gelisim.toplantilar(10):
        if js.stem in toplanti_bitiren:
            continue
        if not v.get("kisaca"):
            with app.test_request_context(f"/api/kisaca/{js.stem}", method="POST", json={}):
                kisaca_uret_api(js.stem)
            for _ in range(60):
                time.sleep(5)
                if not kisaca_durum.get(js.stem, {}).get("calisiyor"):
                    break
            if kisaca_durum.get(js.stem, {}).get("hata"):
                continue
            meet_gelisim.olay("adim", "Eksik Kısaca tamamlandı", js.stem); n += 1
        v2 = json.loads(js.read_text(encoding="utf-8"))["veri"]
        if v2.get("kisaca") and not v2.get("sesli_ozet"):              # 24 Ekim ölçümü: 7 toplantının 6'sında yoktu
            with app.test_request_context(f"/api/sesli-ozet/{js.stem}", method="POST"):
                r = gorevler_ata(js.stem)
            if (r.get_json() or {}).get("sesli_ozet"):
                meet_gelisim.olay("adim", "Eksik sesli özet hazırlandı", js.stem); n += 1
            else:
                log(f"Sesli özet hazırlanamadı: {js.stem} {(r.get_json() or {}).get('log')}")
        if v2.get("kisaca") and not v2.get("danisman") and ayarlar_oku().get("danisman", True) and max([x.get("bit", 0) for x in _s] or [0]) >= 600 and not v2.get("misafir"):
            with app.test_request_context(f"/api/danisman/{js.stem}", method="POST"):     # 27 Ekim ölçümü: 10 toplantının 3'ünde yoktu
                danisman_uret_api(js.stem)
            for _ in range(60):
                time.sleep(5)
                if not danisman_durum.get(js.stem, {}).get("calisiyor"):
                    break
            if not danisman_durum.get(js.stem, {}).get("hata"):
                meet_gelisim.olay("adim", "Eksik danışman notu hazırlandı", js.stem); n += 1
        if v2.get("kisaca") and v2.get("drive") and not Path(v2["drive"]).is_dir() and _drive_klasor_yolu() and _meet_drive_onar(js, v2):
            meet_gelisim.olay("adim", "Kaybolan Drive klasörü yeniden yüklendi", js.stem); n += 1
        if v2.get("kisaca") and not v2.get("sinyaller") and (v2.get("sirket") or "genel") != "genel":
            if _sinyal_isle(js):
                meet_gelisim.olay("adim", "Eksik sinyaller tamamlandı", js.stem); n += 1
    return n


def _meet_drive_onar(js, v):
    """Kaydında Drive klasörü yazılı ama klasörü yerinde olmayan toplantı (2026-10-27: 15 Ekim 11.58'in klasörü hiçbir yerde yoktu): aynı adla, olması
    gereken üst klasöre yeniden yüklenir (belgeler, notlar, kayıt). Döner: yeni yol ya da None."""
    kok = _drive_klasor_yolu()
    ad = Path(v["drive"]).name
    hedef = kok / _drive_ust(v) / ad
    if hedef.exists():
        yol = hedef
    else:
        hedef.mkdir(parents=True, exist_ok=True)
        dosyalar = [(js.with_suffix(".docx"), f"{ad}.docx"), (js.with_suffix(".txt"), f"{ad}.txt"), (KLASOR / f"{js.stem}.notlar.txt", f"{ad} (notlar).txt")]
        if v.get("kayit") and Path(v["kayit"]).exists():
            dosyalar.append((Path(v["kayit"]), f"{ad} (kayıt).m4a"))
        for yerel, isim in dosyalar:
            if yerel.exists():
                h = _drive_kopya(yerel, hedef / isim)
                if h:
                    print(f"Drive onarımı: {isim}: {h}", flush=True)
        yol = hedef
    import kayit_json

    def yaz(d):
        d["veri"]["drive"] = str(yol)
    kayit_json.guncelle(js, yaz)
    return str(yol)


def _meet_musteri_onar(log=print):
    """'Diğer' kalan ve hiç taranmamış toplantılar Claude ile taranır (musteri_onerileri_tara: yalnızca toplantının asıl konusu olan, listedeki
    müşteri güven ≥0,7 ise taşınır). 24 Ekim: şirket seçiminin yan tahmini (musteri_tahmin) güvenilmez çıktı; iç toplantı bir müşteriye gitmişti."""
    T = [js for js, v, _s in meet_gelisim.toplantilar(30) if (v.get("musteri") or "Diğer") == "Diğer" and not v.get("musteri_tarandi") and not v.get("musteri_oneri")]
    if not T:
        return 0
    with app.test_request_context("/api/musteri-onerileri/tara", method="POST"):
        r = musteri_onerileri_tara()
    j = r.get_json() if hasattr(r, "get_json") else (r[0].get_json() if isinstance(r, tuple) else {})
    if (j or {}).get("tasinan"):
        meet_gelisim.olay("musteri", f"{j['tasinan']} toplantının müşterisi bulundu")
    return (j or {}).get("tasinan", 0)


def _meet_sozleri_kontrol(log=print):
    n = 0
    for temel, k, i, teslim in meet_gelisim.soz_kontrol(log=log):
        tj = KLASOR / f"{temel}.json"
        with kilit:
            d = json.loads(tj.read_text(encoding="utf-8"))
            try:
                x = d["veri"]["kisaca"]["kisiler"][k]["isler"][i]
            except Exception:  # noqa: BLE001
                continue
            x["bitti"] = True; x["teslim"] = teslim
            tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        meet_gelisim.olay("soz", f"Teslim edildiği sonraki toplantıda geçiyor: {x.get('is', '')[:80]}", temel, kanit=teslim); n += 1
    return n


def _meet_bildir_saglik(S):
    """Yeni ortaya çıkan 'hata' durumları bir kez bildirilir."""
    d = meet_gelisim.oku(); onceki = set(d.get("bildirilen_hata") or [])
    simdi = {s["kod"] for s in S if s["durum"] == "hata"}
    for s in S:
        if s["kod"] in simdi - onceki:
            _bildir("Meet: " + s["ad"], s["metin"][:120], url=_meet_url())
    d["bildirilen_hata"] = sorted(simdi); d["saglik_son"] = S; d["son"]["saglik"] = time.time()
    meet_gelisim.yaz(d)


def _meet_onar(log=print):
    """Kendiliğinden onarım turu (6 saatte bir ve elle 'Şimdi kontrol et')."""
    import claude_yaz
    meet_gelisim_durum["calisiyor"] = "onarım"
    try:
        for kisa, uzun, b in meet_gelisim.profil_birlestir(log=log):
            meet_gelisim.olay("ses", f"Ses profili birleştirildi: {kisa} → {uzun}")
        _meet_katilimci_temizle(log)
        _meet_geriye_donuk(log)
        if claude_yaz.hazir(toplanti_icerik=True) and claude_yaz.arka_plan_uygun():
            with claude_yaz.toplanti():
                _meet_basliklari_onar(log)
                _meet_eksikleri_tamamla(log)
                _meet_musteri_onar(log)
        meet_gelisim.son("onarim", time.time())
    finally:
        meet_gelisim_durum["calisiyor"] = ""


def _meet_kayit_suruyor():
    try:
        return any(time.time() - f.stat().st_mtime < 60 for f in KAYIT.glob("Toplantı *.m4a")) or bool(toplanti_bitiren)
    except Exception:  # noqa: BLE001
        return False


def _meet_gelisim_dongu():
    """10 dk'da bir: sağlık. Toplantı/kayıt sürerken ağır işler yapılmaz. 6 saatte bir onarım; günde bir e-posta davetleri ve karşı tarafın sözleri;
    haftada bir yenilik radarı ve öz değerlendirme (gece 03.00-07.00 arası tercih edilir)."""
    time.sleep(240)
    while True:
        try:
            ay = ayarlar_oku()
            S = meet_gelisim.saglik(); _meet_bildir_saglik(S)
            if ay.get("meet_gelisim", True) and not _meet_kayit_suruyor() and not meet_gelisim_durum["calisiyor"]:
                saat = time.localtime().tm_hour
                if time.time() - meet_gelisim.son("onarim") > 6 * 3600:
                    _meet_onar()
                try:
                    import davetler
                    aralik = 24 * 3600 if davetler.durum().get("etkinlik") else 7 * 86400   # davet yoksa (iş hesabı Mail'de değil) haftada bir; Mail taraması 13 dk sürüyor
                except Exception:  # noqa: BLE001
                    aralik = 7 * 86400
                if ay.get("meet_davetler", False) and 10 <= saat <= 20 and time.time() - meet_gelisim.son("davet") > aralik:
                    meet_gelisim.son("davet", time.time())
                    meet_gelisim_durum["calisiyor"] = "e-posta davetleri"
                    try:
                        import davetler
                        davetler.oku(log=lambda m: print(m, flush=True))
                    finally:
                        meet_gelisim_durum["calisiyor"] = ""
                if saat >= 9 and time.strftime("%Y-%m-%d", time.localtime(meet_gelisim.son("soz"))) != time.strftime("%Y-%m-%d"):
                    meet_gelisim.son("soz", time.time())
                    meet_gelisim_durum["calisiyor"] = "sözler"
                    try:
                        _meet_sozleri_kontrol(log=lambda m: print(m, flush=True))
                    finally:
                        meet_gelisim_durum["calisiyor"] = ""
                import claude_yaz
                # Örnek toplantı testi (duman_testi.py meet + meet_kisaca): her gece 04.00'ten sonra, site boşken; Studio'nunki 03.30'da
                if 4 <= saat <= 7 and time.strftime("%Y-%m-%d", time.localtime(meet_gelisim.son("ornek"))) != time.strftime("%Y-%m-%d") and not mesgul_nedenler():
                    meet_gelisim.son("ornek", time.time())
                    meet_gelisim_durum["calisiyor"] = "örnek toplantı testi"
                    try:
                        katman = "meet,meet_kisaca" if claude_yaz.arka_plan_uygun() else "meet"
                        r = subprocess.run([PYTHON, str(KLASOR / "duman_testi.py"), katman], capture_output=True, text=True, timeout=1800, cwd=str(KLASOR))
                        if r.returncode != 0:
                            meet_gelisim.olay("uyari", "Örnek toplantı testi geçmedi: " + " ".join(r.stdout.strip().splitlines()[-3:])[:220])
                    finally:
                        meet_gelisim_durum["calisiyor"] = ""
                haftalik = (3 <= saat <= 7) or time.time() - meet_gelisim.son("radar") > 9 * 86400
                if haftalik and time.time() - meet_gelisim.son("radar") > 7 * 86400 and claude_yaz.arka_plan_uygun():
                    meet_gelisim_durum["calisiyor"] = "yenilik radarı"
                    try:
                        meet_gelisim.radar(log=lambda m: print(m, flush=True))
                        meet_gelisim.son("radar", time.time())
                    finally:
                        meet_gelisim_durum["calisiyor"] = ""
                if haftalik and time.time() - meet_gelisim.son("ozdegerlendirme") > 7 * 86400 and claude_yaz.arka_plan_uygun():
                    meet_gelisim_durum["calisiyor"] = "haftalık değerlendirme"
                    try:
                        meet_gelisim.ozdegerlendirme(log=lambda m: print(m, flush=True))
                    finally:
                        meet_gelisim_durum["calisiyor"] = ""
        except Exception as e:  # noqa: BLE001
            meet_gelisim_durum["hata"] = str(e)[:200]
            print(f"Meet gelişim döngüsü hatası: {e}", flush=True)
        time.sleep(600)


threading.Thread(target=_meet_gelisim_dongu, daemon=True).start()


# ----------------------------------------------------------------------------- uçlar
@app.get("/api/meet/durum")
def meet_durum_get():
    d = meet_gelisim.ozet_durum()
    if time.time() - (d.get("saglik_zaman") or 0) > 300:
        S = meet_gelisim.saglik(); _meet_bildir_saglik(S); d["saglik"] = S; d["saglik_zaman"] = time.time()
    d["calisiyor"] = meet_gelisim_durum["calisiyor"]
    ay = ayarlar_oku()
    d["ayar"] = {k: bool(ay.get(k, v)) for k, v in MEET_AYARLAR.items()}
    try:
        import davetler
        d["davet"] = davetler.durum()
    except Exception:  # noqa: BLE001
        d["davet"] = {}
    return jsonify(d)


MEET_AYARLAR = {"meet_gelisim": True, "ekran_kareleri": True, "meet_davetler": False}


# Gelişiminiz kartı (2026-10-27): haftalık konuşma payı kodla, tekrar eden dersler Claude ile (girdi değişince arka planda bir kez)
MEET_GELISIMIM = {"calisiyor": False}


def _meet_gelisimim_tazele():
    try:
        meet_gelisim.gelisimim_tazele()
    except Exception as e:  # noqa: BLE001
        print(f"Gelişiminiz temaları kurulamadı: {e}", flush=True)
    finally:
        MEET_GELISIMIM["calisiyor"] = False


@app.get("/api/meet/gelisimim")
def meet_gelisimim():
    d = meet_gelisim.gelisimim()
    if not d["guncel"] and d["ders_toplanti"] >= 2 and not MEET_GELISIMIM["calisiyor"]:
        MEET_GELISIMIM["calisiyor"] = True
        threading.Thread(target=_meet_gelisimim_tazele, daemon=True).start()
    d["hazirlaniyor"] = MEET_GELISIMIM["calisiyor"]
    return jsonify(d)


@app.post("/api/meet/ayar")
def meet_ayar():
    v = request.get_json(silent=True) or {}
    if v.get("anahtar") not in MEET_AYARLAR:
        return jsonify({"hata": "Bilinmeyen ayar."}), 400
    ay = ayarlar_oku(); ay[v["anahtar"]] = bool(v.get("deger")); ayarlar_yaz(ay)
    return jsonify({"tamam": True})


@app.post("/api/meet/kontrol")
def meet_kontrol():
    """'Şimdi kontrol et': sağlık + onarım turu arka planda."""
    if meet_gelisim_durum["calisiyor"]:
        return jsonify({"tamam": True, "calisiyor": meet_gelisim_durum["calisiyor"]})

    def _calis():
        try:
            _meet_bildir_saglik(meet_gelisim.saglik()); _meet_onar(log=lambda m: print(m, flush=True))
        except Exception as e:  # noqa: BLE001
            meet_gelisim_durum["hata"] = str(e)[:200]
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True, "calisiyor": "onarım"})


@app.post("/api/meet/radar")
def meet_radar_simdi():
    if meet_gelisim_durum["calisiyor"]:
        return jsonify({"tamam": True, "calisiyor": meet_gelisim_durum["calisiyor"]})

    def _calis():
        meet_gelisim_durum["calisiyor"] = "yenilik radarı"
        try:
            meet_gelisim.radar(log=lambda m: print(m, flush=True)); meet_gelisim.son("radar", time.time())
            meet_gelisim_durum["calisiyor"] = "haftalık değerlendirme"
            meet_gelisim.ozdegerlendirme(log=lambda m: print(m, flush=True))
        except Exception as e:  # noqa: BLE001
            meet_gelisim_durum["hata"] = str(e)[:200]
        finally:
            meet_gelisim_durum["calisiyor"] = ""
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.post("/api/meet/oneri/<oid>")
def meet_oneri(oid):
    v = request.get_json(silent=True) or {}
    return jsonify({"tamam": meet_gelisim.oneri_karar(re.sub(r"[^a-f0-9]", "", oid)[:8], "kabul" if v.get("kabul") else "red")})


@app.post("/api/meet/geri-al")
def meet_geri_al():
    """Kendiliğinden verilen bir adı geri alır: {temel, degisim: {eski: yeni}} → yeni adlar yeniden 'Konuşmacı N' olur."""
    v = request.get_json(silent=True) or {}
    temel = str(v.get("temel") or ""); tj = _temel_dogrula(temel).with_suffix(".json")
    ters = {y: e for e, y in (v.get("degisim") or {}).items() if meet_gelisim.ADSIZ.match(str(e))}
    if not ters:
        return jsonify({"hata": "Geri alınacak ad yok."}), 400
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); et = d["veri"]["etiket"]
        for k, a in list(et.items()):
            if a in ters:
                et[k] = ters[a]
        d["veri"].setdefault("ad_red", []).extend(ters.values())
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    _ad_degisti(temel, ters)
    meet_gelisim.duzeltme_kaydet("konusmaci", temel, ", ".join(ters), ", ".join(ters.values()), "kendiliğinden verilen ad geri alındı")
    meet_gelisim.olay("geri", "Kendiliğinden verilen ad geri alındı: " + ", ".join(ters), temel)
    return jsonify({"tamam": True})


@app.post("/api/meet/hatirlat")
def meet_hatirlat():
    """Karşı tarafın gecikmiş sözü için takip mesajı taslağı: {temel, k, i} → {metin, eposta, kim}. Gönderilmez."""
    import sozler
    v = request.get_json(silent=True) or {}
    o = next((x for x in sozler.liste(120)["bekledigin"] if x["temel"] == v.get("temel") and x["k"] == int(v.get("k", -9)) and x["i"] == int(v.get("i", -9))), None)
    if not o:
        return jsonify({"hata": "İş bulunamadı."}), 404
    veri = json.loads((KLASOR / f"{o['temel']}.json").read_text(encoding="utf-8"))["veri"]
    return jsonify({"metin": meet_gelisim.hatirlatma_yaz(o, veri), "eposta": meet_gelisim.eposta_bul(o["kim"], veri), "kim": o["kim"], "konu": o["konu"]})


@app.post("/api/meet/hatirlat/taslak")
def meet_hatirlat_taslak():
    """Mail'de GÖNDERİLMEMİŞ taslak açar; kullanıcı okuyup kendisi gönderir."""
    import notlar as notlar_modulu
    v = request.get_json(silent=True) or {}
    metin = str(v.get("metin") or "").strip()[:4000]
    if not metin:
        return jsonify({"hata": "Mesaj boş."}), 400
    alici = [a for a in [str(v.get("eposta") or "").strip()] if re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", a, re.I)]
    hata = notlar_modulu.taslak_ac(str(v.get("konu") or "Takip")[:120], metin, alici)
    return jsonify({"tamam": not hata, "hata": hata or ""})

# sunucu/03_video_isleri.py — indirme işçisi ve video işleri (altyazılı, klip, kesim, dublaj, dudak, sessizlik).
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- indirme işçisi
def _dizin_oku():
    """İndirilenler dizini. Dosya var ama bozuksa (yarım yazım) .bak'a düşer; o da yoksa HATA verir: eskiden {} dönüp bir sonraki yazımda bütün
    dizin tek kayda iniyordu (2026-10-25 gözden geçirme)."""
    try:
        return json.loads(INDIR_DIZIN.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        bak = INDIR_DIZIN.with_name(INDIR_DIZIN.name + ".bak")
        try:
            d = json.loads(bak.read_text(encoding="utf-8"))
            print(f"İndirilenler dizini bozuk ({e}); yedekten okundu", flush=True)
            return d
        except Exception:  # noqa: BLE001
            raise RuntimeError(f"indirilenler/.dizin.json bozuk: {e}")


def _dizin_yaz(d):
    INDIRILENLER.mkdir(exist_ok=True)
    _json_yaz_atomik(INDIR_DIZIN, d, yedek=True)


def _ffprobe(yol):
    """Genişlik, yükseklik ve süre (sessizce boş döner)."""
    try:
        p = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(yol)],
                           capture_output=True, text=True, timeout=20)
        j = json.loads(p.stdout or "{}")
        st = (j.get("streams") or [{}])[0]
        return {"genislik": st.get("width"), "yukseklik": st.get("height"),
                "sure": float((j.get("format") or {}).get("duration") or 0)}
    except Exception:  # noqa: BLE001
        return {}


def _isci_indir():
    while True:
        is_id = sira_indir.get()
        is_ = isler.get(is_id)
        if not is_ or is_["durum"] != "sirada":
            sira_indir.task_done()
            continue
        is_["durum"] = "calisiyor"
        is_["baslangic"] = time.time()
        if is_.get("tur") == "dublaj":
            try:
                _dublaj_isi(is_)
            except Exception as e:  # noqa: BLE001
                is_["durum"] = "hata"; is_["hata"] = str(e)
            is_["bitis"] = time.time(); _kaydet(); sira_indir.task_done(); continue
        if is_.get("tur") == "dudak":
            try:
                _dudak_isi(is_)
            except Exception as e:  # noqa: BLE001
                is_["durum"] = "hata"; is_["hata"] = str(e)
            is_["bitis"] = time.time(); _kaydet(); sira_indir.task_done(); continue
        if is_.get("tur") == "sessizlik":
            try:
                _sessizlik_isi(is_)
            except Exception as e:  # noqa: BLE001
                is_["durum"] = "hata"; is_["hata"] = str(e)
            is_["bitis"] = time.time(); _kaydet(); sira_indir.task_done(); continue
        if is_.get("tur") in ("altyazili", "klip", "kesim"):
            try:
                _video_isi_calistir(is_)
            except Exception as e:  # noqa: BLE001
                is_["durum"] = "hata"; is_["hata"] = str(e)
            is_["bitis"] = time.time()
            _kaydet()
            sira_indir.task_done()
            continue
        komut = [PYTHON, "-u", str(INDIR_SCRIPT), is_["link"], "--kalite", is_["kalite"], "--klasor", str(INDIRILENLER)]
        if is_.get("kesit"):
            komut += ["--kesit", is_["kesit"]]
        if is_.get("kapak_kaydet"):
            komut += ["--kapak"]
        if is_.get("cerez"):
            komut += ["--cerez", is_["cerez"]]
        if Path("/usr/bin/caffeinate").exists():
            komut = ["/usr/bin/caffeinate", "-i"] + komut
        _kaydet()
        try:
            p = subprocess.Popen(komut, cwd=str(KLASOR), env=_env(), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
            is_["p"] = p
            son_kayit = 0
            for satir in p.stdout:
                satir = satir.rstrip("\n")
                if "\r" in satir:
                    satir = satir.split("\r")[-1]
                _satir_isle_indir(is_, satir)
                if time.time() - son_kayit > 3:
                    _kaydet(); son_kayit = time.time()
            p.wait()
            is_.pop("p", None)
            if is_["durum"] == "iptal":
                pass
            elif is_.get("dosya") and Path(is_["dosya"]).exists():
                _indirme_bitir(is_)
                is_["durum"] = "bitti"
                _bildir("Video indi", is_.get("baslik") or is_["link"])
            else:
                is_["durum"] = "hata"
                is_["hata"] = _hata_metni("\n".join(is_["log"][-40:]))
                _bildir("İndirme olmadı", is_["hata"])
        except Exception as e:  # noqa: BLE001
            is_["durum"] = "hata"
            is_["hata"] = str(e)
        is_["bitis"] = time.time()
        _kaydet()
        sira_indir.task_done()


def _alt_surec(is_, komut, satir_isle):
    """Alt süreci çalıştırır, satırları işler; iptal edilirse None, yoksa dönüş kodu."""
    if Path("/usr/bin/caffeinate").exists():
        komut = ["/usr/bin/caffeinate", "-i"] + komut
    p = subprocess.Popen(komut, cwd=str(KLASOR), env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1, start_new_session=True)
    is_["p"] = p
    son = 0
    for satir in p.stdout:
        satir = satir.rstrip("\n")
        if "\r" in satir:
            satir = satir.split("\r")[-1]
        satir_isle(is_, satir)
        if time.time() - son > 3:
            _kaydet(); son = time.time()
    p.wait()
    is_.pop("p", None)
    return None if is_["durum"] == "iptal" else p.returncode


def _kaynak_video(temel, en_az=0):
    """Transkriptin kaynak videosu: yerel dosyaysa kendisi; indirilmişse en iyi kopya (yüksekliği en_az'dan düşükse yok sayılır); yoksa None."""
    try:
        v = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"]
    except Exception:  # noqa: BLE001
        return None, None
    link = v.get("link") or ""
    if link and not re.match(r"^https?://", link) and Path(link).is_file() and Path(link).suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
        return Path(link), v
    en_iyi, en_h = None, -1
    for ad, d in _dizin_oku().items():
        if d.get("link") == link and (INDIRILENLER / ad).is_file() and ad.lower().endswith((".mp4", ".mkv", ".webm", ".mov")) \
                and not d.get("kesit") and d.get("kalite") not in ("mp3", "altyazili", "klip", "kesim"):
            h = int((d.get("cozunurluk") or "0×0").split("×")[-1] or 0)
            if h > en_h:
                en_iyi, en_h = INDIRILENLER / ad, h
    if en_az and en_h < en_az:
        return None, v
    return en_iyi, v


def _video_isi_baslat(v):
    """Altyazılı video ya da klip işini kuyruğa alır (v: islem, temel, dil, stil, kesit, kalite)."""
    temel = v.get("temel") or ""
    if not re.match(r"^[\w\-]+$", temel) or not (KLASOR / f"{temel}.json").exists():
        return None
    veri = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8"))["veri"]
    is_id = uuid.uuid4().hex[:8]
    isler[is_id] = {
        "id": is_id, "tur": v["islem"], "temel": temel, "link": veri.get("link", ""), "baslik": veri.get("baslik") or temel,
        "kanal": veri.get("kanal", ""), "sure": veri.get("sure", 0), "kapak": _kapak_yolu(temel, veri.get("kapak")),
        "dil": v.get("dil") or "orijinal", "stil": v.get("stil") if v.get("stil") in ("kutu", "sade", "karaoke", "pop", "vurgu") else "kutu",
        "font": re.sub(r"[^a-z]", "", v.get("font") or "")[:12], "renk": re.sub(r"[^0-9a-fA-F]", "", v.get("renk") or "")[:6],
        "dikey": bool(v.get("dikey")), "temiz_ses": bool(v.get("temiz_ses")), "broll": bool(v.get("broll")), "takip": (False if v.get("takip") is False else True),
        "tut": (v.get("tut") or "") if re.match(r"^[\d.,\-]*$", v.get("tut") or "") else "", "sirali": bool(v.get("sirali")),
        "altyazisiz": bool(v.get("altyazisiz")), "baslik_ek": (v.get("baslik_ek") or "")[:60],
        "format": v.get("format") if v.get("format") in ("9:16", "4:5", "1:1") else "", "zoom": bool(v.get("zoom")), "isim_bandi": bool(v.get("isim_bandi")),
        "studyo": bool(v.get("studyo")), "tekrar": bool(v.get("tekrar")), "emoji": bool(v.get("emoji")), "konusana": bool(v.get("konusana")), "arka": v.get("arka") if v.get("arka") in ("bulanik", "koyu") else "",
        "muzik": Path(v.get("muzik") or "").name[:120],
        "kanca": (v.get("kanca") or "")[:120], "kanca_stil": re.sub(r"[^a-z_]", "", v.get("kanca_stil") or "sade")[:30], "en_az": int(v.get("en_az") or 0),
        "kesit": v.get("kesit") or "", "kalite": str(v.get("kalite") or "720"), "cerez": v.get("cerez") or "",
        "durum": "sirada", "log": [], "ilerleme": 0, "adim": 0, "olusturma": time.time(),
    }
    if v.get("kesit"):
        try:
            import indir as indir_modulu
            b, e = indir_modulu.kesit_coz(v["kesit"])
            isler[is_id]["kesit_sn"] = (e - b) if e is not None else max(0, (veri.get("sure") or 0) - b)
            isler[is_id]["sure"] = isler[is_id]["kesit_sn"] or isler[is_id]["sure"]
        except SystemExit:
            pass
    if isler[is_id].get("tut"):
        try:
            kalan = sum(max(0.0, float(b) - float(a)) for a, b in (x.split("-", 1) for x in isler[is_id]["tut"].split(",") if "-" in x))
            isler[is_id]["kesit_sn"] = kalan; isler[is_id]["sure"] = kalan or isler[is_id]["sure"]
        except ValueError:
            pass
    sira_indir.put(is_id)
    _kaydet()
    return is_id


def _dublaj_isi(is_):
    """dublaj.py ile çevrilmiş metni konuşmacının sesiyle seslendirip videoya basar."""
    temel = is_["temel"]; is_["adim"] = 1; is_["durum"] = "calisiyor"; is_["baslangic"] = time.time(); _kaydet()
    kaynak, veri = _kaynak_video(temel)
    if kaynak is None:
        link = (veri or {}).get("link") or ""
        if not re.match(r"^https?://", link):
            is_["durum"] = "hata"; is_["hata"] = "Bu transkriptin kaynak videosu bulunamadı."; return
        is_["log"].append("Kaynak video indiriliyor (720p)")
        kod = _alt_surec(is_, [PYTHON, "-u", str(INDIR_SCRIPT), link, "--kalite", "720", "--klasor", str(INDIRILENLER)] + (["--cerez", is_["cerez"]] if is_.get("cerez") else []), _satir_isle_indir)
        if kod is None:
            return
        if kod != 0 or not is_.get("dosya"):
            is_["durum"] = "hata"; is_["hata"] = _hata_metni("\n".join(is_["log"][-40:])); return
        kaynak = Path(is_["dosya"]); is_.pop("dosya", None)
    is_["adim"] = 2; is_["adim_metni"] = "Seslendiriliyor"; _kaydet()
    ad = re.sub(r"\s*\[[^\]]*\]\s*$", "", Path(kaynak).stem)
    ek_ad = " önizleme" if is_.get("onizleme") else ""
    cikti = INDIRILENLER / f"{ad} [dublaj {is_['dil'].upper()}{ek_ad}].mp4"
    n = 2
    while cikti.exists():
        cikti = INDIRILENLER / f"{ad} [dublaj {is_['dil'].upper()}{ek_ad}]_{n}.mp4"; n += 1
    komut = [PYTHON, "-u", str(KLASOR / "dublaj.py"), str(KLASOR / f"{temel}.json"), "--dil", is_["dil"], "--video", str(kaynak), "--cikti", str(cikti)]
    if is_.get("ozgun_sil"):
        komut.append("--ozgun-sil")
    if is_.get("onizleme"):                                # 23 Ekim: önce ilk 30 sn (okunuş, çeviri, senkron); tamamı için süre tahmini
        komut += ["--onizleme", "30"]
    def satir(is__, s):
        m = re.search(r"ses (\d+)/(\d+)", s)
        if m:
            is__["ilerleme"] = int(100 * int(m.group(1)) / max(1, int(m.group(2)))); is__["adim"] = 3
        t = re.search(r"Tahmin: tamamı ~(\d+) dk", s)
        if t:
            is__["tahmin_dk"] = int(t.group(1))
    kod = _alt_surec(is_, komut, satir)
    if kod is None:
        return
    if kod != 0 or not cikti.exists():
        is_["durum"] = "hata"; is_["hata"] = _hata_metni("\n".join(is_["log"][-30:])) or "Seslendirme başarısız"; return
    is_["adim"] = 4; is_["dosya"] = str(cikti); is_["durum"] = "bitti"
    _indirme_bitir({"dosya": str(cikti), "link": (veri or {}).get("link") or "", "baslik": is_["baslik"], "kanal": is_.get("kanal", ""), "kalite": "dublaj",
                    "sure": 0, "kapak": is_.get("kapak"), "platform": (veri or {}).get("platform", ""), "log": [], "temel": temel, "dil": is_["dil"]})
    _bildir("Dublaj hazır", f"{ad} · {is_['dil'].upper()}")


def _dudak_isi(is_):
    """dudak.py (sync.so, ücretli bulut): dublajlı videonun dudaklarını yeni sese eşler. Kullanıcı her seferinde onaylar; yarıda kesilirse
    kendiliğinden yeniden gönderilmez (yeniden ücretlenmesin diye)."""
    kaynak = INDIRILENLER / is_["dosya_ad"]
    is_["adim"] = 1; is_["durum"] = "calisiyor"; _kaydet()
    if not kaynak.is_file():
        is_["durum"] = "hata"; is_["hata"] = "Video bulunamadı."; return
    ad = re.sub(r"\s*\[[^\]]*\]\s*$", "", kaynak.stem)
    etiket = re.search(r"\[(dublaj [A-Z]{2})[^\]]*\]", kaynak.stem)
    cikti = INDIRILENLER / f"{ad} [{etiket.group(1) + ', ' if etiket else ''}dudak senkronlu].mp4"
    n = 2
    while cikti.exists():
        cikti = INDIRILENLER / f"{ad} [{etiket.group(1) + ', ' if etiket else ''}dudak senkronlu]_{n}.mp4"; n += 1

    def satir(is__, s):
        m = re.match(r"\[(\d)/4\]", s)
        if m:
            is__["adim"] = int(m.group(1))
        p = re.search(r"ilerleme (\d+)%", s)
        if p:
            is__["ilerleme"] = int(p.group(1))
    kod = _alt_surec(is_, [PYTHON, "-u", str(KLASOR / "dudak.py"), str(kaynak), "--cikti", str(cikti)], satir)
    if kod is None:
        return
    if kod != 0 or not cikti.exists():
        is_["durum"] = "hata"; is_["hata"] = _hata_metni("\n".join(is_["log"][-30:])) or "Dudak senkronu başarısız"; return
    is_["adim"] = 4; is_["dosya"] = str(cikti); is_["durum"] = "bitti"
    d0 = _dizin_oku().get(kaynak.name, {})
    _indirme_bitir({"dosya": str(cikti), "link": d0.get("link", ""), "baslik": is_["baslik"], "kanal": d0.get("kanal", ""), "kalite": "dudak",
                    "sure": d0.get("sure", 0), "kapak": d0.get("kapak"), "platform": d0.get("platform", ""), "log": [], "temel": d0.get("temel", ""),
                    "dil": d0.get("dil", "")})
    _bildir("Dudak senkronu hazır", ad)


def _sessizlik_isi(is_):
    """auto-editor ile sessizlikleri keser: mp4 ya da kurgu programı zaman çizelgesi (Final Cut / Premiere / DaVinci)."""
    temel = is_["temel"]; is_["adim"] = 1; is_["durum"] = "calisiyor"; is_["baslangic"] = time.time(); _kaydet()
    kaynak, veri = _kaynak_video(temel)
    if kaynak is None:
        is_["durum"] = "hata"; is_["hata"] = "Bu transkriptin kaynak videosu bulunamadı; önce videoyu indirin."; return
    is_["adim"] = 2; is_["adim_metni"] = "Sessizlikler bulunuyor"; _kaydet()
    bicim = is_["bicim"]
    ad = re.sub(r"\s*\[[^\]]*\]\s*$", "", Path(kaynak).stem)
    uzanti = {"mp4": "mp4", "fcpxml": "fcpxml", "premiere": "xml", "resolve": "xml"}[bicim]
    etiket = {"mp4": "sessizlikler kesilmiş", "fcpxml": "Final Cut", "premiere": "Premiere", "resolve": "DaVinci"}[bicim]
    cikti = INDIRILENLER / f"{ad} [{etiket}].{uzanti}"
    n = 2
    while cikti.exists():
        cikti = INDIRILENLER / f"{ad} [{etiket}]_{n}.{uzanti}"; n += 1
    komut = [str(KLASOR / ".venv" / "bin" / "auto-editor"), str(kaynak), "--edit", f"audio:threshold={is_['esik']}", "--margin", f"{is_['pay']}sec", "--no-open", "-o", str(cikti)]
    if bicim != "mp4":
        komut += ["--export", {"fcpxml": "final-cut-pro", "premiere": "premiere", "resolve": "resolve"}[bicim]]
    else:                         # Mac'in donanım kodlayıcısı (2026-10-24 ölçüm: 41 sn dikey 1080p, işlemci süresi 31 → 7 sn); olmazsa eski yol
        h = int((_ffprobe(kaynak).get("yukseklik") or 720))
        komut += ["-c:v", "h264_videotoolbox", "-b:v", "8M" if h >= 1080 else ("5M" if h >= 720 else "2500k")]
    kod = _alt_surec(is_, komut, lambda is__, satir: None)
    if kod not in (None, 0) and bicim == "mp4" and "h264_videotoolbox" in komut:
        is_["log"].append("Donanım kodlayıcı olmadı; işlemciyle yeniden deneniyor")
        komut = komut[:komut.index("-c:v")]
        cikti.unlink(missing_ok=True)
        kod = _alt_surec(is_, komut, lambda is__, satir: None)
    if kod is None:
        return
    if kod != 0 or not cikti.exists():
        is_["durum"] = "hata"; is_["hata"] = _hata_metni("\n".join(is_["log"][-30:])) or "Sessizlik kesme başarısız"; return
    is_["adim"] = 4; is_["dosya"] = str(cikti); is_["durum"] = "bitti"
    if bicim == "mp4":
        _indirme_bitir({"dosya": str(cikti), "link": (veri or {}).get("link") or "", "baslik": is_["baslik"], "kanal": is_.get("kanal", ""), "kalite": "kesim",
                        "sure": 0, "kapak": is_.get("kapak"), "platform": (veri or {}).get("platform", ""), "log": [], "temel": temel})
    _bildir("Hazır", f"{etiket}: {ad}")


def _video_isi_calistir(is_):
    """[1] kaynak video (gerekirse indir) → [2-3] yakma.py → [4] kaydet."""
    temel = is_["temel"]
    is_["adim"] = 1
    kaynak, veri = _kaynak_video(temel, en_az=int(is_.get("en_az") or 0))
    if kaynak is None:
        link = (veri or {}).get("link") or ""
        if not re.match(r"^https?://", link):
            is_["durum"] = "hata"; is_["hata"] = "Bu transkriptin kaynak videosu bulunamadı."; return
        is_["log"].append(f"Kaynak video indiriliyor ({is_['kalite']}p)")
        komut = [PYTHON, "-u", str(INDIR_SCRIPT), link, "--kalite", is_["kalite"], "--klasor", str(INDIRILENLER)]
        if is_.get("cerez"):
            komut += ["--cerez", is_["cerez"]]
        kod = _alt_surec(is_, komut, _satir_isle_indir)
        if kod is None:
            return
        if kod != 0 or not is_.get("dosya"):
            is_["durum"] = "hata"; is_["hata"] = _hata_metni("\n".join(is_["log"][-40:])); return
        ara_is = {"dosya": is_["dosya"], "link": link, "baslik": is_["baslik"], "kanal": is_.get("kanal", ""), "kalite": is_["kalite"],
                  "sure": veri.get("sure", 0), "kapak": is_.get("kapak"), "platform": veri.get("platform", ""), "log": []}
        _indirme_bitir(ara_is)
        kaynak = Path(is_["dosya"]); is_.pop("dosya", None); is_["ilerleme"] = 0
    is_["adim"] = 2
    komut = [PYTHON, "-u", str(YAKMA_SCRIPT), str(KLASOR / f"{temel}.json"), "--video", str(kaynak), "--stil", is_["stil"]]
    if is_.get("font"):
        komut += ["--font", is_["font"]]
    if is_.get("renk") and len(is_["renk"]) == 6:
        komut += ["--renk", is_["renk"]]
    if is_.get("dil") and is_["dil"] != "orijinal":
        komut += ["--dil", is_["dil"]]
    if is_.get("kesit"):
        komut += ["--kesit", is_["kesit"]]
    if is_.get("dikey"):
        komut += ["--dikey-orta" if is_.get("takip") is False else "--dikey"]
    if is_.get("temiz_ses"):
        komut += ["--temiz-ses"]
    if is_.get("broll"):
        komut += ["--broll"]
    if is_.get("tut"):
        komut += ["--tut-sirali" if is_.get("sirali") else "--tut", is_["tut"]]   # sirali: kurguda paragrafların yeri değişti (Studio, 2026-10-24)
        try:
            is_["kesit_sn"] = sum(max(0.0, float(b) - float(a)) for a, b in (x.split("-", 1) for x in is_["tut"].split(",") if "-" in x))
        except ValueError:
            pass
    if is_.get("altyazisiz"):
        komut += ["--altyazisiz"]
    if is_.get("format") and not is_.get("dikey"):
        komut += ["--format", is_["format"]]
    for anahtar, bayrak in (("zoom", "--zoom"), ("isim_bandi", "--isim-bandi"), ("studyo", "--studyo-sesi"), ("tekrar", "--tekrar-temizle"), ("emoji", "--emoji"), ("konusana", "--konusana")):
        if is_.get(anahtar):
            komut.append(bayrak)
    if is_.get("arka"):
        komut += ["--arka-plan", is_["arka"]]
    if is_.get("muzik") and (KLASOR / "muzik" / is_["muzik"]).exists():
        komut += ["--muzik", str(KLASOR / "muzik" / is_["muzik"])]
    if is_.get("baslik_ek"):
        komut += ["--ek", is_["baslik_ek"]]
    if is_.get("kanca"):
        komut += ["--baslik", is_["kanca"], "--baslik-stil", is_.get("kanca_stil") or "sade"]
    kod = _alt_surec(is_, komut, _satir_isle_yakma)
    if kod is None:
        return
    if kod != 0 or not is_.get("dosya") or not Path(is_["dosya"]).exists():
        is_["durum"] = "hata"; is_["hata"] = _hata_metni("\n".join(is_["log"][-40:])); return
    is_["kalite"] = is_["tur"]
    _indirme_bitir(is_)
    is_["durum"] = "bitti"
    _bildir("Video hazır", is_.get("baslik") or temel)
    if is_.get("baslik_ek") == "Shorts 1" and is_.get("kanca_stil") != "sade":   # marka paketi: aynı yüksek çözünürlüklü kaynaktan kapak taslakları
        threading.Thread(target=_kapak_taslak, args=(temel, kaynak), daemon=True).start()


def _satir_isle_yakma(is_, satir):
    if not satir.strip():
        return
    is_["log"].append(satir)
    if len(is_["log"]) > 400:
        del is_["log"][:100]
    m = re.match(r"^\[(\d)/4\]", satir)
    if m:
        is_["adim"] = int(m.group(1)); is_["ilerleme"] = 0
    m = re.search(r"Altyazı: (\d+)/(\d+)", satir)
    if m:
        is_["ilerleme"] = min(99, int(100 * int(m.group(1)) / max(1, int(m.group(2)))))
    m = re.search(r"\btime=(\d+):(\d\d):(\d\d(?:\.\d+)?)", satir)
    if m and is_.get("adim") == 3:
        sn = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        top = is_.get("kesit_sn") or is_.get("sure") or 0
        if top:
            is_["ilerleme"] = min(99, int(100 * sn / top))
    if satir.startswith("Bitti. Dosya: "):
        is_["dosya"] = satir[len("Bitti. Dosya: "):].strip()


ceviri_durum = {}


def _ceviri_calistir(temel, dil):
    """ceviri.py'yi çalıştırır; durum ceviri_durum[temel]'de izlenir. Döner: başarılı mı."""
    anahtar = temel
    if ceviri_durum.get(anahtar, {}).get("calisiyor"):
        return False
    ceviri_durum[anahtar] = {"dil": dil, "calisiyor": True, "metin": "Başlıyor", "ilerleme": 0, "hata": ""}
    d = ceviri_durum[anahtar]
    try:
        p = subprocess.Popen([PYTHON, "-u", str(CEVIRI_SCRIPT), str(KLASOR / f"{temel}.json"), dil], cwd=str(KLASOR), env=_env(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        son = ""
        for satir in p.stdout:
            satir = satir.strip()
            if not satir:
                continue
            son = satir
            m = re.search(r"Çeviri: (\d+)/(\d+)", satir)
            if m:
                d["ilerleme"] = int(95 * int(m.group(1)) / max(1, int(m.group(2)))); d["metin"] = f"Çevriliyor · {m.group(1)}/{m.group(2)}"
            elif satir.startswith("[2/3]"):
                d["metin"] = "Özet çevriliyor"; d["ilerleme"] = 96
            elif satir.startswith("[3/3]"):
                d["metin"] = "Dosyalar yazılıyor"; d["ilerleme"] = 98
        p.wait()
        if p.returncode != 0:
            d["hata"] = son.replace("HATA:", "").strip() or "Çeviri yapılamadı."
    except Exception as e:  # noqa: BLE001
        d["hata"] = str(e)
    d["calisiyor"] = False; d["ilerleme"] = 100; d["metin"] = "Hazır" if not d["hata"] else d["hata"]
    if not d["hata"]:
        _bildir("Çeviri hazır", f"{temel} · {dil.upper()}")
    return not d["hata"]


def _indirme_bitir(is_):
    yol = Path(is_["dosya"])
    is_["ad"] = yol.name
    is_["boyut"] = yol.stat().st_size
    is_["ilerleme"] = 100
    is_["adim"] = 4
    pr = _ffprobe(yol) if yol.suffix != ".mp3" else {}
    if pr.get("yukseklik"):
        is_["cozunurluk"] = f"{pr['genislik']}×{pr['yukseklik']}"
    if pr.get("sure") and not is_.get("sure"):
        is_["sure"] = pr["sure"]
    kapak = INDIRILENLER / ".kapaklar" / f"{yol.stem}.jpg"
    if not kapak.exists() and is_.get("kapak") and str(is_["kapak"]).startswith("/kapak/"):
        try:
            shutil.copy(str(KLASOR / is_["kapak"].split("/")[-1]), str(kapak))
        except Exception:  # noqa: BLE001
            pass
    elif not kapak.exists() and is_.get("kapak"):
        kapak.parent.mkdir(exist_ok=True)
        _kapak_indir_hedef(kapak, is_["kapak"])
    if not kapak.exists() and yol.suffix.lower() != ".mp3":          # kapak yoksa videodan bir kare al
        try:
            kapak.parent.mkdir(exist_ok=True)
            subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(yol), "-frames:v", "1",
                            "-vf", "scale=640:-2", str(kapak)], capture_output=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
    is_["kapak"] = f"/indirilen-kapak/{yol.stem}.jpg" if kapak.exists() else ""
    with kilit:
        d = _dizin_oku()
        d[yol.name] = {"baslik": is_.get("baslik") or yol.stem, "kanal": is_.get("kanal", ""), "link": is_["link"],
                       "kalite": is_["kalite"], "kesit": is_.get("kesit") or "", "sure": is_.get("sure", 0), "dil": is_.get("dil", ""),
                       "temel": is_.get("temel", ""), "kaynak_imza": _metin_imzasi(is_["temel"]) if is_.get("temel") else "",
                       "cozunurluk": is_.get("cozunurluk", ""), "platform": is_.get("platform", ""),
                       "olusturma": time.time()}
        _dizin_yaz(d)


def _metin_imzasi(temel):
    """Transkript metninin parmak izi: kayıttan üretilen çıktı (altyazılı video, klip, dublaj) sonradan değişen metinle mi kaldı, anlamak için."""
    try:
        seg = json.loads((KLASOR / f"{temel}.json").read_text(encoding="utf-8")).get("segmentler") or []
        return hashlib.sha1("\n".join(x.get("metin", "") for x in seg).encode("utf-8")).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return ""


def _kaynak_durumu(temel, imza=""):
    """Türemiş çıktının kaynağı: var | degisti (metin sonradan değişti) | silindi (çöpte, geri alınabilir) | yok | '' (kaynağı olmayan indirme)."""
    if not temel:
        return ""
    if (KLASOR / f"{temel}.json").exists():
        return "degisti" if imza and _metin_imzasi(temel) != imza else "var"
    return "silindi" if (COP / f"{temel}.json").exists() else "yok"


def _turemisler(temel):
    d = _dizin_oku()
    return [{"ad": ad, "kalite": x.get("kalite", ""), "kesit": x.get("kesit", ""), "dil": x.get("dil", ""), "olusturma": x.get("olusturma", 0),
             "kaynak_durum": _kaynak_durumu(temel, x.get("kaynak_imza", ""))}
            for ad, x in d.items() if x.get("temel") == temel and x.get("kalite") != "yukleme" and (INDIRILENLER / ad).exists()]   # yüklenen asıl video türemiş değil


def _kapak_indir_hedef(hedef, url):
    """Yalnız http(s) ve en çok 8 MB (2026-10-25 güvenlik: urlopen file:// kabul ediyordu; istekten gelen 'kapak' ile Mac'teki herhangi bir dosya
    kapak diye kopyalanıp /indirilen-kapak/ ile okunabilirdi)."""
    if not re.match(r"^https?://", str(url or "")):
        return
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r, open(hedef, "wb") as f:
            if not (r.headers.get("Content-Type") or "image").startswith("image"):
                raise ValueError("resim değil")
            f.write(r.read(8 * 1024 * 1024))
    except Exception:  # noqa: BLE001
        if hedef.exists():
            hedef.unlink()


def _satir_isle_indir(is_, satir):
    if not satir.strip():
        return
    is_["log"].append(satir)
    if len(is_["log"]) > 400:
        del is_["log"][:100]
    m = re.match(r"^\s*Yöntem: (.*)", satir)
    if m:
        is_["yontem"] = m.group(1).strip()
        is_["adim"] = max(is_.get("adim", 0), 1)
    if satir.startswith("[download] Destination:") or "[download] Downloading" in satir and "format" in satir:
        is_["adim"] = 2
        is_["parca"] = is_.get("parca", 0) + (1 if satir.startswith("[download] Destination:") else 0)
        is_["ilerleme"] = 0
    m = re.search(r"\[download\]\s+([0-9.]+)%\s+of\s+~?\s*([0-9.]+\s*[KMG]i?B)(?:.*?at\s+([0-9.]+\s*[KMG]i?B/s))?(?:.*?ETA\s+([\d:]+))?", satir)
    if m:
        is_["adim"] = 2
        is_["ilerleme"] = min(99, int(float(m.group(1))))
        is_["boyut_metni"] = m.group(2).replace("iB", "B").replace(" ", "")
        if m.group(3):
            is_["hiz"] = m.group(3).replace("iB", "B").replace(" ", "")
        if m.group(4) and m.group(4) not in ("00:00", "Unknown"):
            is_["eta"] = m.group(4)
    m = re.search(r"\btime=(\d+):(\d\d):(\d\d(?:\.\d+)?)", satir)      # ffmpeg (kesit indirmede)
    if m and is_.get("kesit_sn"):
        sn = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        is_["adim"] = 2
        is_["ilerleme"] = min(99, int(100 * sn / is_["kesit_sn"]))
    if re.match(r"^\[(Merger|ExtractAudio|VideoRemuxer|FixupM3u8|FixupM4a|ffmpeg)\]", satir):
        is_["adim"] = 3
        is_["ilerleme"] = 99
    m = re.match(r"^\s*Başlık: (.*)", satir)
    if m and m.group(1).strip():
        is_["baslik"] = m.group(1).strip()
    m = re.match(r"^\s*Süre: (\d+) sn", satir)
    if m:
        is_["sure"] = int(m.group(1))
    if satir.startswith("Bitti. Dosya: "):
        is_["dosya"] = satir[len("Bitti. Dosya: "):].strip()
    k = satir.lower()
    if "giriş istiyor" in k or "login required" in k or "use --cookies" in k:
        is_["giris_gerekli"] = True
    if "please update" in k or "yt-dlp -u" in k or "güncellenmesi gerekiyor" in k:
        is_["guncelle_gerekli"] = True


def _satir_isle(is_, satir):
    if not satir.strip():
        return
    is_["log"].append(satir)
    if len(is_["log"]) > 400:
        del is_["log"][:100]
    m = re.match(r"^\s*Süre: (\d+) sn", satir)
    if m:
        is_["sure"] = int(m.group(1))
    m = re.match(r"^\s*Başlık: (.*)", satir)
    if m and m.group(1).strip():
        is_["baslik"] = m.group(1).strip()
    m = re.match(r"^\[(\d)/\d\]", satir)
    if m:
        is_["adim"] = int(m.group(1))
        is_["adim_metni"] = satir.strip()
        is_["ilerleme"] = 0
        if is_["adim"] == 3:
            is_["adim3_bas"] = time.time()
    m = re.search(r"\[download\]\s+([0-9.]+)% of", satir)
    if m and is_.get("adim", 0) <= 1:
        is_["ilerleme"] = min(99, int(float(m.group(1))))
    m = re.match(r"^\s+\[(\d+):(\d\d)\] ", satir)
    if m and is_.get("sure") and is_.get("adim") == 3:
        sn = int(m.group(1)) * 60 + int(m.group(2))
        is_["ilerleme"] = min(99, int(100 * sn / max(1, is_["sure"])))
        is_["model_iniyor"] = False
        is_["son_satir"] = re.sub(r"^\s+\[\d+:\d\d\]\s*", "", satir)
        is_["son_zaman"] = _zaman(sn, is_["sure"] >= 3600)
    if "Konuşma yazıya dökülüyor" in satir:
        is_["model_iniyor"] = False
    m = re.search(r"Görüntü: kare (\d+)/(\d+)", satir)
    if m:
        is_["goruntu_kare"] = [int(m.group(1)), int(m.group(2))]
    if "Görüntü inceleniyor" in satir:
        is_["goruntu_asama"] = True
        is_["son_satir"] = ""
    if satir.startswith("Bitti. Dosya: "):
        is_["txt"] = satir[len("Bitti. Dosya: "):].strip()
    k = satir.lower()
    if "login required" in k or "requested content is not available" in k or "rate-limit" in k or "use --cookies" in k or "giriş istiyor" in k:
        is_["giris_gerekli"] = True
    if "not a bot" in k or "please update" in k or "yt-dlp -u" in k:
        is_["guncelle_gerekli"] = True


def _zincir(is_):
    """Transkript bitince istenen ek işler: çeviri, ardından altyazılı video."""
    temel = is_.get("temel")
    if not temel:
        return
    if is_.get("couple"):        # Couple teslim kontrolü (2026-10-24): kurgucu videosu brief'e göre denetlenir; Ghost'a, Studio kitaplığına gitmez
        def _couple():
            try:
                import couple_video
                couple_video.yazi_bitti(is_["couple"], is_.get("couple_video") or "", temel)
            except Exception as e:  # noqa: BLE001
                print(f"Couple video denetimi yapılamadı: {e}", flush=True)
        threading.Thread(target=_couple, daemon=True).start()
        return
    try:     # X paylaşım önerileri: takip videolarında ve (2026-10-18, kullanıcı istedi) verdiği her videoda kendiliğinden
        import paylasim as paylasim_modulu
        pr = paylasim_modulu.profil()
        atolye_isi = "/.atolye/" in str(is_.get("link") or "")
        import claude_yaz
        # 24 Ekim (kullanıcının editoryal yöntemi; 4 Ekim düzeltmesi): takip edilen YAYINLARDAN doğrudan taslak yazılmaz (konuşmacının fikrini yeniden
        # anlatmak olur); bu yayınlar keşfe konu kaynağı olur (kesif.yayin_konulari: konu → asıl kaynak → ayrı gözlem).
        if not is_.get("misafir") and (is_.get("ghost") or (not is_.get("toplanti") and not atolye_isi and not is_.get("takip") and pr.get("her_video", True)
                                and claude_yaz.arka_plan_uygun())):
            threading.Thread(target=_paylasim_arka, args=(temel,), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass
    if is_.get("marka"):
        try:
            js = KLASOR / f"{temel}.json"; d = json.loads(js.read_text(encoding="utf-8")); d["veri"]["marka"] = is_["marka"]
            with kilit:
                js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    dil = is_.get("ceviri_dil") or ""
    alt = is_.get("altyazili")

    def _calis():
        if is_.get("marka"):
            _marka_baslat(temel, is_["marka"], ["kapak", "youtube", "blog", "shorts", "kurgu", "linkedin", "instagram"])
        if is_.get("toplanti") and "_toplanti_bitir" in globals():       # Meet kurulu değilse (yalnız Studio) toplantı adımı yok
            try:
                _toplanti_bitir(is_)
            except Exception as e:  # noqa: BLE001
                is_["drive"] = f"hata: {e}"
        db_dil = (is_.get("dublaj_dil") or dil) if is_.get("dublaj") else ""
        for cd in dict.fromkeys(x for x in (dil, db_dil) if x):   # altyazı ve dublaj farklı dillerde olabilir
            _ceviri_calistir(temel, cd)
        if db_dil:                                          # kendi sesiyle dublaj: çeviri bittikten sonra seslendirme işi
            try:
                with app.app_context():
                    _baslat({"islem": "dublaj", "temel": temel, "dil": db_dil, "baslik": is_.get("baslik") or temel, "kapak": is_.get("kapak") or "",
                             "sure": is_.get("sure") or 0, "kanal": is_.get("kanal") or "", "cerez": is_.get("cerez") or ""})
            except Exception as e:  # noqa: BLE001
                print(f"Dublaj başlatılamadı: {e}", flush=True)
        if alt:
            hedef_dil = dil if dil and (KLASOR / f"{temel}.{dil}.srt").exists() else "orijinal"
            dz = is_.get("duzen") or {}
            _video_isi_baslat({"islem": "altyazili", "temel": temel, "dil": hedef_dil, "stil": is_.get("altyazi_stil") or "kutu",
                               "font": is_.get("altyazi_font") or "", "renk": is_.get("altyazi_renk") or "",
                               "format": dz.get("format") or "", "dikey": dz.get("format") == "9:16", "zoom": dz.get("zoom"), "isim_bandi": dz.get("isim_bandi"),
                               "studyo": dz.get("studyo"), "tekrar": dz.get("tekrar"), "altyazisiz": dz.get("altyazisiz"), "emoji": dz.get("emoji"), "konusana": dz.get("konusana"), "arka": dz.get("arka") or "", "muzik": dz.get("muzik") or "",
                               "kalite": is_.get("video_kalite") or "720", "cerez": is_.get("cerez")})
    threading.Thread(target=_calis, daemon=True).start()



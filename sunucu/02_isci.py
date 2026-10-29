# sunucu/02_isci.py — yazıya dökme işçisi.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- işçi
def _yuklemeyi_sakla(is_):
    """Yazıya dökülen yüklenmiş dosya: VIDEO ise İndirilenler'e taşınır ve kaynak video olarak kaydedilir (kapak, Shorts, altyazılı video, kurgu
    sonradan da yapılabilsin; 2026-10-25: eskiden silindiği için yüklenen videolarda bunların hiçbiri yapılamıyordu). Ses dosyası silinir."""
    kaynak = Path(is_["link"])
    if not kaynak.is_file():
        return
    if kaynak.suffix.lower() not in (".mp4", ".mov", ".m4v", ".mkv", ".webm"):
        kaynak.unlink(); return
    INDIRILENLER.mkdir(exist_ok=True)
    import ortak
    ad = ortak.guvenli_ad(is_.get("baslik") or kaynak.stem)
    hedef = INDIRILENLER / f"{ad}{kaynak.suffix.lower()}"
    n = 2
    while hedef.exists():
        hedef = INDIRILENLER / f"{ad}_{n}{kaynak.suffix.lower()}"; n += 1
    shutil.move(str(kaynak), str(hedef))
    _indirme_bitir({"dosya": str(hedef), "link": is_["link"], "baslik": is_.get("baslik") or ad, "kanal": "", "kalite": "yukleme",
                    "sure": is_.get("sure") or 0, "kapak": is_.get("kapak") or "", "platform": "Dosya", "log": [], "temel": is_.get("temel") or ""})


def _sonucu_yukle(is_):
    temel = Path(is_["txt"]).with_suffix("")
    is_["temel"] = temel.name
    is_["ilerleme"] = 100
    js = temel.with_suffix(".json")
    if js.exists():
        if is_.get("takip"):
            try:
                d = json.loads(js.read_text(encoding="utf-8"))
                d["veri"]["takip"] = is_["takip"]
                js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        veri = json.loads(js.read_text(encoding="utf-8"))["veri"]
        is_["konusmacilar"] = veri["etiket"]
        is_["baslik"] = veri.get("baslik") or is_.get("baslik")
        _kapak_indir(temel.name, veri.get("kapak"))
        is_["kapak"] = _kapak_yolu(temel.name, veri.get("kapak"))


def _isci():
    while True:
        is_id = sira.get()
        is_ = isler.get(is_id)
        if not is_ or is_["durum"] != "sirada":
            sira.task_done()
            continue
        is_["durum"] = "calisiyor"
        is_["baslangic"] = time.time()
        is_["model_iniyor"] = not _model_var(is_["model"])
        komut = [PYTHON, "-u", str(SCRIPT), is_["link"], is_["dil"], is_["model"]]
        if is_["isimler"]:
            komut += ["--isimler", is_["isimler"]]
        if is_["cerez"]:
            komut += ["--cerez", is_["cerez"]]
        if not is_["altyazi"]:
            komut += ["--altyazi-yok"]
        ay = ayarlar_oku()
        ozet_ac = is_.get("ozet") if is_.get("ozet") is not None else ay.get("ozet", True)
        if not ozet_ac:
            komut += ["--ozet-yok"]
        else:
            komut += ["--ozet-dili", _ozet_dili(ay)]
        if is_.get("goruntu"):
            komut += ["--goruntu"]
        if is_.get("ad"):
            komut += ["--ad", is_["ad"]]
        if is_.get("ses_temizle"):
            komut += ["--ses-temizle"]
        if is_.get("konusmaci") is False:
            komut += ["--konusmaci-yok"]
        elif is_.get("konusmaci_sayisi"):
            komut += ["--konusmaci", str(int(is_["konusmaci_sayisi"]))]
        if Path("/usr/bin/caffeinate").exists():
            komut = ["/usr/bin/caffeinate", "-i"] + komut      # işlem sürerken Mac uyumasın
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
                _satir_isle(is_, satir)
                if time.time() - son_kayit > 5:
                    _kaydet(); son_kayit = time.time()
            p.wait()
            is_.pop("p", None)
            if is_["durum"] == "iptal":
                pass
            elif is_.get("txt") and Path(is_["txt"]).exists():
                if p.returncode != 0:
                    is_["log"].append(f"      (Not: iş tamamlandı, program kapanırken hata kodu {p.returncode} verdi; çıktılar sağlam.)")
                _sonucu_yukle(is_)          # kapak dahil her şey hazır olsun, sonra "bitti"
                is_["durum"] = "bitti"
                try:
                    import kalite
                    if is_.get("sure") and "/.atolye/" not in str(is_.get("link") or ""):
                        kalite.kaydet("transkript", sure_sn=round(time.time() - is_["baslangic"]), video_sn=int(is_["sure"]),
                                      oran=round((time.time() - is_["baslangic"]) / max(1, is_["sure"]), 3), toplanti=bool(is_.get("toplanti")))
                except Exception:  # noqa: BLE001
                    pass
                if is_.get("yerel") and is_.get("yerel_sil", True):
                    try:
                        _yuklemeyi_sakla(is_)
                    except Exception:  # noqa: BLE001
                        pass
                _bildir("Transkript hazır", is_.get("baslik") or is_["link"])
                _zincir(is_)
            else:
                is_["durum"] = "hata"
                is_["hata"] = ("İş yarıda kesildi; program beklenmedik biçimde kapandı." if p.returncode < 0
                               else _hata_metni("\n".join(is_["log"][-40:])))
                _bildir("Transkript olmadı", is_["hata"])
        except Exception as e:  # noqa: BLE001
            is_["durum"] = "hata"
            is_["hata"] = str(e)
        is_["bitis"] = time.time()
        _kaydet()
        sira.task_done()



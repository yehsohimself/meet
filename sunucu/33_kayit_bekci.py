# sunucu/33_kayit_bekci.py — Meet: toplantı kaçmasın (2026-10-30). 29 Ekim 20.28'de kaydedicinin izleme döngüsü askıda kalan bir macOS
# çağrısında durdu; süreç "çalışıyor" göründü, 30 Ekim sabahı Google Meet görüşmesi hiç kaydedilmedi, kimse fark etmedi.
# Kaydedicinin kendi bekçisine ek olarak site iki şeye bakar: (1) kaydedicinin nabzı (kayitlar/.kaydedici_nabiz, her turda yazılır) 3 dk'dır
# tazelenmediyse kaydedici yeniden başlatılır; (2) uzantı ya da ekrandaki pencere bir görüşme gösterdiği halde 60 sn'dir kayıt yoksa kaydedici
# bir kez yeniden başlatılır ve size bildirim gider. site.py bu dosyayı diğer parçalarla AYNI ad alanında yürütür.

KAYDEDICI_ETIKET = "com.yehso.transkript.kaydedici"
KAYIT_BEKCI = {"yeniden": 0.0, "gorusme_bas": 0.0, "gorusme_baslik": "", "uyarildi": "", "son_nabiz_uyari": 0.0, "hata_uyari": 0.0, "mik_uyari": ""}


def _kaydedici_yeniden(neden):
    if time.time() - KAYIT_BEKCI["yeniden"] < 600:                 # en çok 10 dk'da bir
        return False
    KAYIT_BEKCI["yeniden"] = time.time()
    print(f"Kayıt bekçisi: {neden}; kaydedici yeniden başlatılıyor", flush=True)
    try:
        r = subprocess.run(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{KAYDEDICI_ETIKET}"], capture_output=True, timeout=20)
        if r.returncode != 0:                                        # ajan hiç yüklü değil (bootout kalmış): plist'ten yeniden kur
            plist = Path.home() / "Library" / "LaunchAgents" / f"{KAYDEDICI_ETIKET}.plist"
            if plist.exists():
                subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], capture_output=True, timeout=20)
                print("Kayıt bekçisi: kaydedici ajanı yüklü değildi; yeniden kuruldu", flush=True)
            else:
                print("Kayıt bekçisi: kaydedici ajanı yok (plist bulunamadı)", flush=True)
                return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"Kayıt bekçisi: kaydedici yeniden başlatılamadı: {e}", flush=True)
        return False


def _gorusme_basligi():
    """Uzantıya göre şu an bir görüşmenin içinde miyiz (giriş ekranı değil). Döner: toplantı başlığı ya da None."""
    d = uzanti_durum
    if time.time() - float(d.get("zaman") or 0) > 30 or d.get("bekleme") or d.get("kayit"):
        return None
    baslik = str(d.get("baslik") or "")
    # uzantının "aramada" işareti kimi zaman gelmiyor (30 Ekim: Meet görüşmesinde 2 katılımcı varken false); Meet/Teams/Zoom sayfa başlığı da sayılır
    if d.get("arama") or re.search(r"^(Meet - |Meet – )|- Google Meet$", baslik) or re.search(r"\| Microsoft Teams$", baslik) and re.search(r"(?i)toplant|meeting|call|arama", baslik):
        return baslik or (d.get("platform") or "toplantı")
    return None


def kayit_bekci_tur(simdi=None):
    simdi = simdi or time.time()
    ay = ayarlar_oku()
    if not ay.get("oto_kayit", True):
        return None
    nabiz = KAYIT / ".kaydedici_nabiz"
    if nabiz.exists() and simdi - nabiz.stat().st_mtime > 180:
        if _kaydedici_yeniden(f"kaydedici {int(simdi - nabiz.stat().st_mtime)} sn'dir yanıt vermiyor") and simdi - KAYIT_BEKCI["son_nabiz_uyari"] > 3600:
            KAYIT_BEKCI["son_nabiz_uyari"] = simdi
            _bildir("Kaydedici takılmıştı", "Toplantı kaydedici yanıt vermiyordu; yeniden başlatıldı.", url="http://127.0.0.1:8766/")
        return "nabiz"
    baslik = _gorusme_basligi()
    canli = meet_kayit_canli()
    if canli and str(canli.get("sorun") or "").startswith("Ekran") and KAYIT_BEKCI["mik_uyari"] != canli.get("ad"):
        KAYIT_BEKCI["mik_uyari"] = canli.get("ad")                  # ekran yokken yalnız mikrofon kaydediliyor: karşı taraf sesi eksik kalabilir
        _bildir("Toplantı yalnız mikrofondan kaydediliyor", "Ekran bulunamadı (kapak kapalı ya da uyku). Ekranı açın; kayıt kendiliğinden tam kayda geçer.",
                url="http://127.0.0.1:8766/")
    if baslik and not canli:
        hata = KAYIT / ".kayit_hata.json"                           # kaydedici başlatamıyor (izin, cihaz): yeniden başlatmak çözmez, siz görmelisiniz
        try:
            h = json.loads(hata.read_text(encoding="utf-8")) if hata.exists() else None
        except Exception:  # noqa: BLE001
            h = None
        if h and simdi - float(h.get("zaman") or 0) < 120 and simdi - KAYIT_BEKCI["hata_uyari"] > 600:
            KAYIT_BEKCI["hata_uyari"] = simdi
            _bildir("Toplantı kaydedilemiyor", f"{baslik}: {h.get('hata')}. Sistem Ayarları → Gizlilik → Ekran Kaydı ve Mikrofon iznini kontrol edin.",
                    url="http://127.0.0.1:8766/")
            return "hata"
    if not baslik or canli or _kayit_disi_eslesen(baslik):
        KAYIT_BEKCI["gorusme_bas"] = 0.0
        if not baslik:
            KAYIT_BEKCI["uyarildi"] = ""
        return None
    if KAYIT_BEKCI["gorusme_baslik"] != baslik or not KAYIT_BEKCI["gorusme_bas"]:
        KAYIT_BEKCI.update(gorusme_bas=simdi, gorusme_baslik=baslik)
        return None
    if simdi - KAYIT_BEKCI["gorusme_bas"] < 60 or KAYIT_BEKCI["uyarildi"] == baslik:
        return None
    KAYIT_BEKCI["uyarildi"] = baslik
    _kaydedici_yeniden(f"görüşme var ({baslik}) ama kayıt yok")
    _bildir("Toplantı kaydedilmiyor", f"{baslik}: kaydedici yeniden başlatıldı. Kırmızı nokta menü çubuğunda belirmezse Meet'i açın.",
            url="http://127.0.0.1:8766/")
    return "uyari"


def _kayit_bekci_dongu():
    while True:
        time.sleep(15)
        try:
            kayit_bekci_tur()
        except Exception as e:  # noqa: BLE001
            print(f"Kayıt bekçisi: {e}", flush=True)


threading.Thread(target=_kayit_bekci_dongu, daemon=True).start()


def kayit_sagligi():
    """Tek bakışta: toplantıya girince kayıt başlar mı? (Meet ana sayfasındaki durum hapı ve sağlık denetimi.)
    durum: kayit (sürüyor) | hazir | sorun; sorunlar [{kod, metin, cozum}]."""
    simdi = time.time(); ay = ayarlar_oku(); sorunlar = []; v = {}
    nabiz = KAYIT / ".kaydedici_nabiz"
    try:
        nabiz_yas = simdi - nabiz.stat().st_mtime
    except OSError:
        nabiz_yas = None
    v["nabiz_yas"] = None if nabiz_yas is None else int(nabiz_yas)
    try:
        izin = json.loads((KAYIT / ".kaydedici_izin.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        izin = {}
    v["izin"] = {"ekran": izin.get("ekran"), "mikrofon": izin.get("mikrofon")}
    if not ay.get("oto_kayit", True):
        sorunlar.append({"kod": "oto_kayit", "metin": "Otomatik kayıt kapalı", "cozum": "Ayarlar → Kayıt → Otomatik toplantı kaydı"})
    if nabiz_yas is None or nabiz_yas > 180:
        sorunlar.append({"kod": "kaydedici", "metin": "Kayıt yardımcısı yanıt vermiyor" if nabiz_yas is not None else "Kayıt yardımcısı hiç çalışmamış",
                         "cozum": "Birkaç saniye içinde kendiliğinden yeniden başlatılır; olmazsa Mac’i yeniden başlatın"})
    if izin and izin.get("ekran") is False:
        sorunlar.append({"kod": "izin_ekran", "metin": "Ekran ve Sistem Sesi Kaydı izni yok; karşı tarafın sesi alınamaz",
                         "cozum": "Sistem Ayarları → Gizlilik ve Güvenlik → Ekran ve Sistem Sesi Kaydı → Transkript Kaydedici"})
    if izin and izin.get("mikrofon") == "yok":
        sorunlar.append({"kod": "izin_mik", "metin": "Mikrofon izni yok; sizin sesiniz alınamaz", "cozum": "Sistem Ayarları → Gizlilik ve Güvenlik → Mikrofon → Transkript Kaydedici"})
    try:
        h = json.loads((KAYIT / ".kayit_hata.json").read_text(encoding="utf-8"))
        if simdi - float(h.get("zaman") or 0) < 600:
            sorunlar.append({"kod": "hata", "metin": f"Son kayıt denemesi başarısız: {h.get('hata')}", "cozum": "İzinleri kontrol edin"})
    except Exception:  # noqa: BLE001
        pass
    k = meet_kayit_canli()
    if k:
        v["kayit"] = {"ad": k.get("ad"), "sure": int(simdi - float(k.get("baslangic") or simdi)), "sorun": k.get("sorun") or "", "ses_yas": int(simdi - float(k.get("son_ses") or simdi)),
                      "kapaniyor": k.get("kapaniyor")}                       # toplantı sinyali kesildi, kayıt N sn içinde kapanır (kopuk bağlantı payı)
    u = dict(uzanti_durum); u_yas = simdi - float(u.get("zaman") or 0)
    v["uzanti"] = {"surum": u.get("surum"), "aktif": u_yas < 30, "arama": bool(u.get("arama")) and u_yas < 30, "baslik": u.get("baslik") if u_yas < 30 else ""}
    v["sorunlar"] = sorunlar
    v["durum"] = "kayit" if k else ("sorun" if sorunlar else "hazir")
    v["kontrol"] = int(min(x for x in [nabiz_yas if nabiz_yas is not None else 10**6, 15] )) if nabiz_yas is not None else None
    return v


@app.get("/api/meet/kayit-saglik")
def meet_kayit_saglik_get():
    return jsonify(kayit_sagligi())


@app.post("/api/kayit/durdur")
def kayit_durdur_post():
    """Süren masaüstü kaydını hemen bitir (2026-10-30: toplantı bitince kayıt 45 sn daha sürüyor, kişi 'hâlâ kaydediyor' diye endişeleniyordu).
    Kaydedici izleme döngüsünde bayrağı görünce kaydı kapatır, dosyayı birleştirir ve notlar başlar."""
    if not meet_kayit_canli():
        return jsonify({"tamam": False, "neden": "Süren kayıt yok"}), 409
    KAYIT.mkdir(exist_ok=True)
    (KAYIT / ".kayit_durdur").write_text(str(time.time()), encoding="utf-8")
    return jsonify({"tamam": True})

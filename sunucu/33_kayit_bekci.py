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

# sunucu/14_haftalik.py — haftalık özetler.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- haftalık özetler, brief, takip e-postası (Claude)
haftalik_durum = {"calisiyor": False, "tur": "", "hata": "", "log": [], "eposta": ""}
OZETLER = KLASOR / "ozetler"


def _haftalik_calistir(tur, gonder=False):
    import haftalik
    haftalik_durum.update(calisiyor=True, tur=tur, hata="", log=[], eposta="")
    try:
        k = (haftalik.takip_ozeti if tur == "takip" else haftalik.musteri_ozeti)(7, log=lambda m: haftalik_durum["log"].append(m))
        if not k:
            haftalik_durum["hata"] = "Son 7 günde " + ("takip ettiğiniz kanallardan video gelmemiş." if tur == "takip" else "toplantı yok.")
        else:
            if gonder:
                h = haftalik.eposta_gonder(k)
                haftalik_durum["eposta"] = h or "gönderildi"
            _bildir("Haftalık özet hazır", k["baslik"])
    except Exception as e:  # noqa: BLE001
        haftalik_durum["hata"] = str(e)
    haftalik_durum["calisiyor"] = False


def _haftalik_dongu():
    """Pazartesi 08.00'den sonra: haftalık müşteri özeti (e-postayla) ve takip özeti, haftada bir kez."""
    while True:
        time.sleep(1800)
        try:
            simdi = time.localtime()
            if simdi.tm_wday != 0 or simdi.tm_hour < 8:
                continue
            hafta = time.strftime("%G-%V")
            dosya = OZETLER / ".son_hafta"
            if dosya.exists() and dosya.read_text().strip() == hafta:
                continue
            import claude_yaz
            if not claude_yaz.hazir(toplanti_icerik=False):
                continue
            OZETLER.mkdir(exist_ok=True); dosya.write_text(hafta)
            if ayarlar_oku().get("haftalik_eposta", True) and claude_yaz.hazir(toplanti_icerik=True):
                _haftalik_calistir("musteri", gonder=True)
            _haftalik_calistir("takip")
        except Exception as e:  # noqa: BLE001
            print(f"Haftalık özet hatası: {e}", flush=True)


threading.Thread(target=_haftalik_dongu, daemon=True).start()


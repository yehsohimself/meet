"""Toplantı kaçmasın (2026-10-30): kaydedici takılırsa ya da görüşme varken kayıt yoksa site kaydediciyi yeniden başlatır ve haber verir (sanal kök)."""
import os
import time


def _hazirla(site, monkeypatch):
    yeniden, bildirim = [], []
    class R:  # noqa: D401
        returncode = 0
    monkeypatch.setattr(site.subprocess, "run", lambda a, **k: yeniden.append(a) or R())
    monkeypatch.setattr(site, "_bildir", lambda *a, **k: bildirim.append(a))
    monkeypatch.setattr(site, "meet_kayit_canli", lambda: None)
    site.KAYIT_BEKCI.update(yeniden=0.0, gorusme_bas=0.0, gorusme_baslik="", uyarildi="", son_nabiz_uyari=0.0)
    site.KAYIT.mkdir(exist_ok=True)
    ay = site.ayarlar_oku(); ay["oto_kayit"] = True; ay["kayit_disi"] = []; site.ayarlar_yaz(ay)
    return yeniden, bildirim


def test_takilan_kaydedici_yeniden_baslar(site, monkeypatch):
    yeniden, bildirim = _hazirla(site, monkeypatch)
    n = site.KAYIT / ".kaydedici_nabiz"; n.write_text("1")
    os.utime(n, (time.time() - 400, time.time() - 400))
    assert site.kayit_bekci_tur() == "nabiz"
    assert yeniden and "kickstart" in yeniden[0] and bildirim
    assert site.kayit_bekci_tur() == "nabiz" and len(yeniden) == 1          # 10 dk içinde ikinci kez başlatılmaz
    n.unlink()


def test_gorusme_var_kayit_yok_uyarir(site, monkeypatch):
    yeniden, bildirim = _hazirla(site, monkeypatch)
    t = time.time()
    # uzantı "aramada" demese de Meet sayfa başlığı görüşmeyi gösterir (30 Ekim)
    site.uzanti_durum.update(zaman=t, platform="meet", baslik="Meet - Haftalık görüşme", arama=False, bekleme=False, kayit="")
    assert site.kayit_bekci_tur(t) is None                                    # sayaç başladı
    assert site.kayit_bekci_tur(t + 30) is None                               # 60 sn dolmadı
    site.uzanti_durum["zaman"] = t + 70
    assert site.kayit_bekci_tur(t + 70) == "uyari" and yeniden and bildirim
    assert site.kayit_bekci_tur(t + 80) is None                               # aynı toplantı için bir kez
    # giriş ekranında ya da kayıt sürerken uyarmaz
    site.KAYIT_BEKCI.update(yeniden=0.0, gorusme_bas=0.0, uyarildi="")
    site.uzanti_durum.update(zaman=t + 90, bekleme=True)
    assert site.kayit_bekci_tur(t + 90) is None and site.kayit_bekci_tur(t + 200) is None
    site.uzanti_durum.update(bekleme=False)
    monkeypatch.setattr(site, "meet_kayit_canli", lambda: {"ad": "x"})
    site.uzanti_durum["zaman"] = t + 300
    assert site.kayit_bekci_tur(t + 300) is None and site.kayit_bekci_tur(t + 400) is None


def test_kaydedilmeyen_toplantida_uyarmaz(site, monkeypatch):
    yeniden, bildirim = _hazirla(site, monkeypatch)
    ay = site.ayarlar_oku(); ay["kayit_disi"] = [{"ad": "IK 18", "desenler": ["IK 18"]}]; site.ayarlar_yaz(ay)
    t = time.time()
    site.uzanti_durum.update(zaman=t, platform="teams", baslik="(2) Toplantıya katılma | IK 18 | Microsoft Teams", arama=True, bekleme=False, kayit="")
    for s in (0, 70, 140):
        site.uzanti_durum["zaman"] = t + s
        assert site.kayit_bekci_tur(t + s) is None
    assert not yeniden and not bildirim
    ay["kayit_disi"] = []; site.ayarlar_yaz(ay)


def test_kayit_baslatilamiyorsa_bildirir(site, monkeypatch):
    yeniden, bildirim = _hazirla(site, monkeypatch)
    import json
    t = time.time()
    site.uzanti_durum.update(zaman=t, platform="meet", baslik="Haftalık görüşme - Google Meet", arama=False, bekleme=False, kayit="")
    (site.KAYIT / ".kayit_hata.json").write_text(json.dumps({"zaman": t, "hata": "Ekran bulunamadı"}))
    assert site.kayit_bekci_tur(t) == "hata" and bildirim and "Ekran bulunamadı" in bildirim[0][1] and not yeniden
    assert site.kayit_bekci_tur(t + 20) is None                               # 10 dk'da bir
    (site.KAYIT / ".kayit_hata.json").unlink()
    # yalnız mikrofon kaydı sürüyorsa bir kez haber verir
    monkeypatch.setattr(site, "meet_kayit_canli", lambda: {"ad": "Toplantı x", "sorun": "Ekran bulunamadı; yalnız mikrofon kaydediliyor"})
    bildirim.clear()
    site.kayit_bekci_tur(t + 40); site.kayit_bekci_tur(t + 60)
    assert len(bildirim) == 1 and "mikrofon" in bildirim[0][0]


def test_ajan_yuklu_degilse_kurulur(site, monkeypatch):
    calisan = []
    class R:  # noqa: D401
        returncode = 1
    monkeypatch.setattr(site.subprocess, "run", lambda a, **k: calisan.append(a) or R())
    monkeypatch.setattr(site.Path, "home", classmethod(lambda c: site.KLASOR))
    (site.KLASOR / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
    (site.KLASOR / "Library" / "LaunchAgents" / "com.yehso.transkript.kaydedici.plist").write_text("x")
    site.KAYIT_BEKCI["yeniden"] = 0.0
    assert site._kaydedici_yeniden("deneme") and calisan[0][1] == "kickstart" and calisan[1][1] == "bootstrap"


def test_kayit_sagligi(site, istemci, monkeypatch):
    import json
    monkeypatch.setattr(site, "meet_kayit_canli", lambda: None)
    site.KAYIT.mkdir(exist_ok=True)
    ay = site.ayarlar_oku(); ay["oto_kayit"] = True; site.ayarlar_yaz(ay)
    (site.KAYIT / ".kaydedici_nabiz").write_text("1")
    (site.KAYIT / ".kaydedici_izin.json").write_text(json.dumps({"ekran": True, "mikrofon": "var", "zaman": time.time()}))
    (site.KAYIT / ".kayit_hata.json").unlink(missing_ok=True)
    v = istemci.get("/api/meet/kayit-saglik").get_json()
    assert v["durum"] == "hazir" and not v["sorunlar"]
    (site.KAYIT / ".kaydedici_izin.json").write_text(json.dumps({"ekran": False, "mikrofon": "yok", "zaman": time.time()}))
    v = istemci.get("/api/meet/kayit-saglik").get_json()
    assert v["durum"] == "sorun" and {s["kod"] for s in v["sorunlar"]} == {"izin_ekran", "izin_mik"}
    monkeypatch.setattr(site, "meet_kayit_canli", lambda: {"ad": "Toplantı x", "baslangic": time.time() - 90, "son_ses": time.time(), "sorun": ""})
    v = istemci.get("/api/meet/kayit-saglik").get_json()
    assert v["durum"] == "kayit" and v["kayit"]["sure"] >= 89
    (site.KAYIT / ".kaydedici_izin.json").unlink()

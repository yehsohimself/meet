"""Bağlantı kopunca bölünen toplantı kayıtları birleşir (sanal kök; gerçek kayıtlara dokunmaz, Claude ve iş kuyruğu sahte)."""
import json
import subprocess
import time


def _ses(yol, sn, frekans):
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={frekans}:duration={sn}",
                    "-c:a", "aac", str(yol)], check=True)


def test_devam_kaydi_birlesir(site, monkeypatch):
    K = site.KAYIT; K.mkdir(exist_ok=True)
    a, b = K / "Toplantı 2026-10-27 15.29.m4a", K / "Toplantı 2026-10-27 16.20.m4a"
    _ses(a, 8, 440); _ses(b, 5, 660)
    bas0 = 1793104140.0
    site.isler["onceki"] = {"id": "onceki", "toplanti": True, "durum": "sirada", "kayit_baslangic": bas0, "kayit_bitis": bas0 + 8,
                            "kayit_dosya": str(a), "mik_dosya": "", "uygulama": "com.google.Chrome.helper",
                            "toplanti_baslik": "Int Kick-off: Ak Portföy", "katilimcilar": ["Ayşe"], "log": []}
    baslatilan = []
    bekle = time.sleep
    monkeypatch.setattr(site, "_baslat", lambda v: baslatilan.append(v) or site.jsonify({"id": "yeni"}))
    monkeypatch.setattr(site, "_bildir", lambda *a, **k: None)
    monkeypatch.setattr(site.time, "sleep", lambda s: None)
    # ad farklıysa devam sayılmaz
    assert not site.meet_devam_mi(b, bas0 + 60, bas0 + 65, "", "Başka toplantı", "com.google.Chrome.helper", [], None)
    # aynı ad, 52 sn ara: devam
    with site.app.app_context():
        assert site.meet_devam_mi(b, bas0 + 60, bas0 + 65, "", "Int Kick-off: Ak Portföy", "com.google.Chrome.helper", ["Can"], None)
        for _ in range(100):
            if baslatilan:
                break
            bekle(0.2)
    assert baslatilan, "birleşik kayıt işe verilmedi"
    v = baslatilan[0]
    assert v["kayit_dosya"] == str(a) and v["kayit_baslangic"] == bas0 and v["katilimcilar"] == ["Ayşe", "Can"]
    sure = float(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(a)],
                                capture_output=True, text=True).stdout)
    assert 64 < sure < 67                                      # 8 sn + 52 sn kopukluk (sessiz) + 5 sn
    assert (K / ".parcalar" / a.stem / b.name).exists() and not b.exists()
    assert "onceki" not in site.isler


def test_listeden_kaldirma_drive_klasorunu_de_alir_geri_al_koyar(site, monkeypatch, tmp_path):
    """22 Ekim: kaldırılan toplantının Drive klasörü yerinde kalıyordu."""
    d = tmp_path / "Drive" / "Toplantılar" / "Genel" / "2026-10-22 09.26 Deneme"; d.mkdir(parents=True)
    (d / "a.txt").write_text("x", encoding="utf-8")
    site.COP.mkdir(exist_ok=True)
    temel = "transkript_tr_Toplantı_2026_10_22_09"
    (site.COP / f"{temel}.json").write_text(json.dumps({"veri": {"toplanti": True, "drive": str(d)}, "segmentler": []}), encoding="utf-8")
    monkeypatch.setattr(site, "_drive_cope", lambda k: (__import__("shutil").rmtree(k), True)[1])   # gerçek Çöp'e dokunma
    site._meet_sil_drive(temel)
    assert not d.exists() and (site.COP / f"drive__{temel}" / "a.txt").exists()
    site._meet_geri_drive(temel)
    assert (d / "a.txt").exists() and not (d / ".yer").exists()


def test_baska_siteden_istek_reddedilir(site):
    """2026-10-27: her yanıt 'Access-Control-Allow-Origin: *' taşıyordu; başka bir site toplantıları okuyup silebilirdi."""
    c = site.app.test_client()
    r = c.get("/api/gecmis", headers={"Origin": "https://kotu.example"})
    assert "Access-Control-Allow-Origin" not in r.headers
    r = c.get("/api/gecmis", headers={"Origin": "http://127.0.0.1:8766"})
    assert r.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:8766"
    assert c.delete("/api/sil/transkript_x", headers={"Origin": "https://kotu.example"}).status_code == 403
    assert c.post("/api/kayit/dosya", data="{}", headers={"Origin": "null"}).status_code == 403
    assert c.post("/api/kayit/dosya", data="{}", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.get("/api/gecmis", headers={"Host": "saldirgan.example"}).status_code == 403          # DNS yeniden bağlama
    assert c.get("/api/gecmis", headers={"Host": "Emre-MacBook-Air.local:8766"}).status_code == 200

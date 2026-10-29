"""Kaydedilmeyen toplantılar (2026-10-29): her hafta tekrar eden kurs vb. bir kez tanınınca kaydedilmez (sanal kök; gerçek ayarlara dokunmaz)."""
import json

import kayit_disi


def test_imza_ve_eslesme():
    assert kayit_disi.imza("(2) Toplantıya katılma | IK 18 | Microsoft Teams") == "IK 18"
    assert kayit_disi.imza("2026-10-28 20.21 · Ekipler ve Kanallar | Integrationskurs virtuell 18 | Genel") == "Integrationskurs virtuell 18"
    assert kayit_disi.imza("Meet - abc-defg-hij") == ""
    ay = {"kayit_disi": [{"ad": "Almanca kursu", "desenler": ["IK 18", "Integrationskurs"]}]}
    assert kayit_disi.eslesen(["(2) Toplantıya katılma | IK  18 | Microsoft Teams"], ay)["ad"] == "Almanca kursu"
    assert kayit_disi.eslesen(["Ekipler ve Kanallar | Integrationskurs virtuell 18 | Genel"], ay)
    assert not kayit_disi.eslesen(["PIK 180 haftalık | Microsoft Teams"], ay)          # sözcük sınırı
    assert not kayit_disi.eslesen(["Mustela haftalık görüşme"], ay)
    L, eklendi = kayit_disi.ekle(ay, "IK 18")
    assert not eklendi and len(L) == 1                                                  # zaten listede


def test_kurs_kaydi_yaziya_dokulmez(site, istemci, monkeypatch):
    K = site.KAYIT; K.mkdir(exist_ok=True)
    ay = site.ayarlar_oku(); ay["kayit_disi"] = [{"ad": "IK 18", "desenler": ["IK 18"]}]; site.ayarlar_yaz(ay)
    baslatilan = []
    monkeypatch.setattr(site, "_baslat", lambda v: baslatilan.append(v) or site.jsonify({"id": "x"}))
    monkeypatch.setattr(site, "_bildir", lambda *a, **k: None)
    ses, mik = K / "Toplantı 2026-10-29 20.03.m4a", K / "Toplantı 2026-10-29 20.03.mik.m4a"
    ses.write_bytes(b"0" * 100); mik.write_bytes(b"0" * 100)
    r = istemci.post("/api/kayit/dosya", json={"dosya": str(ses), "mik_dosya": str(mik), "uygulama": "com.google.Chrome.helper",
                                               "pencere": "(2) Toplantıya katılma | IK 18 | Microsoft Teams", "baslangic": 1793293429})
    assert r.get_json().get("kayit_disi") == "IK 18"
    assert not baslatilan and not ses.exists() and not mik.exists()
    assert (site.COP / f"kayit_disi__{ses.name}").exists()
    # uzantı bu görüşmede "aramadayım" deyince kaydedici bayrağı yazılmaz, yerine kaydedilmeyen bayrağı
    (K / ".uzanti_arama").unlink(missing_ok=True)
    istemci.post("/api/uzanti/durum", json={"aktif": True, "platform": "teams", "baslik": "IK 18 | Microsoft Teams"})
    assert (K / ".kayit_disi_arama").exists() and not (K / ".uzanti_arama").exists()
    ay = site.ayarlar_oku(); ay["kayit_disi"] = []; site.ayarlar_yaz(ay)


def test_kapi_iki_ayri_gunde_ogrenir(site, monkeypatch):
    monkeypatch.setattr(site, "_bildir", lambda *a, **k: None)
    site.KAYIT_DISI_GECMIS.unlink(missing_ok=True)
    assert not site._kayit_disi_ogren_kapi("Toplantıya katılma | Yoga dersi | Microsoft Teams", "2026-10-20")
    assert site._kayit_disi_ogren_kapi("Toplantıya katılma | Yoga dersi | Microsoft Teams", "2026-10-27")
    L = site.ayarlar_oku().get("kayit_disi")
    assert L and L[0]["ad"] == "Yoga dersi" and L[0]["otomatik"]
    assert site._kayit_disi_eslesen("Yoga dersi | Microsoft Teams")
    r = site.app.test_client().post("/api/kayit-disi", json={"sil": 0})
    assert r.get_json()["liste"] == []
    assert json.loads(site.KAYIT_DISI_GECMIS.read_text())

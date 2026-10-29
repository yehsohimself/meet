"""Giriş (bekleme) ekranında hazırlık notu (2026-10-28): uzantı Meet'in giriş ekranını ve içerideki kişileri bildirir; not görüşmeye girmeden yazılır,
girince 45 sn sonra yeniden yazılmaz; yeni bir giriş ekranında önceki toplantının notu görünmez."""
import sys
import time


def _bekle(site, sn=3):
    son = time.time() + sn
    while site.CANLI_BRIF["calisiyor"] and time.time() < son:
        time.sleep(0.05)


def test_giris_ekraninda_hazirlik_notu(site, istemci, monkeypatch):
    import onbrifing
    cagri = []

    def sahte(baslik, kisiler, platform="", log=print):
        cagri.append((baslik, list(kisiler)))
        return {"id": f"canli:{len(cagri)}", "ad": baslik or "Süren toplantı", "bas": time.time(), "kisiler": list(kisiler), "metin": "- Açık iş: afiş"}
    monkeypatch.setattr(onbrifing, "canli_hazirla", sahte)
    monkeypatch.setattr(site, "ayarlar_oku", lambda: {"benim_adim": "Emre Deneme"})
    site.CANLI_BRIF.update({"kayit": None, "son_nabiz": 0, "bekleme_anahtar": "", "bekleme_sayi": 0, "bekleme_kisi": 0, "bekleme_t": 0, "ilk": 0, "calisiyor": False})
    nabiz = lambda **k: istemci.post("/api/uzanti/durum", json={"platform": "meet", "baslik": "Meet - abc-defg-hij", "surum": "3.21", **k})   # noqa: E731

    # adsız ve kimsesiz giriş ekranı: not yazılmaz
    nabiz(bekleme=True, katilimcilar=[]); _bekle(site)
    assert cagri == []
    # içeride iki kişi: hemen yazılır (45 sn beklenmez), kullanıcının kendisi listede sayılmaz
    nabiz(bekleme=True, katilimcilar=["Ayşe Yılmaz", "Can Demir", "Emre Deneme"]); _bekle(site)
    assert cagri == [("", ["Ayşe Yılmaz", "Can Demir"])]
    d = istemci.get("/api/uzanti/durum").get_json()
    assert d["bekleme"] and not d["arama"]
    ob = istemci.get("/api/on-brifing").get_json()
    assert ob["bekleme"] and ob["suren"]["metin"].startswith("- Açık iş")
    # aynı kişilerle tekrar nabız: yeniden yazılmaz
    nabiz(bekleme=True, katilimcilar=["Ayşe Yılmaz", "Can Demir"]); _bekle(site)
    assert len(cagri) == 1
    # görüşmeye girildi: 45 sn sonra bile aynı kişilerle yeniden yazılmaz (giriş ekranında yazıldı)
    nabiz(aktif=True, katilimcilar=["Ayşe Yılmaz", "Can Demir"]); _bekle(site)
    site.CANLI_BRIF["ilk"] -= 60
    nabiz(aktif=True, katilimcilar=["Ayşe Yılmaz", "Can Demir"]); _bekle(site)
    assert len(cagri) == 1
    assert istemci.get("/api/uzanti/durum").get_json()["arama"]
    # görüşmede iki kişi daha belirdi: bir kez yenilenir, sonra yenilenmez
    nabiz(aktif=True, katilimcilar=["Ayşe Yılmaz", "Can Demir", "Deniz Ak", "Ece Su"]); _bekle(site)
    nabiz(aktif=True, katilimcilar=["Ayşe Yılmaz", "Can Demir", "Deniz Ak", "Ece Su", "Fırat Ok", "Gül Tan"]); _bekle(site)
    assert len(cagri) == 2
    # iki saat sonra başka bir toplantının giriş ekranı: eski not görünmez
    site.CANLI_BRIF["son_nabiz"] -= 7200
    monkeypatch.setattr(onbrifing, "canli_hazirla", lambda *a, **k: (time.sleep(0.5), sahte(*a, **k))[1])
    nabiz(bekleme=True, katilimcilar=["Selin Kaya"])
    assert istemci.get("/api/on-brifing").get_json()["suren"] is None
    _bekle(site)
    assert cagri[-1] == ("", ["Selin Kaya"])

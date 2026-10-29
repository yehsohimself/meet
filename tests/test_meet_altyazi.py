"""Meet altyazısı: eşleme, konuşmacı düzeltme, boşluk doldurma, Claude düzeltme süzgeci (Claude sahte)."""
import meet_altyazi as m


def _seg(bas, bit, k, metin):
    return {"bas": bas, "bit": bit, "k": k, "metin": metin}


ALTYAZI = [
    {"t": 1.0, "son": 5.0, "ad": "Ayşe", "metin": "Bütçeyi bu hafta onaylayalım, kampanya pazartesi başlasın"},
    {"t": 6.0, "son": 10.0, "ad": "Can", "metin": "Afiş tasarımını perşembeye kadar bitiririm"},
    {"t": 11.0, "son": 14.0, "ad": "Ayşe", "metin": "Metinleri cuma günü gönderirim tamam mı"},
    {"t": 30.0, "son": 36.0, "ad": "Can", "metin": "Packshot çekimini de salı günü yapalım derim"},
]


def test_eslesme_ve_konusmaci_duzeltme():
    seg = [_seg(0.5, 4.8, "0", "Büyüceyi bu hafta onaylayalım kampanya pazartesi başlasın"),
           _seg(5.5, 9.8, "1", "Afiş tasarımını perşembeye kadar bitiririm"),
           _seg(10.5, 13.8, "1", "Metinleri cuma günü gönderirim tamam mı")]     # küme yanlış: Ayşe'nin sözü 1'de
    es = m.eslestir(seg, ALTYAZI)
    assert es[0][2] == "metin" and es[2][0] == 2
    assert m.uyum(seg, es) == 1.0
    n = m.konusmaci_duzelt(seg, ALTYAZI, es)
    # küme 1 karışık (Can %57 < %60: adsız); Ayşe'nin kümesi 0 → onun sözü 0'a taşınır, Can'ınki 1'de kalır
    assert n == 1 and seg[2]["k"] == "0" and seg[2]["k_altyazi"] == "1" and seg[1]["k"] == "1"


def test_bosluk_doldur_ve_olaylar():
    seg = [_seg(0.5, 4.8, "0", "Bütçeyi bu hafta onaylayalım kampanya pazartesi başlasın"),
           _seg(5.5, 9.8, "1", "Afiş tasarımını perşembeye kadar bitiririm")]
    es = m.eslestir(seg, ALTYAZI)
    eklenen = m.bosluk_doldur(seg, ALTYAZI, es)
    assert eklenen == 2 and seg[-1]["kaynak"] == "altyazi" and seg[-1]["k"] == "1"     # Can → küme 1
    assert [o["ad"] for o in m.olaylar(ALTYAZI)] == ["Ayşe", "Can", "Ayşe", "Can"]


def test_baska_dil_metne_karismaz(monkeypatch):
    import claude_yaz
    monkeypatch.setattr(claude_yaz, "hazir", lambda: False)
    seg = [_seg(0.5, 4.8, "0", "Bütçeyi bu hafta onaylayalım kampanya pazartesi başlasın")]
    ing = [{"t": 1.0, "son": 5.0, "ad": "Ayşe", "metin": "Let's approve the budget this week and start monday"}]
    oz = m.uygula(seg, ing, log=lambda *_: None)
    assert oz["uyum"] == 0.0 and "eklenen" not in oz and len(seg) == 1


def test_claude_duzeltme_suzgeci(monkeypatch):
    import claude_yaz
    monkeypatch.setattr(claude_yaz, "hazir", lambda: True)
    monkeypatch.setattr(claude_yaz, "sor_json", lambda *a, **k: {"duzeltmeler": [
        {"satir": 0, "eski": "Büyüceyi", "yeni": "Bütçeyi", "kaynak": "altyazi", "neden": "altyazı"},
        {"satir": 1, "eski": "Pekşat", "yeni": "Packshot", "kaynak": "baglam", "neden": "çekim konuşuluyor"},
        {"satir": 1, "eski": "salı", "yeni": "cuma", "kaynak": "baglam", "neden": "anlam değişikliği"}]})
    seg = [_seg(0.5, 4.8, "0", "Büyüceyi bu hafta onaylayalım kampanya pazartesi başlasın"),
           _seg(29.5, 36, "1", "Pekşat çekimini de salı günü yapalım derim")]
    oz = m.uygula(seg, ALTYAZI[:1], log=lambda *_: None)
    assert seg[0]["metin"].startswith("Bütçeyi") and seg[0]["duzeltmeler"][0]["kaynak"] == "altyazi"
    assert seg[1]["metin"].startswith("Packshot") and seg[1]["duzeltmeler"][0]["kaynak"] == "baglam"
    assert "salı" in seg[1]["metin"]                                    # sesçe benzemeyen anlam değişikliği reddedildi
    assert oz["metin_duzeltme"] == 2 and oz["altyazidan"] == 1 and seg[1]["ham_metin"].startswith("Pekşat")


def test_uc_ve_toplanti_akisi(kok, site, istemci, monkeypatch):
    """Uzantı ucu satırları yazar; kayıt aralığı dosyaya çıkar; toplantı sonrası ilk adım konuşmacı olaylarını ve özeti ekler."""
    import json
    import time
    import claude_yaz
    import meet_altyazi as ma
    from tests.conftest import transkript_yaz
    monkeypatch.setattr(ma, "KAYIT", kok / "kayitlar"); monkeypatch.setattr(ma, "DOSYA", kok / "kayitlar" / "uzanti_altyazi.jsonl")
    monkeypatch.setattr(claude_yaz, "hazir", lambda: False)
    bas = time.time()
    r = istemci.post("/api/uzanti/altyazi", json={"platform": "meet", "satirlar": [
        {"ts": bas + 0.5, "son": bas + 4.2, "ad": "Ayşe", "metin": "Merhaba bugün borç konusunu konuşacağız"},
        {"ts": bas + 5.0, "son": bas + 9.2, "ad": "Ayşe", "metin": "Kredi kartı borcu en pahalı borçtur"}, {"metin": ""}]})
    assert r.status_code == 200 and r.get_json()["n"] == 2
    yol = site.meet_altyazi_dosyasi(kok / "kayitlar" / "Toplantı x.m4a", bas, bas + 20)
    assert yol and len(json.loads(open(yol).read())["satirlar"]) == 2
    transkript_yaz(kok, "transkript_tr_altyazi_deneme", toplanti=True)
    is_ = {"temel": "transkript_tr_altyazi_deneme", "altyazi_dosya": yol, "log": []}
    site.meet_altyazi_uygula(is_)
    d = json.loads((kok / "transkript_tr_altyazi_deneme.json").read_text())
    assert d["veri"]["altyazi"]["uyum"] >= 0.5 and d["veri"]["altyazi"]["adlar"] == ["Ayşe"]
    assert [o["ad"] for o in is_["konusmaci_olaylari"]] == ["Ayşe", "Ayşe"] and is_["altyazi_uygulandi"]
    assert (kok / "transkript_tr_altyazi_deneme.altyazi.json").exists()


def test_kayit_canli_durum(kok, site, istemci, monkeypatch):
    """Kaydedicinin canlı durum dosyası → /api/kayit/canli-durum (süre, sorun, sessizlik, kartlar); eski dosya 'kayıt yok' sayılır."""
    import json
    import time
    monkeypatch.setattr(site, "_bildir", lambda *a, **k: None)
    yol = kok / "kayitlar" / ".kayit_canli.json"
    simdi = time.time()
    yol.write_text(json.dumps({"kayit": True, "ad": "Toplantı deneme", "baslangic": simdi - 125, "son_ses": simdi - 30, "guncelleme": simdi,
                               "sorun": "", "parcalar": []}), encoding="utf-8")
    (kok / "kayitlar" / ".canli").mkdir(exist_ok=True)
    (kok / "kayitlar" / ".canli" / "Toplantı deneme.asistan.json").write_text(json.dumps({"kartlar": [{"tur": "hatirlatma", "metin": "x", "zaman": simdi}]}))
    try:
        v = istemci.get("/api/kayit/canli-durum").get_json()
        assert v["kayit"] and 120 <= v["sure"] <= 130 and v["sorun"] == "Ses gelmiyor" and len(v["kartlar"]) == 1
        yol.write_text(json.dumps({"kayit": True, "ad": "Toplantı deneme", "guncelleme": simdi - 90}), encoding="utf-8")
        assert istemci.get("/api/kayit/canli-durum").get_json() == {"kayit": False}
    finally:
        yol.unlink(missing_ok=True)


def test_pencere_toplanti_adi(site):
    """Toplantı adı yalnız gerçek toplantı penceresinden (27 Ekim: 'underbelly' ve 'StatusIndicator' toplantı adı olmuştu)."""
    f = site._pencere_toplanti_adi
    assert f("underbelly", "com.google.Chrome.helper") == ""
    assert f("Meet - ztn-gqhe-nct", "com.google.Chrome") == ""                      # çıplak Meet kodu
    assert f("Meet - Haftalık plan", "com.google.Chrome") == "Haftalık plan"
    assert f("StatusIndicator", "us.zoom.xos") == "" and f("Zoom Meeting", "us.zoom.xos") == ""
    assert f("Bütçe görüşmesi | Microsoft Teams", "com.microsoft.teams2") == "Bütçe görüşmesi"
    assert f("Sohbet", "com.microsoft.teams2") == ""
    assert site._toplanti_adi_temizle("StatusIndicator") == "" and site._toplanti_adi_temizle("Kasım planı") == "Kasım planı"


def test_taninan_katilimcida_yoksa_geri_alinir(kok):
    import meet_gelisim
    v = {"etiket": {"0": "Aysel Altıparmak", "2": "Çağla Şahin", "3": "Erkan Kırtay"}, "taninan": ["Çağla Şahin", "Erkan Kırtay"],
         "katilimcilar": ["Aysel Altıparmak", "Erkan Kırtay", "Savaş Yeşilçay", "yaren öniz"]}
    assert meet_gelisim.taninani_dogrula(v, log=lambda *_: None) == ["Çağla Şahin"]
    assert v["etiket"]["2"] == "Konuşmacı 3" and v["etiket"]["3"] == "Erkan Kırtay" and v["taninan"] == ["Erkan Kırtay"]
    v2 = {"etiket": {"0": "Çağla Şahin"}, "taninan": ["Çağla Şahin"], "katilimcilar": ["Aysel", "Erkan"]}   # liste kısa: dokunulmaz
    assert meet_gelisim.taninani_dogrula(v2, log=lambda *_: None) == [] and v2["etiket"]["0"] == "Çağla Şahin"


def test_cumle_duzeyinde_konusan_altyazidan():
    """Konuşmacı ayırma iki kişiyi aynı kümeye koymuş; altyazı her cümlenin sahibini bilir."""
    seg = [_seg(0.5, 4.8, "0", "Bütçeyi bu hafta onaylayalım kampanya pazartesi başlasın"),
           _seg(5.5, 9.8, "0", "Afiş tasarımını perşembeye kadar bitiririm"),
           _seg(10.5, 13.8, "0", "Metinleri cuma günü gönderirim tamam mı")]
    alt = [dict(a) for a in ALTYAZI]
    e = m.eslestir(seg, alt)
    n, yeni = m.konusmaci_altyazidan(seg, alt, e, {"0": "Konuşmacı 1"})
    adlar = {s["k"]: s for s in seg}
    assert n >= 1 and yeni.get("0") == "Ayşe"                            # kümenin çoğunluğu Ayşe: küme onun adını alır
    can = [k for k, ad in yeni.items() if ad == "Can"]
    assert can and seg[1]["k"] == can[0] and seg[1]["k_altyazi"] == "0"   # Can'ın cümlesi kendi (yeni) kümesine geçer
    assert m.kendini_adlandir([{"ad": "You"}, {"ad": "Ayşe"}], "Emre Deneme")[0]["ad"] == "Emre Deneme"

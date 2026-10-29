"""Gece yedeği ve geri yükleme (sanal kökte: Drive klasörü kok/Drive)."""
import json
import zipfile

from tests.conftest import transkript_yaz


def test_yedek_kapsami_dogrulama_ve_geri_yukleme(kok):
    import yedek
    import geri_yukle
    transkript_yaz(kok, "transkript_tr_yedek1", baslik="Yedek videosu")
    (kok / "transkript_tr_yedek1.jpg").write_bytes(b"\xff\xd8kapak")
    (kok / "ghost").mkdir(exist_ok=True); (kok / "ghost" / "20261025120000_ab12.json").write_text('{"veri":{"baslik":"ghost"},"segmentler":[]}', encoding="utf-8")
    (kok / "indirilenler").mkdir(exist_ok=True); (kok / "indirilenler" / ".dizin.json").write_text('{"a.mp4":{"baslik":"a"}}', encoding="utf-8")
    (kok / "indirilenler" / ".kapaklar").mkdir(exist_ok=True); (kok / "indirilenler" / ".kapaklar" / "a.jpg").write_bytes(b"\xff\xd8")
    (kok / "misafir").mkdir(exist_ok=True); (kok / "misafir" / "davetler.json").write_text('{"kisiler":[]}', encoding="utf-8")
    (kok / "content" / "x1").mkdir(parents=True, exist_ok=True); (kok / "content" / "x1" / "is.json").write_text("{}", encoding="utf-8")
    (kok / "content" / "x1" / "kaynak.mp4").write_bytes(b"0" * 100)
    (kok / "couple" / "isler" / "c1").mkdir(parents=True, exist_ok=True); (kok / "couple" / "isler" / "c1" / "is.json").write_text("{}", encoding="utf-8")
    (kok / "kayitlar").mkdir(exist_ok=True)
    (kok / "kayitlar" / "Toplantı 2026-10-25 10.00.m4a").write_bytes(b"ses" * 10)          # transkripti yok → Drive'a gitmemiş sayılır
    (kok / "kayitlar" / "Toplantı 2026-10-20 10.00.m4a").write_bytes(b"ses")
    transkript_yaz(kok, "transkript_tr_toplanti_eski", toplanti=True)
    d = json.loads((kok / "transkript_tr_toplanti_eski.json").read_text(encoding="utf-8"))
    d["veri"].update({"drive": "Toplantılar/x", "kayit": str(kok / "kayitlar" / "Toplantı 2026-10-20 10.00.m4a")})
    (kok / "transkript_tr_toplanti_eski.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (kok / "kayitlar" / "sahne_dizin").mkdir(exist_ok=True); (kok / "kayitlar" / "sahne_dizin" / "x.json").write_text("{}", encoding="utf-8")

    durum = yedek.yedekle(log=lambda m: None)
    assert durum["dogrulandi"] and durum["dosya"].endswith(".zip")
    with zipfile.ZipFile(durum["dosya"]) as z:
        adlar = set(z.namelist())
    for beklenen in ("transkript_tr_yedek1.json", "transkript_tr_yedek1.jpg", "ghost/20261025120000_ab12.json", "indirilenler/.dizin.json",
                     "indirilenler/.kapaklar/a.jpg", "misafir/davetler.json", "content/x1/is.json", "couple/isler/c1/is.json",
                     "kayitlar/Toplantı 2026-10-25 10.00.m4a", "kayitlar/sahne_dizin/x.json", "ayarlar.json", "YEDEK.txt"):
        assert beklenen in adlar, beklenen
    assert "kayitlar/Toplantı 2026-10-20 10.00.m4a" not in adlar      # Drive'a yüklenmiş toplantının sesi girmez
    assert "content/x1/kaynak.mp4" not in adlar                         # medya girmez
    assert yedek.dogrula(durum["dosya"])[0]
    assert yedek.yedekler()[0]["ad"] == durum["dosya"].split("/")[-1]

    # bozuk zip reddedilir
    bozuk = kok / "bozuk.zip"; bozuk.write_bytes(b"PK\x03\x04bozuk")
    assert not yedek.dogrula(bozuk)[0]

    # geri yükleme: boş köke; var olanın üstüne yazmaz; --uzerine-yaz eskisini kopyalar
    yeni = kok / "geri"; yeni.mkdir()
    s = geri_yukle.geri_yukle(durum["dosya"], kok=yeni, log=lambda m: None)
    assert "transkript_tr_yedek1.json" in s["yazilan"] and (yeni / "ghost" / "20261025120000_ab12.json").exists() and not s["atlanan"]
    assert json.loads((yeni / "transkript_tr_yedek1.json").read_text(encoding="utf-8"))["veri"]["baslik"] == "Yedek videosu"
    (yeni / "transkript_tr_yedek1.json").write_text("{}", encoding="utf-8")
    s2 = geri_yukle.geri_yukle(durum["dosya"], kok=yeni, yalniz=["transkript_*"], log=lambda m: None)
    assert "transkript_tr_yedek1.json" in s2["atlanan"] and (yeni / "transkript_tr_yedek1.json").read_text(encoding="utf-8") == "{}"
    s3 = geri_yukle.geri_yukle(durum["dosya"], kok=yeni, yalniz=["transkript_*"], uzerine_yaz=True, log=lambda m: None)
    assert "transkript_tr_yedek1.json" in s3["yedeklenen"] and json.loads((yeni / "transkript_tr_yedek1.json").read_text(encoding="utf-8"))["veri"]["baslik"] == "Yedek videosu"
    assert list((yeni / ".yedek").glob("geri_yukleme_*/transkript_tr_yedek1.json"))
    kuru = geri_yukle.geri_yukle(durum["dosya"], kok=kok / "kuru", kuru=True, log=lambda m: None)
    assert kuru["yazilan"] and not (kok / "kuru").exists()

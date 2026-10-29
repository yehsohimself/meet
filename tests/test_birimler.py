"""Saf işlevler: zaman, ad temizleme, kitaplık önbelleği, kilitli JSON yazımı, yerinde düzeltme, yayın bölümleri, söz tarihi."""
import json
import threading
import time
from datetime import date


def test_ortak_zaman_ve_saniye(kok):
    import ortak
    assert ortak.zaman(75) == "01:15"
    assert ortak.zaman(4530) == "1:15:30"            # bir saatin üstünde tek biçim (eskiden "75:30" ve "1:15:30" karışıktı)
    assert ortak.zaman(5, saatli=True) == "0:00:05"
    assert ortak.saniye("01:15") == 75 and ortak.saniye("1:15:30") == 4530 and ortak.saniye("75:30") == 4530 and ortak.saniye("x") is None
    assert ortak.guvenli_ad('a/b:c*d?"e<f>g|h') == "a b c d e f g h"
    assert ortak.guvenli_ad("   ") == "Video"
    assert ortak.temel_gecerli("transkript_tr_x-1") and not ortak.temel_gecerli("../x") and not ortak.temel_gecerli("")


def test_kitaplik_onbellegi_degisen_dosyayi_yeniden_okur(kok):
    import kitaplik_onbellek as ko
    from tests.conftest import transkript_yaz
    transkript_yaz(kok, "transkript_tr_onb1", baslik="Birinci")
    transkript_yaz(kok, "transkript_tr_onb2", baslik="İkinci")
    h = {k["temel"]: k["veri"] for k in ko.hepsi(klasor=kok)}
    assert h["transkript_tr_onb1"]["baslik"] == "Birinci" and h["transkript_tr_onb2"]["baslik"] == "İkinci"
    assert "segmentler" not in h["transkript_tr_onb1"]
    yol = kok / "transkript_tr_onb1.json"
    d = json.loads(yol.read_text(encoding="utf-8")); d["veri"]["baslik"] = "Değişti"
    time.sleep(0.02); yol.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert ko.veri("transkript_tr_onb1", klasor=kok)["baslik"] == "Değişti"
    yol.unlink(); (kok / "transkript_tr_onb1.txt").unlink(missing_ok=True)
    assert "transkript_tr_onb1" not in {k["temel"] for k in ko.hepsi(klasor=kok)}


def test_kayit_json_eszamanli_guncelleme_kayipsiz(kok):
    import kayit_json
    p = kok / "kilit_deneme.json"
    p.write_text(json.dumps({"veri": {}, "segmentler": [1, 2, 3]}), encoding="utf-8")
    hatalar = []

    def yaz(i):
        try:
            kayit_json.guncelle(p, lambda d: d["veri"].__setitem__(f"k{i}", i))
        except Exception as e:  # noqa: BLE001
            hatalar.append(e)
    ts = [threading.Thread(target=yaz, args=(i,)) for i in range(30)]
    [t.start() for t in ts]; [t.join() for t in ts]
    d = json.loads(p.read_text(encoding="utf-8"))
    assert not hatalar and len(d["veri"]) == 30 and d["segmentler"] == [1, 2, 3]
    assert not p.with_name(p.name + ".tmp").exists()
    assert "\n" not in p.read_text(encoding="utf-8")        # girintisiz


def test_kayit_json_false_donerse_yazmaz(kok):
    import kayit_json
    p = kok / "kilit2.json"; p.write_text('{"veri":{"a":1},"segmentler":[]}', encoding="utf-8")
    once = p.stat().st_mtime_ns
    kayit_json.guncelle(p, lambda d: False)
    assert p.stat().st_mtime_ns == once


def test_studio_duzelt_zamanlari_korur(kok):
    import studio_duzelt
    seg = [{"bas": 0, "bit": 3, "metin": "Bugün Pekşat çekimini konuştuk.", "kelimeler": [[0, .5, "Bugün"], [.5, 1.2, "Pekşat"], [1.2, 2, "çekimini"], [2, 3, "konuştuk."]]},
           {"bas": 3, "bit": 5, "metin": "Sesin yarın başlıyor.", "k": "0"}]
    r = studio_duzelt.paragraf_duzelt(seg, 0, 5, "Bugün Packshot çekimini konuştuk. Session yarın sabah başlıyor.")
    assert r["ciftler"] == [("Pekşat", "Packshot"), ("Sesin", "Session"), ("", "sabah")]
    assert seg[0]["kelimeler"][1] == [.5, 1.2, "Packshot"] and seg[0]["elle"] and seg[1]["metin"] == "Session yarın sabah başlıyor."
    assert studio_duzelt._terim_mi("Pekşat", "Packshot", False) and not studio_duzelt._terim_mi("Sesin", "Session", True)
    assert not studio_duzelt._terim_mi("ikamet", "ikame", False)


def test_yayin_bolumleri_youtube_kurali(kok):
    import yayin
    b = yayin._bolumleri_temizle([{"zaman": "00:05", "baslik": "a"}, {"zaman": "00:09", "baslik": "b"}, {"zaman": "01:00", "baslik": "c"},
                                  {"zaman": "02:00", "baslik": "d"}, {"zaman": "09:59", "baslik": "son"}], 600)
    assert [x["sn"] for x in b] == [0, 60, 120]
    assert yayin._bolumleri_temizle([{"zaman": "00:00", "baslik": "a"}, {"zaman": "01:00", "baslik": "b"}], 600) == []   # en az 3


def test_sozler_son_tarih(kok):
    import pytest
    sozler = pytest.importorskip("sozler")           # Meet modülü; yalnız Studio kurulumunda yok
    g = date(2026, 10, 22)                                   # perşembe
    assert sozler.son_tarih("yarın", g) == date(2026, 10, 23)
    assert sozler.son_tarih("cumaya kadar", g) == date(2026, 10, 23)
    assert sozler.son_tarih("pazartesi", g) == date(2026, 10, 26)
    assert sozler.son_tarih("hiçbir zaman belli değil", g) is None


def test_harfler_buyuk_harf_kurali(kok):
    import harfler
    assert harfler.ust("migros ve pepsico") == "MİGROS VE PEPSICO"
    assert harfler.ust("instagram'da") == "INSTAGRAM'DA"

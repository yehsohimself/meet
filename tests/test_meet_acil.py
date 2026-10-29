"""Acil paket (2026-10-28): toplantı sağlık özeti, Claude'da toplantılara öncelik, ses tanıma ipucunun parça bütçesi."""
import time

import pytest

import claude_yaz
import meet_gelisim as m
import terimler


def _seg(bas, bit, k="0"):
    return {"bas": bas, "bit": bit, "k": k, "metin": "x"}


def test_saglik_ses_bosluk_erken_uzanti_model(monkeypatch):
    import meet_altyazi
    bas = 1_800_000_000.0; bit = bas + 1200
    # kayıt bittikten sonra 10 dk boyunca 30 sn'de bir altyazı: toplantı sürmüş
    monkeypatch.setattr(meet_altyazi, "aralik", lambda b, e: [{"t": (bit - b) + 90 + i * 30, "ad": "A", "metin": "x"} for i in range(20)])
    veri = {"sure": 1200, "uygulama": "com.google.Chrome.helper", "altyazi": {"satir": 0}, "etiket": {"0": "Konuşmacı 1"},
            "kayit_bosluklari": [{"bas": 300, "bit": 420}], "kisaca": {"model": "gemma3:4b"}, "drive": ""}
    s = m.toplanti_saglik(veri, [_seg(0, 100)], {"kayit_baslangic": bas, "kayit_bitis": bit}, ayar={"drive": True})
    kod = {x["kod"]: x for x in s["maddeler"]}
    assert s["durum"] == "hata"
    assert {"ses", "bosluk", "erken", "uzanti", "adsiz", "model", "drive"} <= set(kod)
    assert "10 dakika daha" in kod["erken"]["metin"] or "11 dakika daha" in kod["erken"]["metin"]
    # sonraki kayıt hemen başladıysa onun altyazısı "erken bitti" sayılmaz
    s2 = m.toplanti_saglik(veri, [_seg(0, 1100)], {"kayit_baslangic": bas, "kayit_bitis": bit}, ayar={"drive": False}, baska_kayitlar=[bit + 60])
    assert "erken" not in {x["kod"] for x in s2["maddeler"]} and "ses" not in {x["kod"] for x in s2["maddeler"]}


def test_saglik_sorunsuz(monkeypatch):
    import meet_altyazi
    monkeypatch.setattr(meet_altyazi, "aralik", lambda b, e: [])
    veri = {"sure": 900, "uygulama": "com.google.Chrome.helper", "altyazi": {"satir": 120}, "etiket": {"0": "Ayşe", "1": "Can"},
            "kisaca": {"model": "claude:sonnet"}, "drive": "/x"}
    s = m.toplanti_saglik(veri, [_seg(0, 400), _seg(400, 880, "1")], {"kayit_baslangic": 1.8e9, "kayit_bitis": 1.8e9 + 900}, ayar={"drive": True})
    assert s["durum"] == "ok" and s["maddeler"] == []


def test_toplantilara_oncelik(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_yaz, "TOPLANTI_ISARETI", tmp_path / ".toplanti_claude")
    monkeypatch.setattr(claude_yaz, "KLASOR", tmp_path)          # gerçek kayıt sürerken (.kayit_canli.json) test şaşmasın
    monkeypatch.setattr(claude_yaz, "misafir", lambda: None)
    monkeypatch.setattr(claude_yaz, "sinir_durumu", lambda: None)
    monkeypatch.setattr(claude_yaz, "arka_plan_uygun", lambda: True)
    # toplantı içerikli çağrı işaret bırakır, kendisi beklemez
    with claude_yaz.toplanti():
        claude_yaz._oncelik("kisaca")
    assert claude_yaz.TOPLANTI_ISARETI.exists() and claude_yaz.toplanti_suruyor()
    uyku = []

    def sahte_uyku(sn):
        uyku.append(sn); claude_yaz.TOPLANTI_ISARETI.unlink()       # toplantı işi bitti: bekleyen devam eder
    monkeypatch.setattr(claude_yaz.time, "sleep", sahte_uyku)
    claude_yaz._oncelik("X taslakları")
    assert uyku == [20]
    claude_yaz.TOPLANTI_ISARETI.touch(); uyku.clear()
    claude_yaz._oncelik("Özet")                                      # arka plan işi değil: beklemez
    assert uyku == []
    monkeypatch.setattr(claude_yaz, "_istekten_mi", lambda: True)    # kullanıcının elle başlattığı Ghost işi: beklemez
    claude_yaz._oncelik("karisim")
    assert uyku == []


def test_ipucu_parca_butcesi(monkeypatch):
    monkeypatch.setattr(terimler, "ayar_sozlugu", lambda: ([], [f"Marka{i} Holding" for i in range(40)]))
    ad = ["Ayşe Yılmaz", "Can Demir", "Deniz Ak", "Ece Su", "Fırat Ok", "Gül Tan", "Hakan Er", "İpek Ay", "Jale Uz", "Kerem Öz"]
    p = terimler.ipucu_yap("tr", ad)
    assert terimler._parca_sayisi(p) <= terimler.IPUCU_BUTCE
    assert p.startswith("Sohbet ediyoruz. Türkçe konuşuyoruz ama session, creative")   # çerçeve ve en sık terimler kesilmez
    assert "Kerem Öz" not in p and "İpek Ay" in p                                       # en çok 8 kişi adı

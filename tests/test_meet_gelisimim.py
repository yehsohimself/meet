"""Meet 'Gelişiminiz' kartı: kullanıcının etiketi, haftalık pay cümlesi, tema süzgeci (Claude sahte)."""
import meet_gelisim as m


def test_benim_etiket_yalniz_emin_olunan():
    olcu = {"Ayşe Kaya": {}, "Emre": {}, "Konuşmacı 2": {}}
    assert m._benim_etiket({}, olcu, "Ayşe Kaya") == "Ayşe Kaya"
    assert m._benim_etiket({}, olcu, "Ayşe Demir") is None                      # yalnız ilk ad tutması yetmez
    assert m._benim_etiket({"danisman": {"siz": "Konuşmacı 2", "emin": True}}, olcu, "X Y") == "Konuşmacı 2"
    assert m._benim_etiket({"danisman": {"siz": "Konuşmacı 2", "emin": False}}, olcu, "X Y") is None


def test_pay_cumlesi():
    H = [{"pay": 30, "beklenen": 25}, {"pay": 10, "beklenen": 20}]
    c = m._pay_cumlesi(H)
    assert "%10" in c and "%20" in c and "ortalaması %30" in c
    assert "yakın" in m._pay_cumlesi([{"pay": 18, "beklenen": 20}])
    assert m._pay_cumlesi([]) == ""


def test_temalar_tek_toplantiyi_ve_uydurma_kaynagi_atar(monkeypatch):
    import claude_yaz
    D = [{"i": 1, "temel": "a", "grup": "a", "baslik": "A", "tarih": "2026-10-20", "emin": True, "ders": "Tarih ver: x", "aksiyonlar": []},
         {"i": 2, "temel": "b", "grup": "b", "baslik": "B", "tarih": "2026-10-22", "emin": True, "ders": "Tarihle kapat: y", "aksiyonlar": []},
         {"i": 3, "temel": "b", "grup": "b", "baslik": "B", "tarih": "2026-10-22", "emin": True, "ders": "Sınır çiz: z", "aksiyonlar": []}]
    monkeypatch.setattr(claude_yaz, "hazir", lambda *a, **k: True)
    monkeypatch.setattr(claude_yaz, "sor_json", lambda *a, **k: {"temalar": [
        {"tema": "Teslim tarihini net söyleyin", "aciklama": "a", "kaynaklar": [1, 2], "ilerleme": "suruyor"},
        {"tema": "Sınırı çizin", "aciklama": "b", "kaynaklar": [3, 99], "ilerleme": "yeni"}]})
    T = m.temalari_kur(D, log=lambda *_: None)
    assert [t["tema"] for t in T] == ["Teslim tarihini net söyleyin"]
    assert T[0]["son"] == "2026-10-22" and len(T[0]["kaynaklar"]) == 2


def test_ayni_toplantinin_parcalari_tek_sayilir(monkeypatch):
    import claude_yaz
    D = [{"i": 1, "temel": "a1", "grup": "g", "baslik": "A", "tarih": "2026-10-16", "emin": True, "ders": "Sınır çiz: x", "aksiyonlar": []},
         {"i": 2, "temel": "a2", "grup": "g", "baslik": "A", "tarih": "2026-10-16", "emin": True, "ders": "Kapsamı netleştir: y", "aksiyonlar": []},
         {"i": 3, "temel": "b", "grup": "h", "baslik": "B", "tarih": "2026-10-21", "emin": True, "ders": "Ekstrayı adıyla koy: z", "aksiyonlar": []}]
    monkeypatch.setattr(claude_yaz, "hazir", lambda *a, **k: True)
    monkeypatch.setattr(claude_yaz, "sor_json", lambda *a, **k: {"temalar": [
        {"tema": "Kapsamı baştan çizin", "aciklama": "a", "kaynaklar": [1, 2, 3], "ilerleme": "suruyor"},
        {"tema": "Yalnız parçalar", "aciklama": "b", "kaynaklar": [1, 2], "ilerleme": "yeni"}]})
    T = m.temalari_kur(D, log=lambda *_: None)
    assert [t["tema"] for t in T] == ["Kapsamı baştan çizin"] and len(T[0]["kaynaklar"]) == 2


def test_video_sesi_toplantida_kullanilmaz(tmp_path, monkeypatch):
    """2026-10-27: YouTube videosundan öğrenilen ses ('Umut') toplantıda başka birine verilmişti."""
    import sesler
    monkeypatch.setattr(sesler, "DOSYA", tmp_path / "sesler.json")
    v = [1.0] + [0.0] * 191
    sesler.ogren({"etiket": {"0": "Videodaki"}, "sesler": {"0": v}})                                    # video: toplantı sayılmaz
    assert sesler.tani({"5": v}) == {"5": "Videodaki"}
    assert sesler.tani({"5": v}, toplanti=True) == {}
    sesler.ogren({"toplanti": True, "taninan": ["Videodaki"], "etiket": {"0": "Videodaki"}, "sesler": {"0": v}})   # sesten tanındı: yine sayılmaz
    assert sesler.tani({"5": v}, toplanti=True) == {}
    sesler.ogren({"toplanti": True, "etiket": {"0": "Videodaki"}, "sesler": {"0": v}})                  # toplantıda elle verildi
    assert sesler.tani({"5": v}, toplanti=True) == {"5": "Videodaki"}

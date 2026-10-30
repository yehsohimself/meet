"""Sunucu uçları (Flask test istemcisi, sanal kök): güvenlik katmanı, kabuk/sıkıştırma, hata yanıtları, yerinde düzeltme, davetli kapısı."""
import gzip
import json
from pathlib import Path

import pytest

from tests.conftest import transkript_yaz

misafir = pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "sunucu" / "22_misafir.py").exists(), reason="Davetli kapısı bu kurulumda yok (ör. Ghost deposu)")
studio = pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "sunucu" / "21_studio.py").exists(), reason="Studio bu kurulumda yok (ör. Meet deposu)")

J = {"Content-Type": "application/json"}


def gov(r):
    d = r.get_data()
    if r.headers.get("Content-Encoding") == "gzip":
        d = gzip.decompress(d)
    return d


def jj(r):
    return json.loads(gov(r))


# ---------------------------------------------------------------- güvenlik katmanı (24)
def test_ayarlar_yanitinda_sir_yok(istemci, kok):
    import gizli
    gizli.koy("asana_token", "2/1234/5678:abcdef0123456789abcdef0123456789")
    r = istemci.get("/api/ayarlar"); d = jj(r)
    assert r.status_code == 200 and not any(k.endswith(("_token", "_anahtar", "_pin")) for k in d) and "2/1234" not in gov(r).decode()
    r = istemci.post("/api/ayarlar", data=json.dumps({"ozet": False}), headers=J); d = jj(r)
    assert r.status_code == 200 and not any(k.endswith(("_token", "_anahtar", "_pin")) for k in d) and d.get("asana_bagli") is True
    assert gizli.al("asana_token").startswith("2/1234")        # dokunulmadı


def test_ayarlar_tur_dogrulama(istemci):
    assert istemci.post("/api/ayarlar", data=json.dumps({"asana_token": 123}), headers=J).status_code == 400
    assert istemci.post("/api/ayarlar", data=json.dumps({"musteriler": 123}), headers=J).status_code == 400
    assert istemci.post("/api/ayarlar", data=json.dumps({"drive_yol": "/etc"}), headers=J).status_code == 400
    assert istemci.post("/api/ayarlar", data="bozuk", headers=J).status_code == 400


def test_api_hatasi_json_doner(istemci, kok):
    transkript_yaz(kok, "transkript_tr_hata")
    r = istemci.post("/api/segment/transkript_tr_hata", data=json.dumps({"bas": "x", "bit": "y", "ad": "a"}), headers=J)
    assert r.status_code == 400 and "hata" in jj(r)
    assert istemci.get("/api/yok_boyle_bir_uc").status_code in (404, 405)


def test_yol_kacisi_reddedilir(istemci):
    for yol in ("/indir/..%2Fayarlar.json", "/kapak/../ayarlar.json", "/medya/..%2Fx", "/zip/..%2F.zip", "/kare/..%2F..%2F/k_1.jpg", "/api/metin/%C3%A7%C3%B6p"):
        assert istemci.get(yol).status_code in (400, 404, 405), yol


def test_ana_sayfa_kabuk_ve_sikistirma(istemci, kok):
    r = istemci.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("Content-Encoding") == "gzip"
    html = gov(r).decode("utf-8")
    assert "<style" not in html and 'href="/static/derlenmis/index.' in html and 'src="/static/derlenmis/index.' in html
    assert len(html) < 120_000                                # kabuk; eskiden 777 KB
    js = html.split('src="/static/derlenmis/')[1].split('"')[0]
    r2 = istemci.get("/static/derlenmis/" + js, headers={"Accept-Encoding": "gzip"})
    assert r2.status_code == 200 and r2.headers.get("Content-Encoding") == "gzip" and "immutable" in r2.headers.get("Cache-Control", "")
    assert istemci.get("/api/gecmis").status_code == 200


def test_yerel_yazma_uclari_disaridan_kapali(istemci, site):
    r = istemci.post("/api/uzanti/durum", data="{}", headers=J, environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert r.status_code == 403
    if any(r_.rule == "/api/uzanti/durum" for r_ in site.app.url_map.iter_rules()):   # uç Meet'le gelir; yalnız Studio kurulumunda yok
        assert istemci.get("/api/uzanti/durum", environ_base={"REMOTE_ADDR": "192.168.1.50"}).status_code == 200


# ---------------------------------------------------------------- Studio: yerinde düzeltme, kurgu, zip
@studio
def test_metin_duzelt_ve_geri_al(istemci, kok):
    transkript_yaz(kok, "transkript_tr_duzelt")
    p = jj(istemci.get("/api/metin/transkript_tr_duzelt"))["paragraflar"][0]
    r = istemci.post("/api/metin-duzelt/transkript_tr_duzelt", data=json.dumps({"bas": p["bas"], "bit": p["bit"], "metin": p["metin"].replace("Merhaba,", "Selam,")}), headers=J)
    assert r.status_code == 200 and jj(r)["degisen"] == 1
    assert "Selam," in (kok / "transkript_tr_duzelt.txt").read_text(encoding="utf-8")
    assert istemci.post("/api/geri-al/transkript_tr_duzelt").status_code == 200
    assert "Merhaba," in jj(istemci.get("/api/metin/transkript_tr_duzelt"))["paragraflar"][0]["metin"]


@studio
def test_kurgu_kaydet_ve_zip(istemci, kok):
    transkript_yaz(kok, "transkript_tr_kurgu")
    r = istemci.post("/api/kurgu/transkript_tr_kurgu", data=json.dumps({"ad": "Deneme", "tut": [[4.5, 9.0], [0, 4.0]], "sira": [1, 0, 2], "cikan": [2]}), headers=J)
    assert r.status_code == 200 and jj(r)["kurgular"][0]["ad"] == "Deneme"
    assert istemci.post("/api/kurgu/transkript_tr_kurgu", data=json.dumps({"tut": [["a", "b"]]}), headers=J).status_code == 400
    z = istemci.get("/zip/transkript_tr_kurgu.zip")
    assert z.status_code == 200 and z.data[:2] == b"PK"


# ---------------------------------------------------------------- davetli kapısı (8770)
M = "http://localhost:8770/"


def davet_olustur(istemci, ad="Arkadaş"):
    r = istemci.post("/api/davetler", data=json.dumps({"ad": ad}), headers=J)
    assert r.status_code == 200, gov(r)
    return jj(r)["kisi"]["id"]


def token_bul(kok, gid):
    return next(k["token"] for k in json.loads((kok / "misafir" / "davetler.json").read_text(encoding="utf-8"))["kisiler"] if k["id"] == gid)


@misafir
def test_davetsiz_kapi_kapali(misafir_istemci):
    assert misafir_istemci.get("/", base_url=M).status_code == 403
    assert misafir_istemci.get("/api/gecmis", base_url=M).status_code == 401
    assert misafir_istemci.get("/api/davetler", base_url=M).status_code == 401
    assert misafir_istemci.get("/d/yanlis_kod_1234567890abcdefghij", base_url=M).status_code == 403


@misafir
def test_davetli_yalnizca_kendi_kayitlarini_gorur(istemci, misafir_istemci, kok):
    transkript_yaz(kok, "transkript_tr_sahip", baslik="Sahibin videosu")
    gid = davet_olustur(istemci, "Kontrol")
    tok = token_bul(kok, gid)
    transkript_yaz(kok, "transkript_tr_misafirin", baslik="Misafirin videosu", misafir=gid)
    r = misafir_istemci.get(f"/d/{tok}", base_url=M)
    assert r.status_code == 302
    sayfa = misafir_istemci.get("/", base_url=M)
    assert sayfa.status_code == 200 and b'data-misafir="1"' in gov(sayfa)
    L = jj(misafir_istemci.get("/api/gecmis", base_url=M))
    assert [x["temel"] for x in L] == ["transkript_tr_misafirin"]
    assert misafir_istemci.get("/api/metin/transkript_tr_sahip", base_url=M).status_code == 404
    assert misafir_istemci.get("/api/metin/transkript_tr_misafirin", base_url=M).status_code == 200
    assert misafir_istemci.get("/indir/transkript_tr_sahip.docx", base_url=M).status_code == 404
    assert misafir_istemci.get("/api/sistem-durum", base_url=M).status_code == 403
    assert misafir_istemci.get("/static/index.html", base_url=M).status_code == 403       # ham sayfa dosyaları davetliye kapalı
    # sahip misafirin kaydını görmez
    assert "transkript_tr_misafirin" not in [x["temel"] for x in jj(istemci.get("/api/gecmis"))]
    # yerel dosya yolu ve iç adres reddedilir
    r = misafir_istemci.post("/api/baslat", base_url=M, data=json.dumps({"link": str(kok / "ayarlar.json")}), headers=J)
    assert r.status_code == 403
    r = misafir_istemci.post("/api/baslat", base_url=M, data=json.dumps({"link": "http://127.0.0.1:8766/api/gecmis"}), headers=J)
    assert r.status_code == 400
    assert misafir_istemci.get("/api/onizle?link=http://localhost:8765/", base_url=M).status_code == 400
    # sayfada sahibin müşteri adı geçmez (Meet temizliği)
    if (kok / "sunucu" / "23_misafir_meet.py").exists():          # Meet kuruluysa sahibin müşteri adları davetli sayfasından silinir
        assert b"Ajans Test" not in gov(sayfa)


@misafir
def test_davet_oran_siniri(misafir_istemci):
    kodlar = [misafir_istemci.get("/d/yanlis_kod_1234567890abcdefghij", base_url=M, environ_base={"REMOTE_ADDR": "10.9.9.9"}).status_code for _ in range(25)]
    assert kodlar[0] == 403 and kodlar[-1] == 429


def test_kapak_adresi_yalniz_http(kok):
    import re
    src = (kok / "sunucu" / "03_video_isleri.py").read_text(encoding="utf-8")
    m = re.search(r"\ndef _kapak_indir_hedef\(hedef, url\):.*?(?=\n\n\ndef |\n\n\n@)", src, re.S)
    ns = {"re": re, "urllib": __import__("urllib.request"), "Path": __import__("pathlib").Path}
    exec(m.group(0), ns)
    h = kok / "kapak_deneme.jpg"
    ns["_kapak_indir_hedef"](h, "file:///etc/hosts")
    assert not h.exists()


def test_paylasilabilir_sayfa(istemci, kok):
    """2026-10-27: tek dosyalık HTML; başlık, metin ve YouTube zaman bağlantıları; kaçış yapılır."""
    transkript_yaz(kok, "transkript_tr_sayfa", baslik="Borç <script>alert(1)</script>")
    r = istemci.get("/disa/transkript_tr_sayfa.html")
    assert r.status_code == 200 and r.headers["Content-Type"].startswith("text/html")
    h = r.get_data(as_text=True)
    assert "Kredi kartı borcu" in h and "youtu.be/abc12345678?t=" in h and "<script>alert(1)" not in h
    assert "attachment" in istemci.get("/disa/transkript_tr_sayfa.html?indir=1").headers.get("Content-Disposition", "")


def test_ozet_onceki_surume_don(istemci, kok):
    """Özet geçmişinden bir sürüme dönülür; şimdiki özet geçmişe girer."""
    import json
    transkript_yaz(kok, "transkript_tr_ozetg")
    yol = kok / "transkript_tr_ozetg.json"
    d = json.loads(yol.read_text(encoding="utf-8"))
    d["veri"]["ozet"] = {"ozet": "Yeni özet.", "maddeler": []}
    d["veri"]["ozet_gecmis"] = [{"ozet": "Eski özet.", "maddeler": [], "bicim": "kisa"}]
    yol.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = istemci.post("/api/ozet/transkript_tr_ozetg/geri", json={"i": 0})
    assert r.status_code == 200 and r.get_json()["ozet"]["ozet"] == "Eski özet."
    d = json.loads(yol.read_text(encoding="utf-8"))
    assert d["veri"]["ozet"]["ozet"] == "Eski özet." and d["veri"]["ozet_gecmis"][0]["ozet"] == "Yeni özet."
    assert istemci.post("/api/ozet/transkript_tr_ozetg/geri", json={"i": 5}).status_code == 404


@studio
def test_kurulum_denetimi(istemci):
    j = istemci.get("/api/kurulum").get_json()
    assert {a["kod"] for a in j["adimlar"]} >= {"ffmpeg", "model", "yazi", "disk"} and "hazir" in j


@misafir
def test_davetli_kurulum_denetimini_gormez(misafir_istemci):
    assert misafir_istemci.get("/api/kurulum", base_url=M).status_code in (401, 403)


@misafir
def test_sikistirma_suzgeclerden_sonra_calisir(istemci, misafir_istemci, kok):
    """Tarayıcı gzip ister: sıkıştırma bütün süzgeçlerden SONRA olmalı (2026-10-29: önce çalışıyor, davetli listesi süzülmüyordu)."""
    import gizli
    Z = {"Accept-Encoding": "gzip"}
    gizli.koy("asana_token", "2/1234/5678:abcdef0123456789abcdef0123456789")
    for r in (istemci.get("/api/ayarlar", headers=Z), istemci.post("/api/ayarlar", data=json.dumps({"ozet": False}), headers={**J, **Z})):
        d = jj(r)
        assert r.status_code == 200 and not any(k.endswith(("_token", "_anahtar", "_pin")) or k == "takvim_ics" for k in d)
    for i in range(14):
        transkript_yaz(kok, f"transkript_tr_sahip_{i}", baslik=f"Sahibin uzunca bir video başlığı {i}")
    assert istemci.get("/api/gecmis", headers=Z).headers.get("Content-Encoding") == "gzip"     # liste gerçekten sıkıştırılacak kadar uzun
    gid = davet_olustur(istemci, "Sikistirma")
    transkript_yaz(kok, "transkript_tr_misafirin", baslik="Misafirin videosu", misafir=gid)
    assert misafir_istemci.get(f"/d/{token_bul(kok, gid)}", base_url=M).status_code == 302
    L = jj(misafir_istemci.get("/api/gecmis", base_url=M, headers=Z))
    assert [x["temel"] for x in L] == ["transkript_tr_misafirin"]
    assert "transkript_tr_misafirin" not in [x["temel"] for x in jj(istemci.get("/api/gecmis", headers=Z))]
    d = jj(istemci.get("/api/davetler", headers=Z))
    assert isinstance(d.get("kisiler"), list) and d["kisiler"]

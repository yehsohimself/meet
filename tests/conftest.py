"""Test iskeleti (2026-10-25 backend gözden geçirmesi).

Sanal kök: proje kodu (py, sunucu/, static/ küçük dosyalar) geçici bir klasöre KOPYALANIR (symlink olmaz: modüller KLASOR'u `Path(__file__)`'dan türetir),
içine boş veri klasörleri ve kapalı ayarlar yazılır. Böylece testler gerçek ayarlara, profile, Anahtar Zinciri'ne ve kitaplığa hiç dokunmaz
(25 Ekim'de canlı siteye atılan bozuk-girdi testi gerçek Asana belirtecini silmişti).

Site, sanal kökteki site.py'den `vh_site` adıyla yüklenir (Python'un kendi `site` modülüyle çakışmasın); Flask test istemcisiyle konuşulur.
Dış dünya kapalı: Anahtar Zinciri sahte sözlük, Claude programı yok, subprocess/requests çağrıları gerçek (yalnız ffmpeg gibi yerel araçlar).

Çalıştırma: .venv/bin/python -m pytest tests -q   (duman_testi.py `testler` kipi ve yeniden_baslat.py de çalıştırır)
"""
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

GERCEK_KOK = Path(__file__).resolve().parent.parent
KOPYALANACAK_STATIC = ("index.html", "content.html", "couple.html", "ghost_tek.html", "studio_ek.js", "studio_ek.css", "meet_ek.js", "meet_ek.css",
                       "misafir.js", "misafir_meet.js", "manifest.webmanifest", "couple.webmanifest", "pt.html", "pt-sw.js", "sahip_uzak.js")


@pytest.fixture(scope="session")
def kok(tmp_path_factory):
    k = tmp_path_factory.mktemp("vh")
    for py in GERCEK_KOK.glob("*.py"):
        shutil.copy(py, k / py.name)
    shutil.copytree(GERCEK_KOK / "sunucu", k / "sunucu", ignore=shutil.ignore_patterns("__pycache__"))
    (k / "static").mkdir()
    for ad in KOPYALANACAK_STATIC:
        if (GERCEK_KOK / "static" / ad).exists():
            shutil.copy(GERCEK_KOK / "static" / ad, k / "static" / ad)
    for alt in ("logo", "logolar", "ikon"):
        if (GERCEK_KOK / "static" / alt).exists():
            shutil.copytree(GERCEK_KOK / "static" / alt, k / "static" / alt)
    for alt in ("atolye",):
        (k / alt).mkdir()
        for ad in ("markalar.ornek.json",):                        # kullanıcının markalar.json'u teste girmez; şablon yeter
            if (GERCEK_KOK / alt / ad).exists():
                shutil.copy(GERCEK_KOK / alt / ad, k / alt / ad)
    for d in ("profil", "kayitlar", "misafir", "indirilenler", "yuklemeler", "ghost", "kareler", ".onbellek", "reports"):
        (k / d).mkdir(exist_ok=True)
    (k / "ayarlar.json").write_text(json.dumps({
        "ozet": False, "ag_paylasimi": False, "drive": False, "oto_kayit": False, "claude": False, "atolye_bakim": False, "sahne_dizini": False,
        "yayin_oto": False, "ghost_kesif": False, "ghost_bildirim": False, "soz_bildirim": False, "on_brifing": False, "notlar_gonder": False,
        "canli_asistan": False, "toplanti_kapisi": False, "danisman": False, "haftalik_eposta": False, "takvim_ics": "",
        "musteriler": ["Ajans Test", "Marka Test"], "benim_adim": "Test Kişi", "benim_epostalar": ["test@example.com"],
        "drive_yol": str(k / "Drive"), "misafir_kisi": 5}, ensure_ascii=False), encoding="utf-8")
    (k / "Drive").mkdir()
    os.environ["VH_TEST"] = "1"
    sys.path.insert(0, str(k))
    for m in [m for m in sys.modules if m in ("gizli", "claude_yaz", "ortak", "kayit_json", "kitaplik_onbellek", "transkript")]:
        del sys.modules[m]
    import gizli                                           # Anahtar Zinciri yerine sözlük
    _sahte = {}
    gizli.al = lambda ad: _sahte.get(ad, "")
    gizli.koy = lambda ad, deger: (_sahte.__setitem__(ad, deger) or True)
    import claude_yaz                                      # Claude programı yok
    claude_yaz.program = lambda: None
    claude_yaz.durum = lambda zorla=False: {"program": False, "giris": False, "kullanim": False}
    return k


@pytest.fixture(scope="session")
def site(kok):
    spec = importlib.util.spec_from_file_location("vh_site", kok / "site.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vh_site"] = mod
    spec.loader.exec_module(mod)
    mod.app.config["TESTING"] = True
    return mod


@pytest.fixture
def istemci(site):
    return site.app.test_client()


@pytest.fixture
def misafir_istemci(site):
    return site.app.test_client()


def transkript_yaz(kok, temel, baslik="Deneme videosu", link="https://www.youtube.com/watch?v=abc12345678", misafir="", toplanti=False):
    """Sanal köke küçük bir transkript kaydı (JSON + txt/docx/srt) yazar; döner: veri."""
    import transkript
    veri = {"link": link, "baslik": baslik, "kanal": "Test Kanalı", "sure": 12.0, "kapak": "", "platform": "YouTube", "video_id": "abc12345678",
            "dil": "tr", "diller": ["tr"], "kaynak": "sesten çözüm", "model": "turbo", "olusturma": 1792900000.0, "etiket": {"0": "Konuşmacı 1"},
            "uyarilar": [], "sesler": {}, "taninan": [], "ad_onerileri": []}
    if misafir:
        veri["misafir"] = misafir
    if toplanti:
        veri["toplanti"] = True
    seg = [{"bas": 0.0, "bit": 4.0, "k": "0", "metin": "Merhaba, bugün borç konusunu konuşacağız.",
            "kelimeler": [[0.0, 0.6, "Merhaba,"], [0.6, 1.2, "bugün"], [1.2, 2.0, "borç"], [2.0, 2.8, "konusunu"], [2.8, 4.0, "konuşacağız."]]},
           {"bas": 4.5, "bit": 9.0, "k": "0", "metin": "Kredi kartı borcu en pahalı borçtur."},
           {"bas": 9.5, "bit": 12.0, "k": "0", "metin": "Teşekkürler."}]
    eski = transkript.ERTELE_SN
    transkript.ERTELE_SN = 0.0
    try:
        transkript.ciktilari_yaz(kok / temel, veri, seg)
    finally:
        transkript.ERTELE_SN = eski
    return veri

"""yedek.py - Video Hub gece yedeği: kişisel veri + ayarlar + kodun git paketi → Drive'daki "Video Hub Yedek" klasörüne tek zip.

Neden (2026-10-18 teknik değerlendirme): sürüm takibi ve otomatik yedek yoktu; disk dolduğunda profil dosyası yazılamamıştı.
Ne girer: transkript JSON'ları (asıl veri; txt/docx/srt bunlardan yeniden üretilir), ayarlar.json, sesler.json, takip.json, profil/,
atolye/ (kadro, markalar, bilgi kartları, çalışmalar, örnekler, geri bildirim), markalar/, ozetler/*.md, kayitlar/*.json (kayıt üst
bilgisi; ses dosyaları her toplantıda zaten Drive'a gidiyor), .isler.json ve kodun `git bundle`'ı. Videolar ve modeller girmez.
Saklama: son 10 yedek. Site `_yedek_dongu` her gece 03.00'ten sonra bir kez çalıştırır; elle: `python yedek.py`.

2026-10-25 (backend gözden geçirmesi, kullanıcı istedi): kapsam genişledi — ghost/*.json, indirilenler/.dizin.json + .kapaklar, kapak jpg/png'leri,
misafir/, content/ ve couple/ JSON'ları, kayitlar/ altındaki bütün json/jsonl (alt klasörler dahil), Drive'a GİTMEMİŞ toplantı sesleri
(kayitlar/Toplantı *.m4a: transkripti Drive'a yüklenmemiş ya da transkripti olmayanlar; .mik.m4a eşi de). Zip yazıldıktan sonra `testzip` ve
`git bundle verify` ile doğrulanır; geçmezse silinir ve bildirilir (`durum["dogrulandi"]`). Sırlar (Anahtar Zinciri) Drive'a GİTMEZ; yalnız bu Mac'te
`.yedek/sirlar.json` (0600) olarak tutulur (bir ayar yanlışlıkla ezilirse geri alınabilsin; 25 Ekim'de Asana belirteci böyle kaybolmuştu).
Geri yükleme: `python geri_yukle.py [zip] [--liste] [--kuru] [--yalniz desen]` (var olan dosyaların üstüne yazmaz; yazacaksa önce .yedek/'e kopyalar).
"""
import json
import subprocess
import time
import zipfile
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
DURUM = KLASOR / "kayitlar" / ".son_yedek.json"
SAKLA = 10


def hedef_klasor():
    try:
        a = json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        a = {}
    kok = Path(a.get("drive_yol") or "~/Desktop/Drive").expanduser()
    return (kok if kok.is_dir() else KLASOR / ".yedek") / "Video Hub Yedek"


EN_BUYUK_MB = 200          # tek dosya sınırı (yanlışlıkla devasa bir dosya zip'e girmesin)


def _drive_gitmemis_sesler(k):
    """kayitlar/Toplantı *.m4a: transkripti Drive'a yüklenmemiş ya da hiç transkripti olmayan kayıtlar (+ .mik.m4a eşleri)."""
    try:
        import kitaplik_onbellek
        kayitlar = kitaplik_onbellek.hepsi(klasor=k)
    except Exception:  # noqa: BLE001
        kayitlar = []
    yuklenen = set()
    for x in kayitlar:
        v = x["veri"]
        if v.get("toplanti") and v.get("drive") and v.get("kayit"):
            yuklenen.add(Path(str(v["kayit"])).name)
    out = []
    for m in (k / "kayitlar").glob("Toplantı *.m4a"):
        ana = m.name.replace(".mik.m4a", ".m4a")
        if ana not in yuklenen and m.stat().st_size < EN_BUYUK_MB * 1e6:
            out.append(m)
    return out


def dosyalar():
    k = KLASOR
    L = list(k.glob("transkript_*.json")) + list(k.glob("transkript_*.jpg")) + list(k.glob("transkript_*.png"))   # kapaklar ve kapak taslakları
    L += [k / f for f in ("ayarlar.json", "sesler.json", "takip.json", ".isler.json", "CLAUDE.md", "NOTLAR_OZEL.md", ".sizinti_izin.txt", ".sizinti_ek.txt") if (k / f).exists()]   # çalışma notları git dışı (2026-10-25)
    for kl, desen in (("profil", "*"), ("atolye", "*.json"), ("atolye", "*.jsonl"), ("atolye/bilgi", "*.json"), ("atolye/calismalar", "*.json"),
                      ("markalar", "**/*.json"), ("ozetler", "*.md"), ("kayitlar", "**/*.json"), ("kayitlar", "**/*.jsonl"), ("radar", "*.md"),
                      ("pt", "**/*.json"), ("ghost", "*.json"), ("reports", "*.md"), ("indirilenler", ".dizin.json"), ("indirilenler/.kapaklar", "*.jpg"),
                      ("misafir", "*.json"), ("content", "**/*.json"), ("couple", "**/*.json"), ("reklam_arsivi", "arsiv.json")):
        L += [p for p in (k / kl).glob(desen) if p.is_file() and p.stat().st_size < EN_BUYUK_MB * 1e6 and ".canli" not in p.parts]
    L += _drive_gitmemis_sesler(k)
    return sorted(set(L))


def _sirlari_sakla(k, log):
    """Anahtar Zinciri'ndeki sırları yalnız bu Mac'te .yedek/sirlar.json (0600) olarak tutar; Drive'a GİTMEZ."""
    try:
        import gizli
        import os
        d = {ad: gizli.al(ad) for ad in gizli.SIRLAR}
        d = {ad: v for ad, v in d.items() if v}
        if not d:
            return
        hedef = k / ".yedek" / "sirlar.json"; hedef.parent.mkdir(exist_ok=True)
        hedef.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8"); os.chmod(hedef, 0o600)
    except Exception as e:  # noqa: BLE001
        log(f"Sırlar yerel yedeğe yazılamadı: {e}")


def dogrula(zip_yolu, log=print):
    """Zip bütünlüğü (testzip) ve kod paketi (git bundle verify). Döner: (True, "") ya da (False, neden)."""
    try:
        with zipfile.ZipFile(zip_yolu) as z:
            bozuk = z.testzip()
            if bozuk:
                return False, f"bozuk üye: {bozuk}"
            if ".kod.bundle" in z.namelist():
                import tempfile
                with tempfile.TemporaryDirectory() as t:
                    z.extract(".kod.bundle", t)
                    r = subprocess.run(["git", "bundle", "verify", str(Path(t) / ".kod.bundle")], capture_output=True, text=True, timeout=120)
                    if r.returncode != 0:
                        return False, "kod paketi doğrulanamadı: " + (r.stderr or r.stdout).strip()[:160]
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:160]
    return True, ""


def yedekle(log=print):
    hedef = hedef_klasor(); hedef.mkdir(parents=True, exist_ok=True)
    ad = hedef / f"Video Hub {time.strftime('%Y-%m-%d %H.%M')}.zip"
    gecici = ad.with_suffix(".zip.yaziliyor")
    paket = KLASOR / ".kod.bundle"
    try:
        subprocess.run(["git", "-C", str(KLASOR), "bundle", "create", str(paket), "--all"], capture_output=True, timeout=120)
    except Exception:  # noqa: BLE001
        pass
    L = dosyalar() + ([paket] if paket.exists() else [])
    with zipfile.ZipFile(gecici, "w", zipfile.ZIP_DEFLATED) as z:
        for p in L:
            try:
                z.write(p, p.relative_to(KLASOR))
            except OSError as e:
                log(f"Yedeğe alınamadı: {p.name} ({e})")
        z.writestr("YEDEK.txt", f"Video Hub yedeği {time.strftime('%Y-%m-%d %H:%M')}\n{len(L)} dosya\nGeri yükleme: python geri_yukle.py \"{ad.name}\"\n")
    paket.unlink(missing_ok=True)
    tamam, neden = dogrula(gecici, log)
    if not tamam:
        gecici.unlink(missing_ok=True)
        log(f"Yedek DOĞRULANAMADI, silindi: {neden}")
        durum = {"zaman": time.time(), "dosya": "", "boyut_mb": 0, "adet": len(L), "dogrulandi": False, "hata": neden}
        DURUM.parent.mkdir(exist_ok=True); DURUM.write_text(json.dumps(durum, ensure_ascii=False), encoding="utf-8")
        return durum
    gecici.rename(ad)
    _sirlari_sakla(KLASOR, log)
    eskiler = sorted(hedef.glob("Video Hub *.zip"))[:-SAKLA]
    for e in eskiler:
        e.unlink(missing_ok=True)
    sesler = sum(1 for p in L if p.suffix == ".m4a")
    durum = {"zaman": time.time(), "dosya": str(ad), "boyut_mb": round(ad.stat().st_size / 1e6, 1), "adet": len(L), "dogrulandi": True, "ses": sesler}
    DURUM.parent.mkdir(exist_ok=True)
    DURUM.write_text(json.dumps(durum, ensure_ascii=False), encoding="utf-8")
    log(f"Yedek: {ad.name} ({durum['boyut_mb']} MB, {len(L)} dosya)")
    return durum


def son():
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def yedekler():
    """Drive'daki yedekler (yeniden eskiye): ad, boyut, zaman."""
    h = hedef_klasor()
    out = []
    for z in sorted(h.glob("Video Hub *.zip"), reverse=True) if h.exists() else []:
        out.append({"ad": z.name, "yol": str(z), "boyut_mb": round(z.stat().st_size / 1e6, 1), "zaman": z.stat().st_mtime})
    return out


if __name__ == "__main__":
    print(yedekle())

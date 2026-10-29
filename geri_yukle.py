"""geri_yukle.py - Video Hub yedeğinden geri yükleme (2026-10-25).

Kullanım:
  python geri_yukle.py                         en yeni yedeği listeler (ne var, kaç dosya), hiçbir şey yazmaz
  python geri_yukle.py --liste [zip]           yedekteki dosyaları listeler
  python geri_yukle.py --kuru [zip]            neyin geri yükleneceğini gösterir, yazmaz
  python geri_yukle.py [zip] [--yalniz DESEN]  geri yükler (DESEN: 'transkript_*', 'ayarlar.json', 'profil/*', 'ghost/*' gibi; birden çok verilebilir)
  --uzerine-yaz                                var olan dosyaların üstüne de yazar (yazmadan önce eskisi .yedek/geri_yukleme_<zaman>/ altına kopyalanır)
  --sirlar                                     .yedek/sirlar.json'daki sırları Anahtar Zinciri'ne geri yazar (yalnız boş olanları; --uzerine-yaz ile hepsini)

Kurallar: zip önce doğrulanır (testzip); yol kaçışı olan üyeler atlanır; var olan dosya üstüne yazılmaz (--uzerine-yaz yoksa); kod paketi
(.kod.bundle) geri yüklenmez, `git clone .kod.bundle` ile ayrıca açılır. Site çalışırken ayarlar.json ve .isler.json geri yüklendiyse site yeniden başlatılmalı.
"""
import fnmatch
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

KLASOR = Path(__file__).resolve().parent


def _zip_sec(a):
    import yedek
    verilen = [x for x in a if x.endswith(".zip")]
    if verilen:
        y = Path(verilen[0]).expanduser()
        if not y.exists():
            y = yedek.hedef_klasor() / verilen[0]
        return y
    L = yedek.yedekler()
    return Path(L[0]["yol"]) if L else None


def _guvenli(uye):
    p = Path(uye)
    return not p.is_absolute() and ".." not in p.parts and uye not in (".kod.bundle",)


def geri_yukle(zip_yolu, yalniz=(), uzerine_yaz=False, kuru=False, log=print, kok=None):
    """Döner: {"yazilan": [...], "atlanan": [...], "yedeklenen": [...]}"""
    import yedek
    kok = Path(kok) if kok else KLASOR
    tamam, neden = yedek.dogrula(zip_yolu, log)
    if not tamam:
        raise SystemExit(f"Yedek doğrulanamadı: {neden}")
    sonuc = {"yazilan": [], "atlanan": [], "yedeklenen": []}
    eski_kl = kok / ".yedek" / f"geri_yukleme_{time.strftime('%Y%m%d_%H%M%S')}"
    with zipfile.ZipFile(zip_yolu) as z:
        for uye in z.namelist():
            if uye.endswith("/") or not _guvenli(uye) or uye == "YEDEK.txt":
                continue
            if yalniz and not any(fnmatch.fnmatch(uye, d) or fnmatch.fnmatch(uye, d + "/*") for d in yalniz):
                continue
            hedef = kok / uye
            if hedef.exists():
                if not uzerine_yaz:
                    sonuc["atlanan"].append(uye); continue
                if not kuru:
                    yedek_yol = eski_kl / uye; yedek_yol.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(hedef, yedek_yol)
                sonuc["yedeklenen"].append(uye)
            if not kuru:
                hedef.parent.mkdir(parents=True, exist_ok=True)
                with z.open(uye) as kaynak, open(hedef, "wb") as f:
                    shutil.copyfileobj(kaynak, f)
            sonuc["yazilan"].append(uye)
    log(f"{'(kuru) ' if kuru else ''}{len(sonuc['yazilan'])} dosya geri yüklendi, {len(sonuc['atlanan'])} var olduğu için atlandı"
        + (f", {len(sonuc['yedeklenen'])} eskisi {eski_kl.name} altına kopyalandı" if sonuc["yedeklenen"] else ""))
    return sonuc


def sirlari_geri_yukle(uzerine_yaz=False, log=print):
    import gizli
    yol = KLASOR / ".yedek" / "sirlar.json"
    if not yol.exists():
        log("Yerel sır yedeği yok (.yedek/sirlar.json)."); return 0
    d = json.loads(yol.read_text(encoding="utf-8"))
    n = 0
    for ad, deger in d.items():
        if deger and (uzerine_yaz or not gizli.al(ad)):
            if gizli.koy(ad, deger):
                n += 1; log(f"Anahtar Zinciri'ne geri yazıldı: {ad}")
    return n


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--sirlar" in a:
        sirlari_geri_yukle("--uzerine-yaz" in a); raise SystemExit(0)
    zp = _zip_sec(a)
    if not zp or not zp.exists():
        raise SystemExit("Yedek bulunamadı. Drive → Video Hub Yedek klasörüne bakın ya da zip yolunu verin.")
    print(f"Yedek: {zp} ({round(zp.stat().st_size / 1e6, 1)} MB)")
    yalniz = [a[i + 1] for i, x in enumerate(a) if x == "--yalniz" and i + 1 < len(a)]
    if "--liste" in a or not (yalniz or "--kuru" in a or "--uzerine-yaz" in a or any(x.endswith(".zip") for x in a)):
        with zipfile.ZipFile(zp) as z:
            uyeler = [u for u in z.namelist() if not u.endswith("/")]
        print(f"{len(uyeler)} dosya. Örnek:", ", ".join(uyeler[:8]))
        if "--liste" in a:
            print("\n".join(uyeler))
        else:
            print("Geri yüklemek için: python geri_yukle.py \"%s\" [--yalniz desen] [--kuru] [--uzerine-yaz]" % zp.name)
        raise SystemExit(0)
    geri_yukle(zp, yalniz=yalniz, uzerine_yaz="--uzerine-yaz" in a, kuru="--kuru" in a)

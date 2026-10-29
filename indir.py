#!/usr/bin/env python3
"""
indir.py - Video linkini bilgisayara indirir (yt-dlp ile; zor sitelerde kademeli yöntemler dener).

Kullanım:
  .venv/bin/python indir.py "<LINK>" [--kalite 720|1080|480|360|en|mp3] [--kesit 1:20-2:45]
                                     [--kapak] [--cerez chrome|safari] [--klasor yol]

  --kalite  720 (varsayılan): en çok 720p video + ses, mp4.  en: eldeki en iyi.  mp3: sadece ses.
  --kesit   videonun yalnızca bir bölümü (dakika:saniye-dakika:saniye; sonu boş bırakılırsa sona kadar).
  --kapak   kapak görselini de jpg olarak yanına kaydet.
  --cerez   giriş isteyen siteler için tarayıcı oturumu (Instagram, TikTok, X...).
  --klasor  kayıt klasörü (varsayılan: bu klasördeki indirilenler/).

Zor sitelerde sırayla denenen yöntemler: standart → tarayıcı kimliği (impersonate) → genel çözümleyici
→ esnek format. Giriş isteyen sitelerde --cerez verilmemişse açıkça "giriş istiyor" der.
Son satır: "Bitti. Dosya: <yol>"
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
VARSAYILAN_HEDEF = KLASOR / "indirilenler"
KALITELER = ("mp3", "360", "480", "720", "1080", "en")


def log(m):
    print(m, flush=True)


def _env():
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    return env


def _ffmpeg():
    for k in ("/opt/homebrew/bin", "/usr/local/bin"):
        if (Path(k) / "ffmpeg").exists():
            return k
    return None


def _impersonate_var():
    try:
        import curl_cffi  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def link_duzelt(link):
    m = re.match(r"^https?://(?:www\.)?vimeo\.com/(?:video/)?(\d+)(?:/([0-9a-f]+))?", link)
    if m:
        yeni = f"https://player.vimeo.com/video/{m.group(1)}"
        if m.group(2):
            yeni += f"?h={m.group(2)}"
        return yeni
    return link


def saniye(t):
    """'1:20' → 80, '1:02:03' → 3723, '95' → 95."""
    t = t.strip()
    if not t:
        return None
    par = [float(x) for x in t.split(":")]
    s = 0.0
    for p in par:
        s = s * 60 + p
    return s


def kesit_coz(metin):
    """'1:20-2:45' → (80, 165); '1:20-' → (80, None)."""
    if not metin:
        return None
    if "-" not in metin:
        raise SystemExit("HATA: kesit biçimi 'başlangıç-bitiş' olmalı, örn. 1:20-2:45")
    a, b = metin.split("-", 1)
    bas, bit = saniye(a) or 0.0, saniye(b)
    if bit is not None and bit <= bas:
        raise SystemExit("HATA: kesitin bitişi başlangıçtan sonra olmalı.")
    return bas, bit


def _format_secici(kalite, esnek=False):
    if kalite == "mp3":
        return "bestaudio/best"
    if esnek:
        return "best" if kalite == "en" else f"b[height<={kalite}]/b"
    if kalite == "en":
        return "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*[ext=mp4]+ba/bv*+ba/b"
    h = int(kalite)
    return (f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}][ext=mp4]+ba/"
            f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b")


def _etiket(kalite, kesit):
    e = "MP3" if kalite == "mp3" else ("en iyi" if kalite == "en" else f"{kalite}p")
    if kesit:
        bas, bit = kesit
        z = lambda s: f"{int(s)//60}.{int(s)%60:02d}"  # noqa: E731
        e += f", {z(bas)}-{z(bit) if bit is not None else 'son'}"
    return e


def _temiz_ad(ad):
    ad = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", ad)
    ad = re.sub(r"\s+", " ", ad).strip(" .")
    return ad[:80] or "video"


def _bos_yol(klasor, stem, uz):
    hedef = klasor / f"{stem}{uz}"
    n = 2
    while hedef.exists() or any(klasor.glob(f"{stem}.*")):
        hedef = klasor / f"{stem}_{n}{uz}"
        stem_n = f"{stem}_{n}"
        if not hedef.exists() and not any(klasor.glob(f"{stem_n}.*")):
            return hedef, stem_n
        n += 1
    return hedef, stem


def _siniflandir(kayit):
    k = kayit.lower()
    if "drm" in k or "kopya korumalı" in k:
        return "drm"
    if ("login required" in k or "sign in to confirm" in k or "sign in" in k or "use --cookies" in k
            or "cookies" in k or "rate-limit" in k or "requested content is not available" in k
            or "not a bot" in k or "login" in k):
        return "giris"
    if "please update" in k or "yt-dlp -u" in k or "update to the latest" in k:
        return "guncelle"
    if "unsupported url" in k or "no video formats" in k or "unable to extract" in k or "no video could be found" in k:
        return "cozumleyici"
    if "requested format is not available" in k:
        return "format"
    if ("403" in k or "cloudflare" in k or "unable to download webpage" in k or "just a moment" in k
            or "challenge" in k or "access denied" in k or "429" in k):
        return "engel"
    if "private video" in k or "404" in k or "not available" in k or "has been removed" in k or "does not exist" in k:
        return "yok"
    if ("timed out" in k or "connection" in k or "reset by peer" in k or "incomplete" in k or "5xx" in k
            or "http error 5" in k or "temporary" in k or "eof occurred" in k):
        return "gecici"
    return "bilinmiyor"


def video_indir(link, kalite="720", klasor=None, kesit=None, kapak=False, cerez=None, log=log):
    """İndirir; döner: dict(dosya, baslik, kanal, sure, platform, video_id, kapak, kalite, etiket)."""
    if kalite not in KALITELER:
        raise SystemExit("HATA: kalite mp3, 360, 480, 720, 1080 ya da en olabilir.")
    klasor = Path(klasor or VARSAYILAN_HEDEF)
    klasor.mkdir(parents=True, exist_ok=True)
    gecici = klasor / f".tmp_{uuid.uuid4().hex[:8]}"
    gecici.mkdir()
    link = link_duzelt(link)
    env = _env()
    deno = shutil.which("deno", path=env["PATH"])
    ff = _ffmpeg()

    def komut_yap(ekstra, esnek):
        k = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-simulate", "--newline", "--progress",
             "--retries", "10", "--fragment-retries", "10", "--concurrent-fragments", "4",
             "-o", str(gecici / "%(title).80s.%(ext)s"),
             "--write-thumbnail", "--convert-thumbnails", "jpg",
             "--print-to-file", "%(title)s\n%(uploader)s\n%(duration)s\n%(extractor_key)s\n%(id)s\n%(webpage_url)s",
             str(gecici / "bilgi.txt"),
             "--print-to-file", "after_move:filepath", str(gecici / "son.txt"),
             "-f", _format_secici(kalite, esnek)]
        if kalite == "mp3":
            k += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            k += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
        if kesit:
            bas, bit = kesit
            k += ["--download-sections", f"*{bas:.0f}-{bit:.0f}" if bit is not None else f"*{bas:.0f}-inf"]
        if ff:
            k += ["--ffmpeg-location", ff]
        k += ["--downloader-args", "ffmpeg:-loglevel error -stats"]
        if deno:
            k += ["--js-runtimes", f"deno:{deno}"]
        if cerez:
            k += ["--cookies-from-browser", cerez]
        return k + ekstra + [link]

    # kademeli yöntemler: (ad, ekstra argümanlar, esnek format)
    yontemler = [("standart", [], False)]
    if _impersonate_var():
        yontemler.append(("tarayıcı kimliğiyle", ["--impersonate", "chrome"], False))
    yontemler.append(("genel çözümleyiciyle", ["--force-generic-extractor"] + (["--impersonate", "chrome"] if _impersonate_var() else []), False))
    yontemler.append(("esnek formatla", ["--impersonate", "chrome"] if _impersonate_var() else [], True))

    log(f"[1/4] Bağlanılıyor: {link}")
    kayit, sebep, basarili = "", "", False
    denenen = set()
    i = 0
    gecici_sayac = 0
    while i < len(yontemler):
        ad, ekstra, esnek = yontemler[i]
        if ad in denenen:
            i += 1; continue
        denenen.add(ad)
        log(f"      Yöntem: {ad}")
        p = subprocess.Popen(komut_yap(ekstra, esnek), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        kayit = ""
        for satir in p.stdout:
            print(satir, end="", flush=True)
            kayit += satir
            if len(kayit) > 200_000:
                kayit = kayit[-100_000:]
        p.wait()
        if p.returncode == 0 and (gecici / "son.txt").exists():
            basarili = True
            break
        sebep = _siniflandir(kayit)
        if sebep in ("drm", "giris", "guncelle", "yok"):
            break
        if sebep == "gecici" and gecici_sayac < 2:
            gecici_sayac += 1; denenen.discard(ad)
            log(f"      Bağlantı sorunu, aynı yöntem tekrar deneniyor ({gecici_sayac}/2)...")
            time.sleep(4); continue
        # sebebe göre sıradaki en uygun yönteme atla
        hedef_ad = {"cozumleyici": "genel çözümleyiciyle", "format": "esnek formatla", "engel": "tarayıcı kimliğiyle"}.get(sebep)
        if hedef_ad and hedef_ad not in denenen:
            i = next(j for j, y in enumerate(yontemler) if y[0] == hedef_ad)
        else:
            i += 1
        log("      Olmadı, başka yöntem deneniyor...")

    if not basarili:
        shutil.rmtree(gecici, ignore_errors=True)
        if sebep == "drm":
            raise SystemExit("HATA: Bu video kopya korumalı (DRM); hiçbir araçla indirilemez.")
        if sebep == "giris":
            raise SystemExit("HATA: Bu site giriş istiyor. Tarayıcı girişinizi kullanmak için --cerez chrome (veya safari) ile tekrar deneyin."
                             if not cerez else "HATA: Bu site giriş istiyor; tarayıcı oturumu da yetmedi. Tarayıcıda o siteye giriş yaptığınızdan emin olun.")
        if sebep == "guncelle":
            raise SystemExit("HATA: Video sitesi yöntem değiştirmiş; indirme aracının güncellenmesi gerekiyor (please update yt-dlp).")
        if sebep == "yok":
            raise SystemExit("HATA: Video bulunamadı ya da gizli (404). Link doğru mu?")
        raise SystemExit("HATA: Hiçbir yöntemle indirilemedi. Ayrıntı için yukarıdaki kayda bakın.")

    son = Path((gecici / "son.txt").read_text(encoding="utf-8").strip().splitlines()[-1])
    satirlar = (gecici / "bilgi.txt").read_text(encoding="utf-8").splitlines() if (gecici / "bilgi.txt").exists() else []
    al = lambda i: satirlar[i].strip() if len(satirlar) > i and satirlar[i].strip() != "NA" else ""  # noqa: E731
    baslik = al(0) or son.stem
    try:
        sure = float(al(2) or 0)
    except ValueError:
        sure = 0.0
    if kesit:
        bas, bit = kesit
        sure = (bit if bit is not None else sure) - bas if sure else 0.0

    log("[4/4] Kaydediliyor")
    stem = _temiz_ad(baslik) + f" [{_etiket(kalite, kesit)}]"
    hedef, stem = _bos_yol(klasor, stem, son.suffix)
    shutil.move(str(son), str(hedef))
    kapak_yolu = ""
    jpg = next(iter(gecici.glob("*.jpg")), None)
    if jpg:
        (klasor / ".kapaklar").mkdir(exist_ok=True)
        shutil.copy(str(jpg), str(klasor / ".kapaklar" / f"{stem}.jpg"))
        if kapak:
            kapak_yolu = str(klasor / f"{stem}.jpg")
            shutil.move(str(jpg), kapak_yolu)
    shutil.rmtree(gecici, ignore_errors=True)
    log(f"      Başlık: {baslik}")
    if sure:
        log(f"      Süre: {int(sure)} sn")
    log(f"Bitti. Dosya: {hedef}")
    return {"dosya": str(hedef), "baslik": baslik, "kanal": al(1), "sure": sure, "platform": al(3),
            "video_id": al(4), "link": al(5) or link, "kapak": kapak_yolu, "kalite": kalite, "etiket": _etiket(kalite, kesit)}


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    if not args:
        print(__doc__); raise SystemExit(1)
    kalite, kesit, kapak, cerez, klasor, poz = "720", None, False, None, None, []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--kalite":
            kalite = re.sub(r"^(\d+)p$", r"\1", args[i + 1].lower()); i += 2
        elif a == "--kesit":
            kesit = kesit_coz(args[i + 1]); i += 2
        elif a == "--kapak":
            kapak = True; i += 1
        elif a == "--cerez":
            cerez = args[i + 1].lower(); i += 2
        elif a == "--klasor":
            klasor = args[i + 1]; i += 2
        else:
            poz.append(a); i += 1
    if not poz:
        raise SystemExit("HATA: link verilmedi.")
    video_indir(poz[0], kalite=kalite, klasor=klasor, kesit=kesit, kapak=kapak, cerez=cerez)


if __name__ == "__main__":
    main()

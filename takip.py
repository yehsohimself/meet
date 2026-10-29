#!/usr/bin/env python3
"""
takip.py - YouTube kanalı ya da oynatma listesi takibi: yeni video düşünce site onu kendiliğinden yazıya döker.

takip.json: {"kanallar": [{"id", "url", "ad", "islem": "ozet"|"transkript", "otomatik": true, "bilinen": [...],
                           "son_kontrol", "eklenme", "sayac"}]}
Tek başına: .venv/bin/python takip.py <kanal_veya_liste_linki>   → son videoları listeler
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
DOSYA = KLASOR / "takip.json"
PYTHON = sys.executable
SON_N = 12


def oku():
    try:
        return json.loads(DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"kanallar": []}


def yaz(d):
    DOSYA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _env():
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    return env


def _adaylar(url):
    url = url.strip()
    adaylar = [url]
    if "youtube.com/" in url and "list=" not in url and not re.search(r"/(videos|shorts|streams|live)/?$", url):
        adaylar.insert(0, url.rstrip("/") + "/videos")
    return adaylar


def _rss_adresi(k):
    """YouTube'un ücretsiz akışı (kanal ya da oynatma listesi) ya da podcast akışının kendisi; yoksa None."""
    lid, url = k.get("liste_id") or "", k.get("url") or ""
    if k.get("tur") == "podcast":
        return url
    if re.match(r"^UC[\w-]{22}$", lid):
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={lid}"
    if re.match(r"^(PL|UU|OL|FL)[\w-]{10,}$", lid):
        return f"https://www.youtube.com/feeds/videos.xml?playlist_id={lid}"
    return None


def _getir(url, zaman=20):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) Transcript/1.0"})
    with urllib.request.urlopen(req, timeout=zaman) as r:
        return r.read().decode("utf-8", "replace")


def rss_idler(k):
    """Akıştaki video/bölüm kimlikleri (en yeni önce). Hata olursa None (eski yola düşülür)."""
    adres = _rss_adresi(k)
    if not adres:
        return None
    try:
        x = _getir(adres)
    except Exception:  # noqa: BLE001
        return None
    if k.get("tur") == "podcast":
        return [b["id"] for b in _podcast_ayristir(x)[1]]
    return re.findall(r"<yt:videoId>([\w-]{11})</yt:videoId>", x) or None


def _podcast_ayristir(x):
    import html as _h
    ad = _h.unescape((re.search(r"<channel>.*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", x, re.S) or [None, ""])[1]).strip()
    bolumler = []
    for it in re.findall(r"<item\b.*?</item>", x, re.S):
        enc = re.search(r'<enclosure[^>]*url="([^"]+)"', it)
        if not enc:
            continue
        bas = _h.unescape((re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S) or [None, ""])[1]).strip()
        guid = (re.search(r"<guid[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</guid>", it, re.S) or [None, enc.group(1)])[1].strip()
        sure = (re.search(r"<itunes:duration>([\d:]+)</itunes:duration>", it) or [None, "0"])[1]
        sn = 0
        for parca in sure.split(":"):
            sn = sn * 60 + int(parca or 0)
        bolumler.append({"id": guid[-120:], "baslik": bas, "url": _h.unescape(enc.group(1)), "sure": sn, "canli": False})
    return ad, bolumler


def podcast_mu(url):
    if "youtube.com" in url or "youtu.be" in url:
        return False
    if re.search(r"(\.rss|\.xml|/feed/?|/rss/?|feeds\.|anchor\.fm/s/|/podcast)", url, re.I):
        return True
    try:
        return "<rss" in _getir(url, 10)[:2000]
    except Exception:  # noqa: BLE001
        return False


def listele(url, n=SON_N):
    """(meta, videolar). meta: {"ad","liste_id","url"}; videolar: [{"id","baslik","url","sure","canli"}]"""
    if podcast_mu(url):
        ad, bolumler = _podcast_ayristir(_getir(url))
        if not bolumler:
            raise RuntimeError("Akışta bölüm bulunamadı.")
        return {"ad": ad or url, "liste_id": "", "url": url, "tur": "podcast"}, bolumler[:n]
    env = _env()
    deno = shutil.which("deno", path=env["PATH"])
    son_hata = ""
    for aday in _adaylar(url):
        komut = [PYTHON, "-m", "yt_dlp", "--flat-playlist", "--no-warnings", "-q", "--playlist-end", str(n),
                 "--print", "%(id)s\t%(title)s\t%(url)s\t%(duration)s\t%(live_status)s\t%(playlist_title)s\t%(playlist_channel)s\t%(playlist_id)s\t%(channel)s"]
        if deno:
            komut += ["--js-runtimes", f"deno:{deno}"]
        komut.append(aday)
        try:
            p = subprocess.run(komut, env=env, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            son_hata = "zaman aşımı"; continue
        if p.returncode != 0 or not p.stdout.strip():
            son_hata = (p.stderr or "").strip().splitlines()[-1:] or ["liste alınamadı"]
            son_hata = son_hata[0]; continue
        videolar, meta = [], {"ad": "", "liste_id": "", "url": aday}
        for satir in p.stdout.splitlines():
            par = (satir.split("\t") + [""] * 9)[:9]
            vid, baslik, vurl, sure, canli, lt, lc, lid, ch = [x.strip() for x in par]
            if not vid or vid == "NA":
                continue
            if not meta["ad"]:
                meta["ad"] = (lc if lc and lc != "NA" else "") or (lt if lt != "NA" else "") or (ch if ch != "NA" else "") or aday
                meta["liste_id"] = lid if lid != "NA" else ""
            try:
                sure_f = float(sure) if sure not in ("", "NA") else 0
            except ValueError:
                sure_f = 0
            videolar.append({"id": vid, "baslik": baslik, "url": vurl if vurl.startswith("http") else f"https://www.youtube.com/watch?v={vid}",
                             "sure": sure_f, "canli": canli in ("is_live", "is_upcoming")})
        if videolar:
            return meta, videolar
    raise RuntimeError(son_hata or "liste alınamadı")


def ekle(url, islem="ozet", geriye=0):
    """Kanalı ekler; mevcut videoları 'bilinen' sayar. geriye=N ise son N video hemen işlenmek üzere döner."""
    meta, videolar = listele(url)
    d = oku()
    for k in d["kanallar"]:
        if k.get("liste_id") and k["liste_id"] == meta["liste_id"] or k["url"] == meta["url"]:
            raise RuntimeError("Bu kanal zaten takipte.")
    simdi = [v for v in videolar if not v["canli"]]
    hemen = simdi[:max(0, geriye)]
    k = {"id": uuid.uuid4().hex[:8], "url": meta["url"], "ad": meta["ad"], "liste_id": meta["liste_id"], "islem": islem,
         "otomatik": True, "bilinen": [v["id"] for v in videolar], "son_kontrol": time.time(), "eklenme": time.time(),
         "sayac": 0, "son_video": simdi[0]["baslik"] if simdi else "", "tur": meta.get("tur", "youtube")}
    d["kanallar"].append(k)
    yaz(d)
    return k, hemen


def kontrol(kanal_id):
    """Kanalı yeniden listeler; yeni (bilinmeyen, canlı olmayan) videoları döner ve bilinenlere ekler."""
    d = oku()
    k = next((x for x in d["kanallar"] if x["id"] == kanal_id), None)
    if not k:
        raise RuntimeError("Kanal bulunamadı.")
    bilinen = set(k.get("bilinen", []))
    idler = rss_idler(k)                       # hafif yol: akışta yeni yoksa yt-dlp hiç çalışmaz
    if idler is not None and all(i in bilinen for i in idler[:SON_N]):
        k["son_kontrol"] = time.time()
        yaz(d)
        return k, []
    meta, videolar = listele(k["url"])
    yeni = [v for v in videolar if v["id"] not in bilinen and not v["canli"]]
    k["bilinen"] = list(bilinen | {v["id"] for v in videolar})[-400:]
    k["son_kontrol"] = time.time()
    if meta["ad"] and not k.get("ad"):
        k["ad"] = meta["ad"]
    if videolar:
        k["son_video"] = videolar[0]["baslik"]
    k["sayac"] = k.get("sayac", 0) + len(yeni)
    yaz(d)
    return k, yeni


def sil(kanal_id):
    d = oku()
    d["kanallar"] = [k for k in d["kanallar"] if k["id"] != kanal_id]
    yaz(d)


def guncelle(kanal_id, **alanlar):
    d = oku()
    for k in d["kanallar"]:
        if k["id"] == kanal_id:
            k.update({a: b for a, b in alanlar.items() if a in ("islem", "otomatik", "ad")})
    yaz(d)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    meta, vids = listele(sys.argv[1])
    print(meta)
    for v in vids:
        print(f"  {v['id']}  {v['baslik']}  ({int(v['sure'] // 60)} dk){'  CANLI' if v['canli'] else ''}")

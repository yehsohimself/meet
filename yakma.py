#!/usr/bin/env python3
"""
yakma.py - Altyazıyı videonun içine yazar (burn-in) ve videodan altyazılı klip keser.

Bu bilgisayardaki ffmpeg'de altyazı filtresi (libass) yok; bu yüzden her altyazı parçası macOS'un kendi
yazı çizicisiyle (AppKit) şeffaf PNG olarak üretilir ve ffmpeg "overlay" filtresiyle videoya bindirilir.
Kodlama Apple donanımıyla (h264_videotoolbox) yapılır; hızlıdır.

Kullanım (tek başına):
  .venv/bin/python yakma.py transkript_x.json [--video yol.mp4] [--dil en] [--stil kutu|sade]
                             [--kesit 1:20-2:45] [--dikey] [--tut 0-12.5,20-45.2] [--altyazisiz] [--cikti yol.mp4]
  --dikey: 9:16, yüz takipli kadraj (Reels/TikTok); --dikey-orta: ortadan kırp.  --tut: yalnızca bu saniye aralıklarını tut, art arda ekle (metinden kesme).
Döner (son satır): "Bitti. Dosya: <yol>"
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
from transkript import altyazi_parcalari, _satira_bol  # noqa: E402

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"


def log(m):
    print(m, flush=True)


def video_bilgi(yol):
    p = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(yol)],
                       capture_output=True, text=True, timeout=30)
    j = json.loads(p.stdout or "{}")
    st = (j.get("streams") or [{}])[0]
    fr = st.get("r_frame_rate", "30/1")
    try:
        a, b = fr.split("/"); fps = float(a) / float(b)
    except Exception:  # noqa: BLE001
        fps = 30.0
    return {"w": int(st.get("width") or 0), "h": int(st.get("height") or 0), "fps": fps or 30.0,
            "sure": float((j.get("format") or {}).get("duration") or 0)}


# ----------------------------------------------------------------------------- yazı çizimi (AppKit)
def _kanvas(w, h):
    """Tam w×h piksellik şeffaf tuval (Retina ölçeklemesi olmadan)."""
    import AppKit
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, w, h, 8, 4, True, False, AppKit.NSCalibratedRGBColorSpace, 0, 0)
    rep.setSize_((w, h))
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)
    AppKit.NSColor.clearColor().set()
    AppKit.NSRectFill(((0, 0), (w, h)))
    return rep


def _kaydet(rep, yol):
    import AppKit
    AppKit.NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(AppKit.NSPNGFileType, None).writeToFile_atomically_(str(yol), True)



# Yazı tipi ve renk seçimi (2026-10-20; sitede Altyazılı video → Yazı tipi, Renk). None = varsayılan (sistem kalın, beyaz yazı / stilin vurgu rengi).
YAZI_TIPLERI = {"sistem": None, "yuvarlak": "rounded", "avenir": "AvenirNext-Heavy", "futura": "Futura-Bold", "helvetica": "HelveticaNeue-Bold", "georgia": "Georgia-Bold"}
SECIM = {"font": None, "renk": None}          # renk: (r, g, b) 0-1; animasyonlu stillerde vurgu, düz stillerde yazı rengi


def _font(boyut):
    import AppKit
    ad = YAZI_TIPLERI.get(SECIM["font"] or "sistem")
    if ad == "rounded":
        f = AppKit.NSFont.systemFontOfSize_weight_(boyut, AppKit.NSFontWeightHeavy)
        d = f.fontDescriptor().fontDescriptorWithDesign_(AppKit.NSFontDescriptorSystemDesignRounded)
        return AppKit.NSFont.fontWithDescriptor_size_(d, boyut) or f
    if ad:
        f = AppKit.NSFont.fontWithName_size_(ad, boyut)
        if f:
            return f
    return AppKit.NSFont.boldSystemFontOfSize_(boyut)


def _hex(h):
    h = (h or "").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) if len(h) == 6 else None


def _png_ciz(w, h, satirlar, yol, stil="kutu"):
    """Şeffaf w×h görsel; altyazı satırları altta ortalı. stil: kutu (yarı saydam kutu) | sade (sadece kenarlık)."""
    import AppKit
    rep = _kanvas(w, h)
    boyut = max(18, round(h * (0.052 if h >= w else 0.042)))
    font = _font(boyut)
    para = AppKit.NSMutableParagraphStyle.alloc().init()
    para.setAlignment_(AppKit.NSCenterTextAlignment)
    golge = AppKit.NSShadow.alloc().init()
    golge.setShadowColor_(AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.9))
    golge.setShadowBlurRadius_(boyut * 0.12)
    golge.setShadowOffset_((0, -boyut * 0.05))
    yazi_renk = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*SECIM["renk"], 1.0) if SECIM["renk"] else AppKit.NSColor.whiteColor()
    nit = {AppKit.NSFontAttributeName: font, AppKit.NSForegroundColorAttributeName: yazi_renk,
           AppKit.NSParagraphStyleAttributeName: para, AppKit.NSShadowAttributeName: golge}
    kenar = None
    if stil == "sade":                              # kenarlık ayrı çizilir, yazı üstüne: tek geçişte (eksi kalınlık) değişken yazı tipinin
        kenar = dict(nit)                           # iç çizgileri harflerin içinde siyah çizgi bırakıyordu (2026-10-24)
        kenar[AppKit.NSStrokeColorAttributeName] = AppKit.NSColor.blackColor()
        kenar[AppKit.NSStrokeWidthAttributeName] = 7.0
    satir_yuk = boyut * 1.28
    alt_pay = h * (0.11 if h > w else 0.075)
    toplam = satir_yuk * len(satirlar)
    if stil == "kutu":
        genis = 0
        for s in satirlar:
            genis = max(genis, AppKit.NSAttributedString.alloc().initWithString_attributes_(s, nit).size().width)
        pad_x, pad_y = boyut * 0.55, boyut * 0.22
        kutu = ((( w - genis) / 2 - pad_x, alt_pay - pad_y), (genis + 2 * pad_x, toplam + 2 * pad_y))
        yol_ = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(kutu, boyut * 0.25, boyut * 0.25)
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.55).set()
        yol_.fill()
    y = alt_pay + toplam - satir_yuk
    for s in satirlar:
        if kenar:
            AppKit.NSAttributedString.alloc().initWithString_attributes_(s, kenar).drawInRect_(((0, y), (w, satir_yuk)))
        AppKit.NSAttributedString.alloc().initWithString_attributes_(s, nit).drawInRect_(((0, y), (w, satir_yuk)))
        y -= satir_yuk
    _kaydet(rep, yol)


TURKCE = True          # büyük harfe çevirirken Türkçe kuralı (i → İ, ı → I); main() videonun diline göre ayarlar


def _buyuk(s):
    import harfler                                         # kelime kelime: Türkçe İ, İngilizce I (MİGROS, PEPSICO)
    return harfler.ust(s) if TURKCE else s.upper()


BASLIK_STILLERI = {
    # sarı: koyu kenarlı, turuncu parıltılı sarı, kalın yuvarlak büyük harf (bir YouTube serisinin kapaklarından alındı)
    "sari": {"renk": (1.0, 0.80, 0.16), "kenar": (0.30, 0.09, 0.0), "parlama": (1.0, 0.45, 0.0), "kutu": None},
    "sade": {"renk": (1.0, 1.0, 1.0), "kenar": (0.0, 0.0, 0.0), "parlama": None, "kutu": (0.0, 0.0, 0.0, 0.55)},
}


def baslik_stili(ad):
    """Stil adı ya da marka kodu → BASLIK_STILLERI anahtarı. Marka kodu verilirse markalar/<kod>/stil.json `baslik_stili` okunur (yoksa 'sade')."""
    if ad in BASLIK_STILLERI:
        return ad
    try:
        import json as _j
        st = _j.loads((Path(__file__).resolve().parent / "markalar" / str(ad) / "stil.json").read_text(encoding="utf-8")).get("baslik_stili")
        return st if st in BASLIK_STILLERI else "sade"
    except Exception:  # noqa: BLE001
        return "sade"


def _baslik_png(w, h, satirlar, yol, stil="sade"):
    """Videonun üstünde duran kanca başlığı (Shorts): 1-2 satır BÜYÜK HARF, ortalı, üstten ~%13 aşağıda; genişliğe sığdırılır."""
    import AppKit
    st = BASLIK_STILLERI[baslik_stili(stil)]
    rep = _kanvas(w, h)
    satirlar = [_buyuk(s.strip()) for s in satirlar if s.strip()][:3]
    boyut = round(min(w, h) * (0.115 if h > w else 0.075))

    def _font(b):
        f = AppKit.NSFont.systemFontOfSize_weight_(b, AppKit.NSFontWeightBlack)
        try:
            d = f.fontDescriptor().fontDescriptorWithDesign_(AppKit.NSFontDescriptorSystemDesignRounded)
            f = AppKit.NSFont.fontWithDescriptor_size_(d, b) or f
        except Exception:  # noqa: BLE001
            pass
        return f
    while boyut > 20:                                    # en uzun satır genişliğin %88'ine sığana dek küçült
        f = _font(boyut)
        en = max(AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: f}).size().width for s in satirlar)
        if en <= w * 0.88:
            break
        boyut -= 4
    font = _font(boyut)
    para = AppKit.NSMutableParagraphStyle.alloc().init(); para.setAlignment_(AppKit.NSCenterTextAlignment)
    renk = lambda c, a=1.0: AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(c[0], c[1], c[2], a)  # noqa: E731
    satir_yuk = boyut * 1.08
    ust = h * (0.13 if h > w else 0.08)
    toplam = satir_yuk * len(satirlar)
    y = h - ust - satir_yuk
    if st.get("kutu"):
        genis = max(AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font}).size().width for s in satirlar)
        k = st["kutu"]; pad = boyut * 0.35
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*k).set()
        AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_((((w - genis) / 2 - pad, h - ust - toplam - pad * 0.6), (genis + 2 * pad, toplam + pad * 1.2)), boyut * 0.2, boyut * 0.2).fill()
    for s in satirlar:
        kutu = ((0, y), (w, satir_yuk * 1.15))
        if st.get("parlama"):                             # 1) turuncu parıltı
            g = AppKit.NSShadow.alloc().init(); g.setShadowColor_(renk(st["parlama"], 0.95)); g.setShadowBlurRadius_(boyut * 0.28); g.setShadowOffset_((0, 0))
            AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font, AppKit.NSParagraphStyleAttributeName: para,
                AppKit.NSForegroundColorAttributeName: renk(st["kenar"]), AppKit.NSShadowAttributeName: g}).drawInRect_(kutu)
        AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font, AppKit.NSParagraphStyleAttributeName: para,   # 2) kalın koyu kenar
            AppKit.NSStrokeColorAttributeName: renk(st["kenar"]), AppKit.NSStrokeWidthAttributeName: 14.0}).drawInRect_(kutu)
        AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font, AppKit.NSParagraphStyleAttributeName: para,   # 3) dolgu
            AppKit.NSForegroundColorAttributeName: renk(st["renk"])}).drawInRect_(kutu)
        y -= satir_yuk
    _kaydet(rep, yol)


# Kelime kelime (hareketli) stiller: karaoke = cümle görünür, söylenen kelime renkli; pop = 2-3 kelime büyük ve
# BÜYÜK HARF, söylenen sarı; vurgu = cümle görünür, söylenen kelime büyür ve renklenir.
KELIME_STILLERI = {
    "karaoke": {"grup": 0, "buyuk_harf": False, "kutu": True, "vurgu": (1.0, 0.85, 0.1), "olcek": 1.0, "cerceve": False},
    "pop": {"grup": 3, "buyuk_harf": True, "kutu": False, "vurgu": (1.0, 0.85, 0.1), "olcek": 1.0, "cerceve": True, "boyut": 1.55},
    "vurgu": {"grup": 0, "buyuk_harf": False, "kutu": False, "vurgu": (0.35, 0.9, 0.45), "olcek": 1.22, "cerceve": True, "boyut": 1.15},
}


def _png_ciz_kelime(w, h, kelimeler, aktif, yol, stil):
    """kelimeler: [str]; aktif: söylenen kelimenin dizini (-1: yok). Satırlara sarar, altta ortalar."""
    import AppKit
    st = KELIME_STILLERI[stil]
    rep = _kanvas(w, h)
    boyut = max(18, round(h * (0.052 if h >= w else 0.042) * st.get("boyut", 1.0)))
    sozcukler = [_buyuk(k) if st["buyuk_harf"] else k for k in kelimeler]
    # En uzun kelime (büyütülmüş haliyle) genişliğin %88'ine sığmıyorsa yazı boyutunu küçült (KAPATTIĞIMDA taşıyordu)
    en_genis = max((AppKit.NSAttributedString.alloc().initWithString_attributes_(sz, {AppKit.NSFontAttributeName: _font(boyut * st["olcek"])}).size().width
                    for sz in sozcukler), default=0)
    if en_genis > w * 0.88:
        boyut = max(18, int(boyut * (w * 0.88) / (en_genis + 1)))
    font = _font(boyut)
    buyuk = _font(boyut * st["olcek"])
    golge = AppKit.NSShadow.alloc().init()
    golge.setShadowColor_(AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.9)); golge.setShadowBlurRadius_(boyut * 0.12); golge.setShadowOffset_((0, -boyut * 0.05))
    beyaz, vr = AppKit.NSColor.whiteColor(), AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*(SECIM["renk"] or st["vurgu"]), 1.0)
    def nitelik(aktif_mi, kenar=False):
        n = {AppKit.NSFontAttributeName: buyuk if aktif_mi and st["olcek"] != 1.0 else font,
             AppKit.NSForegroundColorAttributeName: vr if aktif_mi else beyaz, AppKit.NSShadowAttributeName: golge}
        if kenar:                                   # kenarlık ayrı geçişte (yazı üstüne çizilir; harf içinde çizgi kalmasın)
            n[AppKit.NSStrokeColorAttributeName] = AppKit.NSColor.blackColor(); n[AppKit.NSStrokeWidthAttributeName] = 4.4
        return n
    # Satırlara sar (genişliğin %86'sı)
    en_fazla = w * 0.86; satirlar, cur, cur_w = [], [], 0.0
    bosluk = AppKit.NSAttributedString.alloc().initWithString_attributes_(" ", nitelik(False)).size().width
    for i, sz in enumerate(sozcukler):
        gw = AppKit.NSAttributedString.alloc().initWithString_attributes_(sz, nitelik(i == aktif)).size().width
        if cur and cur_w + bosluk + gw > en_fazla:
            satirlar.append(cur); cur, cur_w = [], 0.0
        cur.append((i, sz, gw)); cur_w += (bosluk if cur_w else 0) + gw
    if cur:
        satirlar.append(cur)
    satir_yuk = boyut * st["olcek"] * 1.3
    alt_pay = h * (0.11 if h > w else 0.075)
    toplam = satir_yuk * len(satirlar)
    if st["kutu"]:
        genis = max(sum(g for _i, _s, g in sat) + bosluk * (len(sat) - 1) for sat in satirlar)
        pad_x, pad_y = boyut * 0.55, boyut * 0.22
        kutu = (((w - genis) / 2 - pad_x, alt_pay - pad_y), (genis + 2 * pad_x, toplam + 2 * pad_y))
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.55).set()
        AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(kutu, boyut * 0.25, boyut * 0.25).fill()
    y = alt_pay + toplam - satir_yuk
    for sat in satirlar:
        genis = sum(g for _i, _s, g in sat) + bosluk * (len(sat) - 1)
        x = (w - genis) / 2
        for i, sz, gw in sat:
            a = AppKit.NSAttributedString.alloc().initWithString_attributes_(sz, nitelik(i == aktif))
            dy = (satir_yuk - a.size().height) / 2
            if st["cerceve"]:
                AppKit.NSAttributedString.alloc().initWithString_attributes_(sz, nitelik(i == aktif, True)).drawAtPoint_((x, y + dy))
            a.drawAtPoint_((x, y + dy)); x += gw + bosluk
        y -= satir_yuk
    _kaydet(rep, yol)


def _kelime_kareleri(secili, stil, w, h, gecici, sure, log):
    """Kelime kelime stil için ffconcat listesi: her kelime süresi boyunca o kelime vurgulu kare."""
    st = KELIME_STILLERI[stil]
    satirlar, t, n = ["ffconcat version 1.0"], 0.0, 0
    for c in secili:
        kel = [(b, e, k) for b, e, k in (c.get("kelimeler") or []) if k.strip()]
        if not kel:
            parca = c["metin"].split(); sure_c = max(0.3, c["bit"] - c["bas"]); dt = sure_c / max(1, len(parca))
            kel = [(c["bas"] + i * dt, c["bas"] + (i + 1) * dt, p) for i, p in enumerate(parca)]
        gruplar = [kel] if not st["grup"] else [kel[i:i + st["grup"]] for i in range(0, len(kel), st["grup"])]
        for g in gruplar:
            metinler = [k for _b, _e, k in g]
            for j, (b, e, _k) in enumerate(g):
                b = max(b, t); e = max(e, b + 0.05)
                if b > t + 0.01:
                    satirlar += ["file 'bos.png'", f"duration {b - t:.3f}"]
                p = gecici / f"k{n:05d}.png"; n += 1
                _png_ciz_kelime(w, h, metinler, j, p, stil)
                satirlar += [f"file '{p.name}'", f"duration {e - b:.3f}"]
                t = e
                if n % 100 == 0:
                    log(f"      Altyazı: {n} kelime")
    if sure > t:
        satirlar += ["file 'bos.png'", f"duration {sure - t + 1:.3f}"]
    satirlar += ["file 'bos.png'"]
    return satirlar


def _bos_png(w, h, yol):
    _kaydet(_kanvas(w, h), yol)


# ----------------------------------------------------------------------------- ana iş
YUMUSATMA = 0.03     # her parçanın sesi 30 ms içinde açılır/kapanır: birleşme yerinde "tık" sesi olmaz (Manticore fade_ms)


def _yumusat(sure):
    if sure < 4 * YUMUSATMA:
        return ""
    return f",afade=t=in:st=0:d={YUMUSATMA},afade=t=out:st={sure - YUMUSATMA:.3f}:d={YUMUSATMA}"


def _kes_birlestir(video, tut, cikti, log=log):
    """Videodan yalnızca tut=[(bas,bit),...] aralıklarını alır, art arda ekler (yeniden kodlama, donanım)."""
    n = len(tut)
    if n <= 60:     # her parça kendi girdisi: ffmpeg doğrudan o saniyeye atlar (2026-10-24: tek girdide trim videonun tamamını parça sayısı
        # kadar çözüyor, sırası değişmiş kurguda da öndeki parçayı beklerken bütün kareleri bellekte tutuyordu; 4 dk 8 parça 0,5x hızdaydı)
        girdi = []
        for b, e in tut:
            girdi += ["-ss", f"{b:.3f}", "-t", f"{e - b:.3f}", "-i", str(video)]
        fc = "".join(f"[{i}:v]setpts=PTS-STARTPTS[v{i}];[{i}:a]asetpts=PTS-STARTPTS{_yumusat(e - b)}[a{i}];" for i, (b, e) in enumerate(tut))
    else:
        girdi = ["-i", str(video)]
        fc = "".join(f"[0:v]trim=start={b:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];[0:a]atrim=start={b:.3f}:end={e:.3f},asetpts=PTS-STARTPTS{_yumusat(e - b)}[a{i}];"
                     for i, (b, e) in enumerate(tut))
    fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    komut = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-stats", *girdi, "-filter_complex", fc,
             "-map", "[v]", "-map", "[a]", "-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", str(cikti)]
    log(f"[2/4] Video kesiliyor: {n} parça birleştiriliyor")
    p = subprocess.Popen(komut, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for satir in p.stdout:
        satir = satir.rstrip("\n")
        if "\r" in satir:
            satir = satir.split("\r")[-1]
        if satir.strip():
            print(satir, flush=True)
    p.wait()
    if p.returncode != 0 or not Path(cikti).exists():
        raise SystemExit("HATA: Video kesilemedi (ffmpeg).")


def altyazi_yak(video, cueler, cikti, stil="kutu", kesit=None, log=log, dikey=False, tut=None, takip=True, temiz_ses=False, broll_ekle=False,
                baslik=None, baslik_stil="sade", oran=None, zoom=False, isimler=None, studyo=False, emoji=False, muzik=None, siralar=None, arka=None):
    """cueler: [{"bas","bit","metin"}] (video zamanına göre). kesit=(bas,bit) verilirse o aralık kesilir ve
    altyazılar o aralığa göre kaydırılır. dikey=True: 9:16 ortadan kırpılır. tut=[(bas,bit)]: önce yalnızca bu
    aralıklar tutulup birleştirilir (cueler bu yeni zamana göre verilmelidir, bkz. cueler_json). Döner: çıktı yolu."""
    video, cikti = Path(video), Path(cikti)
    gecici_kes = None
    if tut:
        gecici_kes = Path(tempfile.mkdtemp(prefix="kes_"))
        _kes_birlestir(video, tut, gecici_kes / "kesik.mp4", log)
        video = gecici_kes / "kesik.mp4"
    bilgi = video_bilgi(video)
    w, h = bilgi["w"], bilgi["h"]
    if not w or not h:
        raise SystemExit("HATA: Video okunamadı.")
    if w % 2:
        w -= 1
    if h % 2:
        h -= 1
    bas0, bit0 = (kesit or (0.0, None))
    sure = (bit0 - bas0) if bit0 is not None else max(0.0, bilgi["sure"] - bas0)
    if sure <= 0:
        raise SystemExit("HATA: Kesit süresi sıfır.")
    if arka in ("bulanik", "koyu"):                    # arka plan: önce yalnız istenen bölüm işlenir, sonra o yeni video kullanılır
        import arkaplan
        gecici_ap = Path(tempfile.mkdtemp(prefix="arkaplan_"))
        log("[1/4] Arka plan " + ("bulanıklaştırılıyor" if arka == "bulanik" else "değiştiriliyor"))
        yeni = arkaplan.isle(video, bas0, sure, gecici_ap / "ap.mp4", arka, log=log)
        if yeni:
            video, bas0 = yeni, 0.0
        import atexit
        atexit.register(shutil.rmtree, gecici_ap, True)
    kirp = None; plan = None
    oran = oran or (9 / 16 if dikey else None)
    if oran and w / h > oran + 0.01:
        cw = int(round(h * oran)); cw -= cw % 2
        kirp = f"crop={cw}:{h}:(iw-{cw})/2:0,"
        if takip:
            try:
                import kadraj
                log("[1/4] Kadraj: yüz takibi hesaplanıyor")
                plan = kadraj.kadraj_plani(video, bas0, sure, w, h, log=log, oran=oran)
                if plan.get("filtre"):
                    kirp = plan["filtre"]
                log(f"      Kadraj düzeni: {plan.get('duzen')} (yüz görünürlüğü %{int(plan.get('yuz_orani', 0) * 100)})")
            except Exception as e:  # noqa: BLE001
                log(f"      Yüz takibi yapılamadı ({e}); ortadan kırpılıyor"); plan = None
        w = cw
        hedef = {0.5625: (1080, 1920), 0.8: (1080, 1350), 1.0: (1080, 1080)}.get(round(oran, 4))
        if hedef and h < hedef[1]:                       # Shorts/Reels 1080×1920, Instagram 4:5 1080×1350, kare 1080×1080 (küçük çıkmasın)
            w, h = hedef
    secili = []
    for c in cueler:
        b, e = c["bas"] - bas0, c["bit"] - bas0
        if e <= 0 or b >= sure:
            continue
        secili.append({"bas": max(0.0, b), "bit": min(sure, e), "metin": c["metin"],
                       "kelimeler": [(max(0.0, kb - bas0), min(sure, ke - bas0), kw) for kb, ke, kw in (c.get("kelimeler") or []) if ke - bas0 > 0 and kb - bas0 < sure]})
    gecici = Path(tempfile.mkdtemp(prefix="yakma_"))
    try:
        log(f"[2/4] Altyazı çiziliyor: {len(secili)} parça")
        bos = gecici / "bos.png"
        _bos_png(w, h, bos)
        if stil in KELIME_STILLERI:
            satirlar = _kelime_kareleri(secili, stil, w, h, gecici, sure, log)
        else:
            satirlar = ["ffconcat version 1.0"]
            t = 0.0
            for i, c in enumerate(secili):
                if c["bas"] > t + 0.01:
                    satirlar += [f"file 'bos.png'", f"duration {c['bas'] - t:.3f}"]
                p = gecici / f"c{i:04d}.png"
                _png_ciz(w, h, c.get("satirlar") or _satira_bol(c["metin"]), p, stil)
                satirlar += [f"file '{p.name}'", f"duration {max(0.05, c['bit'] - c['bas']):.3f}"]
                t = c["bit"]
                if i % 50 == 0:
                    log(f"      Altyazı: {i + 1}/{len(secili)}")
            if sure > t:
                satirlar += [f"file 'bos.png'", f"duration {sure - t + 1:.3f}"]
            satirlar += ["file 'bos.png'"]
        (gecici / "cues.txt").write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        log("[3/4] Video yazılıyor")
        if plan and plan.get("komutlar"):
            import kadraj
            kirp = kadraj.komut_dosyasi(plan, gecici) + kirp
        bit_hizi = "8M" if max(w, h) >= 1920 else ("5M" if max(w, h) >= 1280 else "2500k")
        komut = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-stats"]
        if bas0:
            komut += ["-ss", f"{bas0:.3f}"]
        komut += ["-i", str(video)]
        komut += ["-f", "concat", "-safe", "0", "-i", str(gecici / "cues.txt")]
        ek_girdi, broll_filtre, taban = [], "", "[v]"
        if broll_ekle:
            try:
                import broll
                brolls = broll.plan(secili, sure, dikey=(h > w), log=log)
                if brolls:
                    ek_girdi, broll_filtre, taban = broll.filtre_ekle(2, "[v]", brolls, w, h)
            except Exception as e:  # noqa: BLE001
                log(f"      B-roll eklenemedi ({e})")
        komut += ek_girdi
        baslik_filtre = ""
        if baslik:
            _baslik_png(w, h, re.split(r"\s*/\s*|\n", baslik), gecici / "baslik.png", baslik_stil)
            n_girdi = 2 + sum(1 for x in ek_girdi if x == "-i")
            komut += ["-loop", "1", "-t", f"{sure + 1:.3f}", "-i", str(gecici / "baslik.png")]
            baslik_filtre = f";[ara][{n_girdi}:v]overlay=0:0:shortest=0[out]"
        konusan_f = ""
        if siralar and not oran:
            try:
                import konusan
                dl, kcw, kch = konusan.plan(video, bas0, sure, w, h, siralar, log=log)
                ff, _ok = konusan.filtre(dl, kcw, kch, w, h, gecici)
                if ff:
                    konusan_f = "," + ff
            except Exception as e:  # noqa: BLE001
                log(f"      Konuşana geçen kadraj yapılamadı ({str(e)[:80]})")
        zoom_f = ""
        if zoom:
            import duzenle
            zp = duzenle.yakinlastirma(secili, sure)
            if zp:
                z = duzenle.olcek_ifadesi(zp)
                zoom_f = (f",scale=w='trunc(iw*({z})/2)*2':h='trunc(ih*({z})/2)*2':eval=frame:flags=bicubic,"
                          f"crop={w}:{h}:'(iw-{w})/2':'(ih-{h})*0.35'")
                log(f"      Otomatik yakınlaştırma: {len(zp)} cümlede")
        isim_f, n_sonraki = "", 2 + sum(1 for x in ek_girdi if x == "-i") + (1 if baslik else 0)
        for j, (t0, t1, ad) in enumerate(isimler or []):
            import duzenle
            png = gecici / f"isim{j}.png"
            duzenle.isim_png(w, h, ad, png)
            komut += ["-loop", "1", "-t", f"{sure + 1:.3f}", "-i", str(png)]
            onceki = "out" if not isim_f else f"i{j - 1}"
            isim_f += (f";[{n_sonraki}:v]format=rgba,fade=t=in:st={t0:.2f}:d=0.25:alpha=1,fade=t=out:st={t1 - 0.3:.2f}:d=0.3:alpha=1[n{j}];"
                       f"[{onceki}][n{j}]overlay=0:0:shortest=0:enable='between(t,{t0:.2f},{t1:.2f})'[i{j}]")
            n_sonraki += 1
        if isim_f:
            log(f"      Konuşmacı ismi etiketi: {', '.join(a for _t, _e, a in isimler)}")
        if emoji:
            import duzenle
            onceki_son = f"i{len(isimler) - 1}" if isim_f else "out"
            for j, (t0, em) in enumerate(duzenle.emoji_plani(secili, sure, log=log)):
                png = gecici / f"emoji{j}.png"
                duzenle.emoji_png(w, h, em, png)
                komut += ["-loop", "1", "-t", f"{sure + 1:.3f}", "-i", str(png)]
                isim_f += (f";[{n_sonraki}:v]format=rgba,fade=t=in:st={t0:.2f}:d=0.15:alpha=1,fade=t=out:st={t0 + 1.25:.2f}:d=0.25:alpha=1[e{j}];"
                           f"[{onceki_son}][e{j}]overlay=0:0:shortest=0:enable='between(t,{t0:.2f},{t0 + 1.5:.2f})'[em{j}]")
                onceki_son = f"em{j}"; n_sonraki += 1
        ses_map = "0:a?"
        if studyo:
            import duzenle
            sw = duzenle.studyo_sesi(video, bas0, sure, gecici, log=log)
            if sw:
                komut += ["-i", str(sw)]; ses_map = f"{n_sonraki}:a"; n_sonraki += 1
        ses_f = ""
        if muzik and Path(muzik).exists():
            komut += ["-stream_loop", "-1", "-i", str(muzik)]
            kaynak_ses = f"[{ses_map.split(':')[0]}:a]" if not ses_map.endswith("?") else "[0:a]"
            ses_f = (f";{kaynak_ses}asplit=2[kon][yan];[{n_sonraki}:a]volume=0.32,afade=t=in:d=1.5,afade=t=out:st={max(0.0, sure - 2):.2f}:d=2[mz];"
                     f"[mz][yan]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450:makeup=1[mzd];"
                     f"[kon][mzd]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[ses]")
            ses_map = "[ses]"; n_sonraki += 1
            log(f"      Müzik altlığı: {Path(muzik).stem} (konuşmada kısılır)")
        son = onceki_son if emoji else (f"i{len(isimler) - 1}" if isim_f else "out")
        cikis = "ara" if baslik else "out"
        komut += ["-filter_complex", f"[0:v]{kirp or ''}scale={w}:{h}:flags=lanczos{konusan_f}{zoom_f}[v];{broll_filtre}[1:v]scale={w}:{h},format=rgba[s];{taban}[s]overlay=0:0:eof_action=pass:shortest=0[{cikis}]{baslik_filtre}{isim_f}{ses_f}",
                  "-map", f"[{son}]", "-map", ses_map, "-c:v", "h264_videotoolbox", "-b:v", bit_hizi, "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]
        if temiz_ses and not studyo:
            import temizle
            komut += ["-af", temizle.filtre_zinciri("orta")]
            log("      Ses temizleniyor (gürültü bastırma + dengeleme)")
        if kesit:
            komut += ["-t", f"{sure:.3f}"]
        komut.append(str(cikti))
        p = subprocess.Popen(komut, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for satir in p.stdout:
            satir = satir.rstrip("\n")
            if "\r" in satir:
                satir = satir.split("\r")[-1]
            if satir.strip():
                print(satir, flush=True)
        p.wait()
        if p.returncode != 0 or not cikti.exists():
            raise SystemExit("HATA: Video yazılamadı (ffmpeg).")
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
        if gecici_kes:
            shutil.rmtree(gecici_kes, ignore_errors=True)
    log("[4/4] Kaydedildi")
    log(f"Bitti. Dosya: {cikti}")
    return cikti


def _kelimeler(s):
    """Segmentin kelime zamanları (varsa gerçek, yoksa karakter oranıyla)."""
    if s.get("kelimeler"):
        return [(k[0], k[1], k[2]) for k in s["kelimeler"]]
    parca = s["metin"].split()
    if not parca:
        return []
    toplam = sum(len(p) + 1 for p in parca); t = s["bas"]; sure = max(0.5, s["bit"] - s["bas"]); out = []
    for p in parca:
        dt = sure * (len(p) + 1) / toplam
        out.append((t, t + dt, p)); t += dt
    return out


def tut_coz(metin, sirala=True):
    """'0-12.5,20-45.2' → [(0,12.5),(20,45.2)] (sıralı, çakışmasız). sirala=False: verilen sırayla (metinden düzenlemede paragrafların
    yeri değiştirildiyse; Studio kurgu, 2026-10-24)."""
    out = []
    for parca in (metin or "").split(","):
        if "-" not in parca:
            continue
        a, b = parca.split("-", 1)
        try:
            a, b = float(a), float(b)
        except ValueError:
            continue
        if b - a >= 0.05:
            out.append((a, b))
    if sirala:
        out.sort()
    return out


def zaman_kaydir(t, tut):
    """Orijinal zamanı, tutulan aralıkların birleştirilmiş zamanına çevirir; aralık dışıysa None."""
    off = 0.0
    for b, e in tut:
        if b <= t <= e:
            return off + (t - b)
        off += e - b
    return None


def cueler_json(json_yolu, dil=None, tut=None):
    """Transkript JSON'undan altyazı parçaları; dil verilirse o dildeki çeviri, tut verilirse yalnızca tutulan
    aralıklardaki kelimeler (yeni zaman eksenine kaydırılmış)."""
    d = json.loads(Path(json_yolu).read_text(encoding="utf-8"))
    seg = d["segmentler"]
    if dil and dil != "orijinal":
        cev = (d["veri"].get("ceviriler") or {}).get(dil)
        if not cev:
            raise SystemExit(f"HATA: Bu transkriptin {dil} çevirisi yok.")
        seg = [{"bas": s["bas"], "bit": s["bit"], "k": s["k"], "metin": m} for s, m in zip(seg, cev["segmentler"])]
    if tut:
        yeni = []
        for s in seg:
            kel = []
            for b, e, w in _kelimeler(s):
                orta = (b + e) / 2
                nb, ne = zaman_kaydir(orta, tut), zaman_kaydir(orta, tut)
                if nb is None:
                    continue
                dt = max(0.05, (e - b) / 2)
                kel.append((max(0.0, nb - dt), ne + dt, w))
            if kel:
                kel.sort(key=lambda k: k[0])
                yeni.append({"bas": kel[0][0], "bit": kel[-1][1], "k": s.get("k", "0"), "metin": " ".join(k[2] for k in kel), "kelimeler": kel})
        seg = sorted(yeni, key=lambda x: x["bas"])            # sırası değiştirilmiş kurguda yeni zaman eksenine göre
    if not tut and not (dil and dil != "orijinal"):              # anlamlı kırılım planı varsa onu kullan
        import altyazi
        plan = altyazi.gecerli_plan(d["veri"], seg)
        if plan:
            return altyazi.parcalar(seg, plan), d["veri"]
    return altyazi_parcalari(seg), d["veri"]


def _dolgu_pencereleri(d):
    try:
        import dolgu
        return dolgu.gecerli_pencereler(d)
    except Exception:  # noqa: BLE001
        return None


def _sinirlari_oturt(js, video, tut):
    """Kesim kenarlarını sesin sessizlik haritasına taşır (kesim_sinir): kenar kelimenin ortasına düşmez, konuşmanın yanında
    kısa bir nefes payı kalır. Herhangi bir sorun olursa aralıklar olduğu gibi kalır."""
    try:
        import kesim_sinir
        d = json.loads(Path(js).read_text(encoding="utf-8"))
        harita = kesim_sinir.ses_haritasi(video)
        toplam = harita["sure"] or video_bilgi(Path(video))["sure"]
        yeni, r = kesim_sinir.oturt(tut, harita["sessizlik"], kesim_sinir.kelimeler(d["segmentler"], _dolgu_pencereleri(d)), toplam)
        if yeni:
            log(f"      Kesim kenarları sese oturtuldu: {r['kenar']} kenar, {r['sessizlige']} tanesi sessizliğe"
                + (f", {r['kelime_arasina']} tanesi kelime arasına" if r["kelime_arasina"] else "")
                + (f", {r['oturmadi']} tanesi yerinde kaldı" if r["oturmadi"] else ""))
            return yeni
    except Exception as e:  # noqa: BLE001
        log(f"      Kesim kenarları sese oturtulamadı ({e}); yazı zamanları kullanılıyor")
    return tut


def _saniye(t):
    t = t.strip()
    if not t:
        return None
    s = 0.0
    for p in t.split(":"):
        s = s * 60 + float(p)
    return s


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    if not args:
        print(__doc__); raise SystemExit(1)
    video = dil = cikti = kesit = None
    stil = "kutu"; dikey = False; tut = None; altyazisiz = False; ek = ""; takip = True; temiz_ses = False; broll_ekle = False
    baslik = None; baslik_stil = "sade"
    oran = None; zoom = False; isim_bandi = False; studyo = False; tekrar = False; kesit_etiketi = None; emoji = False; muzik = None; konusana = False; arka = None
    poz = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--video":
            video = args[i + 1]; i += 2
        elif a == "--dil":
            dil = args[i + 1]; i += 2
        elif a == "--stil":
            stil = args[i + 1]; i += 2
        elif a == "--font":
            SECIM["font"] = args[i + 1] if args[i + 1] in YAZI_TIPLERI else None; i += 2
        elif a == "--renk":
            SECIM["renk"] = _hex(args[i + 1]); i += 2
        elif a == "--cikti":
            cikti = args[i + 1]; i += 2
        elif a == "--kesit":
            a_, b_ = args[i + 1].split("-", 1)
            kesit = (_saniye(a_) or 0.0, _saniye(b_)); i += 2
        elif a == "--dikey":
            dikey = True; i += 1
        elif a == "--dikey-orta":
            dikey = True; takip = False; i += 1
        elif a == "--temiz-ses":
            temiz_ses = True; i += 1
        elif a == "--broll":
            broll_ekle = True; i += 1
        elif a == "--ek":
            ek = re.sub(r'[\\/:*?"<>|]+', ' ', args[i + 1]).strip()[:60]; i += 2
        elif a == "--baslik":
            baslik = args[i + 1].strip()[:120]; i += 2
        elif a == "--baslik-stil":
            baslik_stil = args[i + 1]; i += 2
        elif a == "--format":
            oran = {"9:16": 9 / 16, "4:5": 0.8, "1:1": 1.0}.get(args[i + 1]); i += 2
        elif a == "--arka-plan":
            arka = args[i + 1] if args[i + 1] in ("bulanik", "koyu") else None; i += 2
        elif a == "--konusana":
            konusana = True; i += 1
        elif a == "--muzik":
            muzik = args[i + 1]; i += 2
        elif a == "--emoji":
            emoji = True; i += 1
        elif a == "--zoom":
            zoom = True; i += 1
        elif a == "--isim-bandi":
            isim_bandi = True; i += 1
        elif a == "--studyo-sesi":
            studyo = True; i += 1
        elif a == "--tekrar-temizle":
            tekrar = True; i += 1
        elif a == "--altyazisiz":
            altyazisiz = True; i += 1
        elif a == "--tut":
            tut = tut_coz(args[i + 1]); i += 2
        elif a == "--tut-sirali":
            tut = tut_coz(args[i + 1], sirala=False); i += 2
        else:
            poz.append(a); i += 1
    js = Path(poz[0])
    if tekrar and video:
        import duzenle
        log("[0/4] Tekrar alımlar aranıyor")
        cikar = duzenle.tekrar_alimlar(js, log=log)
        if kesit:                                   # yalnız istenen bölümdeki tekrarlar; bölüm dışı hiç işlenmez
            k0, k1 = kesit[0], kesit[1] or video_bilgi(Path(video))["sure"]
            cikar = [(b, e) for b, e in cikar if e > k0 and b < k1]
        if cikar:
            toplam = video_bilgi(Path(video))["sure"]
            t2 = duzenle.tut(cikar, toplam)
            if kesit:
                t2 = duzenle.kesisim(t2, [(k0, k1)]); kesit_etiketi = kesit; kesit = None
            tut = duzenle.kesisim(tut, t2) if tut else t2
    if tut and video:
        tut = _sinirlari_oturt(js, video, tut)
    cueler, veri = cueler_json(js, dil, tut)
    global TURKCE
    TURKCE = (dil if dil and dil != "orijinal" else veri.get("dil", "tr")) in ("tr", "az")
    if altyazisiz:
        cueler = []
    if not video:
        raise SystemExit("HATA: --video ile kaynak video dosyasını verin (indirilenler klasöründeki mp4).")
    if not cikti:
        et = f"altyazılı{' ' + dil.upper() if dil and dil != 'orijinal' else ''}"
        if kesit:
            z = lambda s: f"{int(s)//60}.{int(s)%60:02d}"  # noqa: E731
            et = f"{'dikey ' if dikey else ''}klip {z(kesit[0])}-{z(kesit[1]) if kesit[1] else 'son'}" + (f", {dil.upper()}" if dil and dil != "orijinal" else "")
        if tut and kesit_etiketi:
            z = lambda s: f"{int(s)//60}.{int(s)%60:02d}"  # noqa: E731
            et = f"klip {z(kesit_etiketi[0])}-{z(kesit_etiketi[1]) if kesit_etiketi[1] else 'son'}, tekrarsız"
        elif tut:
            et = "kesilmiş" + (", altyazılı" if not altyazisiz else "") + (f" {dil.upper()}" if dil and dil != "orijinal" and not altyazisiz else "")
        cikti = KLASOR / "indirilenler" / f"{re.sub(r'[\\\\/:*?\"<>|]+', ' ', veri.get('baslik') or js.stem).strip()[:80]} [{et}]{' ' + ek if ek else ''}.mp4"
        cikti.parent.mkdir(exist_ok=True)
        n = 2
        temel_ad = cikti.stem
        while cikti.exists():                  # aynı adlı video varsa üzerine yazılmaz (2026-10-25: yayın paketi Shorts'u marka paketinin Shorts'unu ezdi)
            cikti = cikti.with_name(f"{temel_ad}_{n}.mp4"); n += 1
    log(f"[1/4] Kaynak: {Path(video).name}")
    isimler = None
    if isim_bandi:
        import duzenle
        b0 = kesit[0] if kesit else 0.0
        kaydir = (lambda t: (zaman_kaydir(t, tut) if tut else t) - b0 if (not tut or zaman_kaydir(t, tut) is not None) else None)
        isimler = duzenle.isim_bantlari(js, kaydir=kaydir, sure=(kesit[1] - kesit[0]) if kesit and kesit[1] else None)
    siralar = None
    if konusana:
        b0 = kesit[0] if kesit else 0.0
        kd = lambda t: ((zaman_kaydir(t, tut) if tut else t) - b0) if (not tut or zaman_kaydir(t, tut) is not None) else None  # noqa: E731
        siralar = []
        for sg in json.loads(Path(js).read_text(encoding="utf-8"))["segmentler"]:
            b, e = kd(sg["bas"]), kd(sg["bit"])
            if b is None or e is None or e <= 0:
                continue
            if siralar and siralar[-1][2] == sg.get("k") and b - siralar[-1][1] < 1.0:
                siralar[-1][1] = e
            else:
                siralar.append([max(0.0, b), e, sg.get("k")])
    altyazi_yak(video, cueler, cikti, stil, kesit, dikey=dikey, tut=tut, takip=takip, temiz_ses=temiz_ses, broll_ekle=broll_ekle,
                baslik=baslik, baslik_stil=baslik_stil, oran=oran, zoom=zoom, isimler=isimler, studyo=studyo, emoji=emoji, muzik=muzik, siralar=siralar, arka=arka)


if __name__ == "__main__":
    main()

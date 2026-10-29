"""kapak.py - YouTube kapak (thumbnail) taslakları: videodan en iyi yüz karesi + kapak yazısı, marka stilinde.

Kareler ffmpeg ile videonun her yerinden örneklenir (en çok ~120), Mac'in yüz tanıması (Vision
VNDetectFaceCaptureQualityRequest: göz açık, net, iyi ışık) ile puanlanır; birbirinden uzak en iyi 3 kare seçilir.
Kapak yazısı (içerik paketindeki ilk 3 öneri) yüzün karşı tarafına, koyu mavi geçişin üstüne, markanın
kapaklarındaki gibi sarı dolgu + koyu kenar + turuncu parıltıyla yazılır. 1280×720 PNG: <temel>.kapak1.png ...

taslaklar(json_yolu, video, n=3, log) -> [png yolları]
Elle: python kapak.py transkript_x.json video.mp4
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
FFMPEG = "/opt/homebrew/bin/ffmpeg"
W, H = 1280, 720


def _sure(video):
    r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _kareler(video, klasor, sure):
    adim = max(2.0, sure / 120.0)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-vf", f"fps=1/{adim:.2f},scale={W}:-2", "-q:v", "3",
                    str(Path(klasor) / "k_%04d.jpg")], check=False)
    return [(i * adim, p) for i, p in enumerate(sorted(Path(klasor).glob("k_*.jpg")))]


def _puanla(jpg):
    """En iyi yüz: (puan, cx, cy, w, h); yüz yoksa None. Puan = çekim kalitesi × (0,4 + yüz büyüklüğü)."""
    import Quartz
    import Vision
    from Foundation import NSURL
    src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(jpg)), None)
    if src is None:
        return None
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNDetectFaceCaptureQualityRequest.alloc().init()
    Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None).performRequests_error_([req], None)
    en = None
    for o in (req.results() or []):
        b = o.boundingBox(); q = float(o.faceCaptureQuality() or 0)
        alan = b.size.width * b.size.height
        if alan < 0.01:
            continue
        p = q * (0.4 + min(alan, 0.25) * 4)
        if not en or p > en[0]:
            en = (p, b.origin.x + b.size.width / 2, 1 - (b.origin.y + b.size.height / 2), b.size.width, b.size.height)
    return en


def _sec(adaylar, n, sure):
    secilen = []
    ara = max(20.0, sure * 0.12)
    for a in sorted(adaylar, key=lambda x: -x[1][0]):
        if all(abs(a[0] - s[0]) >= ara for s in secilen):
            secilen.append(a)
        if len(secilen) >= n:
            break
    return secilen


def _ciz(kare, yuz, satirlar, cikti, stil="finansal_terapi"):
    import AppKit
    import yakma
    st = yakma.BASLIK_STILLERI[yakma.baslik_stili(stil)]
    rep = yakma._kanvas(W, H)
    im = AppKit.NSImage.alloc().initWithContentsOfFile_(str(kare))
    iw, ih = im.size().width, im.size().height
    cx, cy, fw, fh = yuz[1], yuz[2], yuz[3], yuz[4]
    taraf = "sol" if cx > 0.58 else ("sag" if cx < 0.42 else "alt")
    # Yüzü hedef noktaya getir (alt düzende üst üçte bir, yanlarda karşı taraf); görüntü tuvali her zaman kaplar
    tx, ty, zum = {"alt": (0.5, 0.30, 1.18), "sol": (0.70, 0.42, 1.08), "sag": (0.30, 0.42, 1.08)}[taraf]
    olcek = max(W / iw, H / ih) * zum
    dw, dh = iw * olcek, ih * olcek
    ox = min(0, max(W - dw, tx * W - cx * dw))
    oy = min(0, max(H - dh, H * (1 - ty) - (1 - cy) * dh))
    im.drawInRect_fromRect_operation_fraction_(((ox, oy), (dw, dh)), ((0, 0), (iw, ih)), AppKit.NSCompositingOperationSourceOver, 1.0)
    lacivert = lambda a: AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.03, 0.08, 0.32, a)  # noqa: E731
    if taraf == "alt":
        yuz_alt = H - (oy + (1 - cy - fh / 2) * dh)          # yüzün alt kenarı, üstten piksel
        bos = max(H * 0.26, H - yuz_alt - H * 0.03)
        g = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(lacivert(0.92), lacivert(0.0))
        g.drawInRect_angle_(((0, 0), (W, min(H * 0.6, bos + H * 0.12))), 90)
        kutu = (W * 0.05, H * 0.04, W * 0.9, min(H * 0.44, bos))
    else:
        g = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(lacivert(0.9), lacivert(0.0))
        if taraf == "sol":
            g.drawInRect_angle_(((0, 0), (W * 0.62, H)), 0)
            kutu = (W * 0.04, H * 0.08, W * 0.52, H * 0.84)
        else:
            g.drawInRect_angle_(((W * 0.38, 0), (W * 0.62, H)), 180)
            kutu = (W * 0.44, H * 0.08, W * 0.52, H * 0.84)
    satirlar = [yakma._buyuk(s.strip()) for s in satirlar if s.strip()][:3]
    boyut = 150
    hiza = AppKit.NSCenterTextAlignment if taraf == "alt" else (AppKit.NSLeftTextAlignment if taraf == "sol" else AppKit.NSRightTextAlignment)

    def _font(b):
        f = AppKit.NSFont.systemFontOfSize_weight_(b, AppKit.NSFontWeightBlack)
        try:
            d = f.fontDescriptor().fontDescriptorWithDesign_(AppKit.NSFontDescriptorSystemDesignRounded)
            f = AppKit.NSFont.fontWithDescriptor_size_(d, b) or f
        except Exception:  # noqa: BLE001
            pass
        return f
    while boyut > 40:
        f = _font(boyut)
        en = max(AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: f}).size().width for s in satirlar)
        if en <= kutu[2] and boyut * 1.05 * len(satirlar) <= kutu[3]:
            break
        boyut -= 6
    font = _font(boyut)
    para = AppKit.NSMutableParagraphStyle.alloc().init(); para.setAlignment_(hiza)
    renk = lambda c, a=1.0: AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(c[0], c[1], c[2], a)  # noqa: E731
    satir_yuk = boyut * 1.05
    toplam = satir_yuk * len(satirlar)
    y = kutu[1] + (kutu[3] + toplam) / 2 - satir_yuk if taraf != "alt" else kutu[1] + toplam - satir_yuk
    for s in satirlar:
        r = ((kutu[0], y), (kutu[2], satir_yuk * 1.2))
        if st.get("parlama"):
            gl = AppKit.NSShadow.alloc().init(); gl.setShadowColor_(renk(st["parlama"], 0.95)); gl.setShadowBlurRadius_(boyut * 0.3); gl.setShadowOffset_((0, 0))
            AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font, AppKit.NSParagraphStyleAttributeName: para,
                AppKit.NSForegroundColorAttributeName: renk(st["kenar"]), AppKit.NSShadowAttributeName: gl}).drawInRect_(r)
        AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font, AppKit.NSParagraphStyleAttributeName: para,
            AppKit.NSStrokeColorAttributeName: renk(st["kenar"]), AppKit.NSStrokeWidthAttributeName: 12.0}).drawInRect_(r)
        AppKit.NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: font, AppKit.NSParagraphStyleAttributeName: para,
            AppKit.NSForegroundColorAttributeName: renk(st["renk"])}).drawInRect_(r)
        y -= satir_yuk
    yakma._kaydet(rep, cikti)


def taslaklar(json_yolu, video, n=3, log=print):
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8")); veri = d["veri"]
    marka = veri.get("marka") or ""
    paket = (veri.get("marka_paket") or {}).get(marka) or {}
    yazilar = [[k["satir1"], k["satir2"]] for k in (paket.get("kapak") or [])][:n]
    if not yazilar:
        yazilar = [re.split(r"\s*[|:]\s*", veri.get("baslik") or "")[:2]]
    sure = _sure(video)
    gecici = Path(tempfile.mkdtemp(prefix="kapak_"))
    try:
        log("      Kapak: kareler seçiliyor...")
        kareler = _kareler(video, gecici, sure)
        adaylar = [(t, p, k) for (t, k) in kareler for p in [_puanla(k)] if p]
        secilen = _sec([(t, p) for t, p, _k in adaylar], len(yazilar), sure)
        yol_harita = {t: k for t, _p, k in adaylar}
        temel = json_yolu.with_suffix("")
        out = []
        for i, ((t, yuz), yazi) in enumerate(zip(secilen, yazilar), 1):
            cikti = Path(f"{temel}.kapak{i}.png")
            _ciz(yol_harita[t], yuz, yazi, cikti, yakma.baslik_stili(marka))
            out.append(str(cikti))
        paket["kapak_gorsel"] = [Path(p).name for p in out]
        veri.setdefault("marka_paket", {})[marka] = paket
        json_yolu.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"      Kapak: {len(out)} taslak hazır")
        return out
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(1)
    for p in taslaklar(sys.argv[1], sys.argv[2]):
        print(p)

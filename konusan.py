"""konusan.py - Konuşana geçen kadraj (2026-10-20): iki ya da daha çok kişinin aynı karede olduğu (geniş) çekimlerde, kim konuşuyorsa görüntü
o kişiye yakınlaşır; çok kameralı çekim hissi. Yatay çıktı için (dikeyde kadraj.py zaten tek yüzü izler).

Yöntem: kareler 4/sn örneklenir (480 px), macOS Vision VNDetectFaceLandmarksRequest ile her yüzün kutusu ve dudak açıklığı (iç dudak yüksekliği /
yüz yüksekliği) alınır. Yüzler yatay konuma göre izlere ayrılır. Her konuşma sırasında (konuşmacı ayırmadan) dudak açıklığı en çok DEĞİŞEN iz
konuşan sayılır (konuşan ağız açılıp kapanır). Konuşan kişi geniş çekimde görünüyorsa o sıra boyunca 1/YAKIN oranında ona yakınlaşılır.
Dönüş: [(bas, bit, x, y)] (kaynak piksel; kırpma kutusunun sol üstü) ve kırpma boyutu.
"""
import subprocess
import tempfile
from pathlib import Path

FFMPEG = "/opt/homebrew/bin/ffmpeg"
ORNEK_FPS = 5
YAKIN = 1.6


def _yuz_dudak(jpg):
    """[(cx, cy, fw, fh, dudak)] normalize (sol üst köken)."""
    import Quartz
    import Vision
    from Foundation import NSURL
    url = NSURL.fileURLWithPath_(str(jpg))
    istek = Vision.VNDetectFaceLandmarksRequest.alloc().init()
    isleyici = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    ok, _ = isleyici.performRequests_error_([istek], None)
    out = []
    for g in (istek.results() or []):
        bb = g.boundingBox()
        x, y, w, h = bb.origin.x, bb.origin.y, bb.size.width, bb.size.height
        dudak = 0.0
        lm = g.landmarks()
        il = lm.innerLips() if lm else None
        if il and il.pointCount() >= 4:
            ys = [il.normalizedPoints()[i].y for i in range(il.pointCount())]
            dudak = max(ys) - min(ys)                      # yüz kutusuna göre normalize
        out.append((x + w / 2, 1 - (y + h / 2), w, h, dudak))
    return out


def _yuzler(jpg):
    """[(x0, y0, x1, y1)] normalize, sol üst köken; yan profili de yakalayan yüz kutusu dedektörü."""
    import Vision
    from Foundation import NSURL
    istek = Vision.VNDetectFaceRectanglesRequest.alloc().init()
    try:
        istek.setRevision_(3)
    except Exception:  # noqa: BLE001
        pass
    isleyici = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(jpg)), {})
    isleyici.performRequests_error_([istek], None)
    out = []
    for g in (istek.results() or []):
        bb = g.boundingBox()
        out.append((bb.origin.x, 1 - bb.origin.y - bb.size.height, bb.origin.x + bb.size.width, 1 - bb.origin.y))
    return out


def plan(video, bas, sure, w, h, siralar, log=print):
    """siralar: [(bas, bit, konusmaci)] videonun (kesit sonrası) zamanında. Döner (dilimler, cw, ch).
    Kimin konuştuğu: yüz + çene bölgesindeki hareket (ardışık kareler farkı); konuşmacı → yüz izi eşleşmesi tüm sıraların oylamasıyla."""
    import numpy as np
    from PIL import Image
    cw, ch = int(w / YAKIN) // 2 * 2, int(h / YAKIN) // 2 * 2
    gecici = Path(tempfile.mkdtemp(prefix="konusan_"))
    subprocess.run([FFMPEG, "-y", "-v", "error"] + (["-ss", f"{bas:.3f}"] if bas else []) + ["-i", str(video), "-t", f"{sure:.3f}",
                    "-vf", f"fps={ORNEK_FPS},scale=960:-2", str(gecici / "k_%05d.jpg")], capture_output=True)
    kareler = sorted(gecici.glob("k_*.jpg"))
    orn, onceki = [], None                                 # (t, [(kova, cx, cy, hareket)])
    for i, k in enumerate(kareler):
        try:
            yuzler = _yuzler(k)
            gri = np.asarray(Image.open(k).convert("L"), dtype=np.float32)
        except Exception:  # noqa: BLE001
            orn.append((i / ORNEK_FPS, [])); continue
        H, W = gri.shape
        kayit = []
        for x0, y0, x1, y1 in yuzler:
            fy = y1 - y0
            bx0, bx1 = int(max(0, x0 - 0.1 * (x1 - x0)) * W), int(min(1, x1 + 0.1 * (x1 - x0)) * W)
            by0, by1 = int(max(0, y0 + 0.45 * fy) * H), int(min(1, y1 + 0.35 * fy) * H)   # ağız ve çene
            hr = float(np.mean(np.abs(gri[by0:by1, bx0:bx1] - onceki[by0:by1, bx0:bx1]))) if onceki is not None and by1 > by0 and bx1 > bx0 else 0.0
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            kayit.append((round(cx * 4) / 4, cx, cy, hr))
        orn.append((i / ORNEK_FPS, kayit)); onceki = gri
        k.unlink(missing_ok=True)
    try:
        gecici.rmdir()
    except OSError:
        pass
    genis = sum(1 for _t, y in orn if len(y) >= 2) / max(1, len(orn))
    log(f"      Geniş çekim oranı %{int(genis * 100)} ({len(orn)} kare)")
    if genis < 0.15:
        log("      Konuşana geçen kadraj: geniş çekim az; dokunulmadı")
        return [], cw, ch
    oy = {}                                                # konuşmacı → iz → toplam hareket (yalnız geniş karelerde)
    for b, e, kk in siralar:
        for t, y in orn:
            if b <= t <= e and len(y) >= 2:
                for kova, _cx, _cy, hr in y:
                    oy.setdefault(kk, {}).setdefault(kova, []).append(hr)
    esle = {}
    for kk, izler in oy.items():
        ort = {kv: sum(v) / len(v) for kv, v in izler.items() if len(v) >= 4}
        if len(ort) >= 2:
            sirali = sorted(ort.items(), key=lambda x: -x[1])
            if sirali[0][1] > 1.12 * sirali[1][1]:
                esle[kk] = sirali[0][0]
    log(f"      Konuşmacı → konum eşleşmesi: {esle or 'bulunamadı'}")
    dilimler = []
    for b, e, kk in siralar:
        if e - b < 1.0 or kk not in esle:
            continue
        ilgili = [(cx, cy) for t, y in orn if b <= t <= e and len(y) >= 2 for kova, cx, cy, _hr in y if kova == esle[kk]]
        if len(ilgili) < max(2, 0.4 * (e - b) * ORNEK_FPS):
            continue
        cx = sum(x for x, _ in ilgili) / len(ilgili); cy = sum(y for _, y in ilgili) / len(ilgili)
        x = int(min(max(cx * w - cw / 2, 0), w - cw)) // 2 * 2
        y = int(min(max(cy * h - ch * 0.42, 0), h - ch)) // 2 * 2
        if e - b <= 12:
            dilimler.append((b, e, x, y))
        else:                                              # uzun konuşma: ~7 sn yakın, ~3 sn geniş (çok kamera ritmi), yakın çekimle bitir
            t = b
            while t < e - 1.0:
                dilimler.append((t, min(e, t + 7.0), x, y)); t += 10.0
    log(f"      Konuşana geçen kadraj: {len(dilimler)} konuşma sırasında yakın çekim")
    return dilimler, cw, ch


def filtre(dilimler, cw, ch, w, h, klasor):
    """[v] girişini alan, konuşana yakın çekim dilimlerini bindiren filtre parçası ve sendcmd dosyası. Döner (ön_filtre, son_etiket) ya da ('', None)."""
    if not dilimler:
        return "", None
    yol = Path(klasor) / "konusan.cmd"
    yol.write_text("\n".join(f"{b:.3f} crop@kz x {x}, crop@kz y {y};" for b, _e, x, y in dilimler) + "\n", encoding="utf-8")
    ac = "+".join(f"between(t,{b:.2f},{e:.2f})" for b, e, _x, _y in dilimler)
    x0, y0 = dilimler[0][2], dilimler[0][3]
    return (f"split=2[kg][kz0];[kz0]sendcmd=f='{yol}',crop@kz={cw}:{ch}:{x0}:{y0},scale={w}:{h}:flags=lanczos[kz];"
            f"[kg][kz]overlay=0:0:enable='{ac}'"), True

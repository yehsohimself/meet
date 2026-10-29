"""kadraj.py - Dikey (9:16) klip için yüz takipli kadraj: kırpma penceresi konuşan kişiyi izler.

Mac'in yerleşik yüz tanıması (Vision, pyobjc) ile saniyede 4 kare örneklenir, ana yüz seçilir (en büyük; önceki
kareye yakın olan tercih edilir), yumuşatılır (ölü bölge + üstel ortalama), sahne değişiminde sıfırlanır.
İki kişi uzun süre birlikte görünüyorsa "bölünmüş ekran" (üst/alt) düzeni seçilir.

plan = kadraj_plani(video, bas, sure, log)  →  {"duzen": "tek"|"bolunmus"|"orta", "cw": kırpma genişliği,
   "komutlar": sendcmd satırları, "filtre": ffmpeg filtre parçası ("[0:v]...[v]" içine konacak), "yuz_orani": ...}
ffmpeg: sendcmd ile crop filtresinin x/y değerleri zaman içinde güncellenir (komut dosyası geçici klasörde).
"""
import os
import subprocess
import tempfile
from pathlib import Path

FFMPEG = "/opt/homebrew/bin/ffmpeg"
ORNEK_FPS = 4
KUCUK_W = 480


def _yuzler(jpg):
    """Bir karedeki yüzler: [(cx, cy, w, h)] 0-1 normalize (sol üst köşe orijin)."""
    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except Exception:  # noqa: BLE001
        return None
    src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(jpg)), None)
    if src is None:
        return []
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNDetectFaceRectanglesRequest.alloc().init()
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    h.performRequests_error_([req], None)
    out = []
    for o in (req.results() or []):
        b = o.boundingBox()                                  # Vision: sol ALT köşe orijinli
        x, y, w, hh = b.origin.x, b.origin.y, b.size.width, b.size.height
        if w * hh < 0.0008:
            continue
        out.append((x + w / 2, 1 - (y + hh / 2), w, hh))
    return out


def _kareler(video, bas, sure, klasor, log):
    komut = [FFMPEG, "-v", "error", "-y"]
    if bas:
        komut += ["-ss", f"{bas:.3f}"]
    komut += ["-t", f"{sure:.3f}", "-i", str(video), "-vf", f"fps={ORNEK_FPS},scale={KUCUK_W}:-2", "-q:v", "6", str(klasor / "k%05d.jpg")]
    subprocess.run(komut, check=False, capture_output=True)
    return sorted(klasor.glob("k*.jpg"))


def _sahneler(video, bas, sure):
    """Sahne değişim zamanları (kesit başına göre)."""
    komut = [FFMPEG, "-v", "info", "-nostats"]
    if bas:
        komut += ["-ss", f"{bas:.3f}"]
    komut += ["-t", f"{sure:.3f}", "-i", str(video), "-vf", f"scale={KUCUK_W}:-2,select='gt(scene,0.35)',showinfo", "-f", "null", "-"]
    r = subprocess.run(komut, capture_output=True, text=True)
    import re
    return [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", r.stderr)]


def kadraj_plani(video, bas, sure, w, h, log=print, oran=9 / 16):
    """Kırpma planı. w,h: kaynak boyut (çift); oran: hedef en/boy (9/16 dikey, 1 kare, 0.8 = 4:5). Döner sözlük; yüz bulunamazsa duzen='orta'."""
    cw = int(round(h * oran)); cw -= cw % 2
    if cw >= w:
        return {"duzen": "orta", "cw": w, "komutlar": [], "filtre": "", "yuz_orani": 0.0}
    gecici = Path(tempfile.mkdtemp(prefix="kadraj_"))
    kareler = _kareler(video, bas, sure, gecici, log)
    if not kareler:
        return {"duzen": "orta", "cw": cw, "komutlar": [], "filtre": f"crop={cw}:{h}:(iw-{cw})/2:0,", "yuz_orani": 0.0}
    orn = []
    for i, k in enumerate(kareler):
        y = _yuzler(k)
        if y is None:                                        # Vision yok
            return {"duzen": "orta", "cw": cw, "komutlar": [], "filtre": f"crop={cw}:{h}:(iw-{cw})/2:0,", "yuz_orani": 0.0}
        orn.append((i / ORNEK_FPS, y))
        try:
            k.unlink()
        except Exception:  # noqa: BLE001
            pass
    try:
        os.rmdir(gecici)
    except Exception:  # noqa: BLE001
        pass
    yuzlu = sum(1 for _t, y in orn if y)
    yuz_orani = yuzlu / max(1, len(orn))
    if yuz_orani < 0.25:
        log(f"      Yüz az görünüyor (%{int(yuz_orani * 100)}); ortadan kırpılıyor")
        return {"duzen": "orta", "cw": cw, "komutlar": [], "filtre": f"crop={cw}:{h}:(iw-{cw})/2:0,", "yuz_orani": yuz_orani}
    sahneler = _sahneler(video, bas, sure)
    # İki kişi düzeni: örneklerin ≥%55'inde iki yüz ve aralarındaki yatay mesafe kırpma genişliğinden büyükse
    ikili = sum(1 for _t, y in orn if len(y) >= 2 and abs(sorted(y, key=lambda f: -f[2] * f[3])[0][0] - sorted(y, key=lambda f: -f[2] * f[3])[1][0]) * w > cw * 0.9)
    if oran < 0.6 and ikili / max(1, len(orn)) >= 0.55:          # bölünmüş ekran yalnız dikeyde anlamlı
        return _bolunmus_plan(orn, sahneler, w, h, cw, yuz_orani, log)
    # Tek kişi: ana yüz izi
    merkezler, onceki = [], None
    for t, y in orn:
        if not y:
            merkezler.append((t, None)); continue
        if onceki is not None:
            y = sorted(y, key=lambda f: (abs(f[0] - onceki) > 0.15, -f[2] * f[3]))   # öncekine yakın ve büyük olan
        else:
            y = sorted(y, key=lambda f: -f[2] * f[3])
        onceki = y[0][0]
        merkezler.append((t, y[0][0]))
    xs = _yumusat(merkezler, sahneler, w, cw)
    komutlar = [f"{t:.3f} crop@k x {x};" for t, x in xs]
    return {"duzen": "tek", "cw": cw, "komutlar": komutlar, "filtre": f"crop@k={cw}:{h}:{xs[0][1] if xs else (w - cw) // 2}:0,", "yuz_orani": yuz_orani}


def _yumusat(merkezler, sahneler, w, cw, olu_bolge=0.04, alfa=0.25):
    """Yüz merkezini (0-1) kırpma x'ine çevirir; ölü bölge + üstel yumuşatma; sahne değişiminde anında atlar."""
    xs, hedef, cur = [], None, None
    sahne_i = 0
    son_gecerli = 0.5
    for t, cx in merkezler:
        if cx is None:
            cx = son_gecerli
        else:
            son_gecerli = cx
        sahne = False
        while sahne_i < len(sahneler) and sahneler[sahne_i] <= t:
            sahne_i += 1; sahne = True
        if hedef is None or sahne or abs(cx - hedef) > olu_bolge:
            hedef = cx
        if cur is None or sahne:
            cur = hedef
        else:
            cur = cur + alfa * (hedef - cur)
        x = int(round(cur * w - cw / 2)); x = max(0, min(w - cw, x)); x -= x % 2
        if not xs or xs[-1][1] != x:
            xs.append((t, x))
    return xs or [(0.0, (w - cw) // 2)]


def _bolunmus_plan(orn, sahneler, w, h, cw, yuz_orani, log):
    """İki kişi: üst/alt yarı; her yarı cw×(h/2) kaynak bölgesi, kendi yüzünü izler (sol kişi üstte)."""
    log("      İki kişi görünüyor; bölünmüş ekran düzeni")
    hh = h // 2; hh -= hh % 2
    sol, sag = [], []
    for t, y in orn:
        if len(y) >= 2:
            a, b = sorted(sorted(y, key=lambda f: -f[2] * f[3])[:2], key=lambda f: f[0])
            sol.append((t, a[0], a[1])); sag.append((t, b[0], b[1]))
        else:
            sol.append((t, None, None)); sag.append((t, None, None))
    komutlar = []
    ilk = {}
    for ad, dizi in (("a", sol), ("b", sag)):
        xs = _yumusat([(t, cx) for t, cx, _cy in dizi], sahneler, w, cw)
        ys = _yumusat([(t, cy) for t, _cx, cy in dizi], sahneler, h, hh)
        ilk[ad] = (xs[0][1], ys[0][1])
        komutlar += [f"{t:.3f} crop@{ad} x {x};" for t, x in xs] + [f"{t:.3f} crop@{ad} y {y};" for t, y in ys]
    komutlar.sort(key=lambda s: float(s.split()[0]))
    filtre = (f"split=2[s0][s1];[s0]crop@a={cw}:{hh}:{ilk['a'][0]}:{ilk['a'][1]}[ca];[s1]crop@b={cw}:{hh}:{ilk['b'][0]}:{ilk['b'][1]}[cb];"
              f"[ca][cb]vstack=inputs=2,")
    return {"duzen": "bolunmus", "cw": cw, "komutlar": komutlar, "filtre": filtre, "yuz_orani": yuz_orani, "bolunmus": True}


def komut_dosyasi(plan, klasor):
    """sendcmd dosyasını yazar; filtre başına eklenecek 'sendcmd=f=...,' parçasını döner."""
    if not plan.get("komutlar"):
        return ""
    yol = Path(klasor) / "kadraj.cmd"
    yol.write_text("\n".join(plan["komutlar"]) + "\n", encoding="utf-8")
    return f"sendcmd=f='{yol}',"


if __name__ == "__main__":
    import sys, json
    v = Path(sys.argv[1]); bas = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0; sure = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(v)], capture_output=True, text=True)
    w, h = [int(x) for x in r.stdout.strip().split(",")[:2]]
    p = kadraj_plani(v, bas, sure, w, h)
    print(json.dumps({k: (v_ if k != "komutlar" else f"{len(v_)} komut") for k, v_ in p.items()}, ensure_ascii=False))
    print("\n".join(p["komutlar"][:8]))

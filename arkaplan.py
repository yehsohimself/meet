"""arkaplan.py - Arka planı bulanıklaştırma ya da değiştirme (2026-10-20). macOS Core Image CIPersonSegmentation (kişi maskesi, ek kurulum yok)
ile her karede kişi ayrılır; arka plan bulanık (portre modu gibi) ya da koyu stüdyo zemini olur. Kareler ffmpeg ile ham olarak okunup yazılır.

isle(girdi, bas, sure, cikti, mod="bulanik"|"koyu", log): sesi aynen taşır. Hız (M4, 1080p): ölçüme göre loga yazar.
"""
import subprocess
import time
from pathlib import Path

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"


def _bilgi(yol):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(yol)],
                       capture_output=True, text=True)
    w, h, fr = r.stdout.strip().split(",")[:3]
    a, b = fr.split("/") if "/" in fr else (fr, 1)
    return int(w), int(h), float(a) / float(b or 1)


def isle(girdi, bas, sure, cikti, mod="bulanik", log=print):
    import Quartz
    from Foundation import NSData
    w, h, fps = _bilgi(girdi)
    w -= w % 2; h -= h % 2
    oku = subprocess.Popen([FFMPEG, "-v", "error"] + (["-ss", f"{bas:.3f}"] if bas else []) + ["-i", str(girdi), "-t", f"{sure:.3f}",
                           "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgra", "-"], stdout=subprocess.PIPE)
    yaz = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-r", f"{fps:.3f}", "-i", "-"]
                           + (["-ss", f"{bas:.3f}"] if bas else []) + ["-i", str(girdi), "-t", f"{sure:.3f}", "-map", "0:v", "-map", "1:a?",
                           "-c:v", "h264_videotoolbox", "-b:v", "10M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(cikti)],
                           stdin=subprocess.PIPE)
    ctx = Quartz.CIContext.contextWithOptions_(None)
    renk = Quartz.CGColorSpaceCreateDeviceRGB()
    boy = w * h * 4
    segm = Quartz.CIFilter.filterWithName_("CIPersonSegmentation")
    segm.setValue_forKey_(1, "inputQualityLevel")                      # 0 hızlı, 1 dengeli, 2 kaliteli
    gri = Quartz.CIFilter.filterWithName_("CIColorMatrix")
    for ad in ("inputRVector", "inputGVector", "inputBVector"):
        gri.setValue_forKey_(Quartz.CIVector.vectorWithX_Y_Z_W_(1, 0, 0, 0), ad)
    gri.setValue_forKey_(Quartz.CIVector.vectorWithX_Y_Z_W_(0, 0, 0, 1), "inputAVector")
    zemin = None
    if mod == "koyu":
        g = Quartz.CIFilter.filterWithName_("CIRadialGradient")
        g.setValue_forKey_(Quartz.CIVector.vectorWithX_Y_(w / 2, h * 0.55), "inputCenter")
        g.setValue_forKey_(min(w, h) * 0.15, "inputRadius0"); g.setValue_forKey_(max(w, h) * 0.75, "inputRadius1")
        g.setValue_forKey_(Quartz.CIColor.colorWithRed_green_blue_(0.20, 0.21, 0.26), "inputColor0")
        g.setValue_forKey_(Quartz.CIColor.colorWithRed_green_blue_(0.04, 0.04, 0.06), "inputColor1")
        zemin = g.outputImage().imageByCroppingToRect_(((0, 0), (w, h)))
    t0, n = time.time(), 0
    while True:
        ham = oku.stdout.read(boy)
        if not ham or len(ham) < boy:
            break
        resim = Quartz.CIImage.imageWithBitmapData_bytesPerRow_size_format_colorSpace_(
            NSData.dataWithBytes_length_(ham, boy), w * 4, (w, h), Quartz.kCIFormatBGRA8, renk)
        segm.setValue_forKey_(resim, "inputImage")
        maske = segm.outputImage()
        me = maske.extent()
        maske = maske.imageByApplyingTransform_(Quartz.CGAffineTransformMakeScale(w / me.size.width, h / me.size.height))
        gri.setValue_forKey_(maske, "inputImage")                     # maske yalnız kırmızı kanalda gelir; gri tona çevir
        maske = gri.outputImage().imageByClampingToExtent().imageByApplyingGaussianBlurWithSigma_(1.5).imageByCroppingToRect_(((0, 0), (w, h)))
        if zemin is None:
            arka = resim.imageByClampingToExtent().imageByApplyingGaussianBlurWithSigma_(min(w, h) * 0.018).imageByCroppingToRect_(((0, 0), (w, h)))
        else:
            arka = zemin
        harman = Quartz.CIFilter.filterWithName_("CIBlendWithMask")
        harman.setValue_forKey_(resim, "inputImage"); harman.setValue_forKey_(arka, "inputBackgroundImage"); harman.setValue_forKey_(maske, "inputMaskImage")
        cikis = bytearray(boy)
        ctx.render_toBitmap_rowBytes_bounds_format_colorSpace_(harman.outputImage(), cikis, w * 4, ((0, 0), (w, h)), Quartz.kCIFormatBGRA8, renk)
        yaz.stdin.write(bytes(cikis)); n += 1
        if n % 150 == 0:
            log(f"      Arka plan: {n} kare ({n / (time.time() - t0):.0f} kare/sn)")
    yaz.stdin.close(); yaz.wait(); oku.wait()
    log(f"      Arka plan {'bulanıklaştırıldı' if mod == 'bulanik' else 'değiştirildi'}: {n} kare, {time.time() - t0:.0f} sn")
    return Path(cikti) if Path(cikti).exists() and n else None

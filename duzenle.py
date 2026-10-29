"""duzenle.py - Studio'nun video düzenleme yardımcıları (2026-10-20; kullanıcı "hızlı kazanımları ekle").

- tekrar_alimlar(json): konuşmacı aynı cümleyi birden çok kez denediyse (yanlış başlama, "baştan alıyorum"), Claude metinden bulur;
  YALNIZCA en son/en iyi alım kalır. Dönüş: çıkarılacak aralıklar [(bas, bit)]; tut() ile tutulacak aralıklara çevrilir.
- yakinlastirma(cueler, sure): cümle sınırlarında dönüşümlü hafif yakınlaştırma (1,0 → 1,10), kısa ve vurgulu cümlelerde 1,18.
  Reels/Shorts'taki "punch-in" kurgusu; konuşan kafa videosunu canlandırır. Dönüş: [(bas, bit, olcek)].
- isim_bantlari(json, tut): her adlandırılmış konuşmacının İLK konuşmasında 3,5 sn ad bandı. "Konuşmacı N" etiketleri atlanır.
- studyo_sesi(video, bas, sure, klasor): Demucs ile konuşma/arka plan ayrılır; konuşma netleştirilip (alçak frekans kesme, hafif sıkıştırma,
  yükseklik dengesi) arka plan %25'e indirilerek yeniden karıştırılır (Adobe Podcast "Enhance" benzeri). Ayırma motoru dublajla ortak (.venv-dublaj).
"""
import json
import subprocess
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"
TTS_PY = KLASOR / ".venv-dublaj" / "bin" / "python"


def _seg(json_yolu):
    d = json.loads(Path(json_yolu).read_text(encoding="utf-8"))
    return d["veri"], d["segmentler"]


def tekrar_alimlar(json_yolu, log=print):
    """Claude ile tekrar alımları bulur; çıkarılacak [(bas, bit)] döner (bulamazsa boş)."""
    _v, seg = _seg(json_yolu)
    if len(seg) < 3:
        return []
    try:
        import claude_yaz
        if not claude_yaz.hazir():
            log("      Tekrar alım temizliği atlandı (Claude yok)")
            return []
        satirlar = "\n".join(f"{i + 1}. [{s['bas']:.1f}-{s['bit']:.1f}] {s['metin']}" for i, s in enumerate(seg))
        cevap = claude_yaz.sor_json(
            "Aşağıda bir videonun numaralı cümleleri var (zamanlarıyla). Konuşmacının AYNI şeyi birden fazla kez söylemeye çalıştığı yerleri bul: "
            "yarım bırakıp baştan aldığı, takılıp tekrar ettiği, 'baştan alıyorum / bir daha söyleyeyim' dediği denemeler. Her grupta YALNIZCA son "
            "ve tam alım kalsın; önceki denemelerin numaralarını ver. Bilinçli tekrarları (vurgu için tekrar, nakarat, soru-cevap) ve farklı içerikli "
            "cümleleri ASLA seçme. Emin değilsen seçme. "
            'JSON: {"sil": [numaralar], "neden": "kısa"}\n\n' + satirlar)
        sil = sorted({int(n) - 1 for n in (cevap or {}).get("sil", []) if str(n).isdigit() and 0 < int(n) <= len(seg)})
    except Exception as e:  # noqa: BLE001
        log(f"      Tekrar alım temizliği yapılamadı: {str(e)[:80]}")
        return []
    if sil:
        log(f"      {len(sil)} tekrar alım çıkarılacak: " + "; ".join(seg[i]["metin"][:40] for i in sil[:4]))
    else:
        log("      Tekrar alım bulunmadı")
    return [(max(0.0, seg[i]["bas"] - 0.05), seg[i]["bit"] + 0.05) for i in sil]


def tut(cikar, sure):
    """Çıkarılacak aralıkları tutulacak aralıklara çevirir (sıralı, birleşik)."""
    cikar = sorted(cikar)
    out, t = [], 0.0
    for b, e in cikar:
        if b > t + 0.05:
            out.append((t, b))
        t = max(t, e)
    if sure > t + 0.05:
        out.append((t, sure))
    return out


def kesisim(a, b):
    """İki tutma listesinin kesişimi."""
    out = []
    for x0, x1 in a:
        for y0, y1 in b:
            s, e = max(x0, y0), min(x1, y1)
            if e - s > 0.05:
                out.append((s, e))
    return sorted(out)


def yakinlastirma(cueler, sure, en_cok=40):
    """Cümle sınırlarında dönüşümlü yakınlaştırma planı [(bas, bit, olcek)]; cueler videonun (kesit sonrası) zamanında."""
    plan, sira = [], 0
    for c in cueler:
        b, e = c["bas"], c["bit"]
        if e - b < 1.2:
            continue
        kelime = len((c.get("metin") or "").split())
        vurgu = (c.get("metin") or "").rstrip().endswith(("!", "?")) or kelime <= 5
        sira += 1
        if vurgu:
            plan.append((b, e, 1.18))
        elif sira % 2 == 0:
            plan.append((b, e, 1.10))
        if len(plan) >= en_cok:
            break
    return [(max(0.0, b), min(sure, e), z) for b, e, z in plan if e > b]


def olcek_ifadesi(plan):
    """ffmpeg zaman ifadesi: aralıklarda ölçek, dışında 1."""
    if not plan:
        return "1"
    ifade = "1"
    for b, e, z in reversed(plan):
        ifade = f"if(between(t,{b:.2f},{e:.2f}),{z:.2f},{ifade})"
    return ifade


def isim_bantlari(json_yolu, kaydir=None, sure=None):
    """[(bas, bit, ad)]: her adlandırılmış konuşmacının İLK ≥1,8 sn'lik konuşma sırasında (aynı kişinin ardışık cümleleri birleşir), yalnız o
    kişi konuşurken (en çok 4 sn) ad bandı. Konuşma sırası dışına taşmaz, bantlar çakışmaz. "Konuşmacı N" etiketleri atlanır."""
    v, seg = _seg(json_yolu)
    etiket = v.get("etiket") or {}
    siralar = []                                     # konuşma sıraları: [k, bas, bit]
    for s in seg:
        if siralar and siralar[-1][0] == s.get("k") and s["bas"] - siralar[-1][2] < 1.0:
            siralar[-1][2] = s["bit"]
        else:
            siralar.append([s.get("k"), s["bas"], s["bit"]])
    gorulen, out, son = set(), [], -1.0
    for k, b0, e0 in siralar:
        ad = etiket.get(k, "")
        if not ad or ad.startswith("Konuşmacı") or ad in gorulen:
            continue
        b = kaydir(b0) if kaydir else b0
        e = kaydir(e0) if kaydir else e0
        if b is None or e is None or b < 0 or (sure is not None and b > sure - 1.5):
            continue
        b = max(b, son + 0.2)
        e = min(e, b + 4.0, (sure or 1e9))
        if e - b < 1.8:
            continue
        gorulen.add(ad)
        out.append((b, e, ad)); son = e
    return out


def isim_png(w, h, ad, yol):
    """Alt-sol köşede yarı saydam koyu bant, beyaz kalın ad (AppKit, şeffaf PNG)."""
    import AppKit
    from yakma import _kanvas, _font
    rep = _kanvas(w, h)
    boyut = max(16, round(min(w, h) * 0.038))
    font = _font(boyut)
    nit = {AppKit.NSFontAttributeName: font, AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor()}
    yazi = AppKit.NSAttributedString.alloc().initWithString_attributes_(ad, nit)
    tw, th = yazi.size().width, yazi.size().height
    pad = boyut * 0.6
    x = w * (0.06 if w > h else 0.08)
    y = h * (0.30 if h > w else 0.26)                 # altyazı bölgesinin üstünde (altyazı alttan ~%8-22)
    AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.05, 0.72).set()
    AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((x, y), (tw + 2 * pad, th + pad)), boyut * 0.3, boyut * 0.3).fill()
    AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.18, 0.36, 1.0, 1.0).set()               # Studio mavisi şerit
    AppKit.NSBezierPath.fillRect_(((x, y), (boyut * 0.18, th + pad)))
    yazi.drawAtPoint_((x + pad, y + pad * 0.5))
    from yakma import _kaydet
    _kaydet(rep, yol)


def studyo_sesi(video, bas, sure, klasor, log=print):
    """Netleştirilmiş ses wav'ı (konuşma öne, arka plan %25); olmazsa None."""
    klasor = Path(klasor)
    wav = klasor / "studyo_ham.wav"
    komut = [FFMPEG, "-y", "-v", "error"] + (["-ss", f"{bas:.3f}"] if bas else []) + ["-i", str(video)] + (["-t", f"{sure:.3f}"] if sure else []) + \
        ["-vn", "-ac", "2", "-ar", "44100", str(wav)]
    subprocess.run(komut, capture_output=True)
    if not wav.exists() or not TTS_PY.exists():
        return None
    t = time.time()
    for cihaz in ("mps", "cpu"):
        r = subprocess.run(["/usr/bin/nice", "-n", "5", str(TTS_PY), "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-d", cihaz,
                            "-o", str(klasor / "ayrim"), str(wav)], capture_output=True, text=True)
        k = klasor / "ayrim" / "htdemucs" / "studyo_ham"
        if r.returncode == 0 and (k / "vocals.wav").exists():
            break
    else:
        log("      Stüdyo sesi yapılamadı (ayrım başarısız)")
        return None
    cikti = klasor / "studyo.wav"
    fc = ("[0:a]highpass=f=80,afftdn=nf=-25,acompressor=threshold=-20dB:ratio=3:attack=10:release=150,equalizer=f=3000:t=q:w=1.2:g=2.5,"
          "loudnorm=I=-16:TP=-1.5:LRA=9[v];[1:a]volume=0.25[b];[v][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[o]")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(k / "vocals.wav"), "-i", str(k / "no_vocals.wav"), "-filter_complex", fc, "-map", "[o]", str(cikti)],
                   capture_output=True)
    if cikti.exists():
        log(f"      Stüdyo sesi hazır ({time.time() - t:.0f} sn)")
        return cikti
    return None


def emoji_plani(cueler, sure, log=print):
    """Anahtar kelimelere emoji (Submagic tarzı): Claude her ~6 sn'de en çok bir vurgulu kelime seçer → [(t, emoji)] (videonun zamanında)."""
    kel = []
    for c in cueler:
        for b, _e, w in (c.get("kelimeler") or []):
            if 0 <= b < sure:
                kel.append((b, w))
    if len(kel) < 6:
        return []
    try:
        import claude_yaz
        if not claude_yaz.hazir():
            return []
        satir = " ".join(f"{i}:{w}" for i, (_b, w) in enumerate(kel))
        cevap = claude_yaz.sor_json(
            "Aşağıda bir kısa videonun kelimeleri numaralı (numara:kelime). Ekranda kelimenin üstünde küçük bir emoji belirecek (Reels/TikTok altyazı "
            "tarzı). Anlamı en güçlü, somut ya da duygulu kelimeleri seç: ortalama her 15-20 kelimede EN ÇOK bir tane, toplamda en çok "
            f"{max(1, int(sure / 6))}. Her biri için o kelimeyi en iyi anlatan TEK bir emoji ver. Bağlaç, zamir, sıradan fiillere emoji koyma; "
            'uygun kelime yoksa boş liste ver. JSON: {"secim": [{"i": numara, "emoji": "😀"}]}\n\n' + satir)
        secim = (cevap or {}).get("secim") or []
    except Exception as e:  # noqa: BLE001
        log(f"      Emoji seçilemedi: {str(e)[:80]}")
        return []
    out, son = [], -9.0
    for x in secim:
        try:
            i = int(x.get("i"))
        except (TypeError, ValueError):
            continue
        em = (x.get("emoji") or "").strip()[:4]
        if 0 <= i < len(kel) and em and kel[i][0] - son >= 2.5:
            out.append((kel[i][0], em)); son = kel[i][0]
    log(f"      Emoji: {' '.join(e for _t, e in out) or 'yok'}")
    return out


def emoji_png(w, h, emoji, yol):
    """Tek emoji, altyazının üstünde ortada; Apple Color Emoji (AppKit, şeffaf PNG)."""
    import AppKit
    from yakma import _kanvas, _kaydet
    rep = _kanvas(w, h)
    boyut = round(min(w, h) * 0.19)
    font = AppKit.NSFont.fontWithName_size_("Apple Color Emoji", boyut) or AppKit.NSFont.systemFontOfSize_(boyut)
    golge = AppKit.NSShadow.alloc().init()
    golge.setShadowColor_(AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.45)); golge.setShadowBlurRadius_(boyut * 0.12); golge.setShadowOffset_((0, -boyut * 0.04))
    yazi = AppKit.NSAttributedString.alloc().initWithString_attributes_(emoji, {AppKit.NSFontAttributeName: font, AppKit.NSShadowAttributeName: golge})
    sz = yazi.size()
    yazi.drawAtPoint_(((w - sz.width) / 2, h * (0.37 if h > w else 0.34)))
    _kaydet(rep, yol)

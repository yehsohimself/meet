"""Metinden kesmede kesim sınırlarını sesin sessizlik haritasına oturtur (2026-10-29).

Neden: Studio'nun Kes, Metinden kurgu ve duraksama temizliği tutulacak aralıkları yazıya dökmenin paragraf/kelime
zamanlarından hesaplıyordu. O zamanlar ±100-300 ms kayar (Whisper duraksamayı önceki kelimeye katar, paragraf sonunu
erken bitirir); kesim kelimenin ortasına düşüp sözün başı ya da sonu kırpılıyordu. Açık kaynak BMad Manticore'un
(MIT, skills/mc-cut: analyze_audio.py, snap_spans.py) ilkesi: METİN neyin söylendiğini, SES nerede kesileceğini söyler.
Sessizlikte duran bir kesim kelime kırpamaz.

ses_haritasi(medya): ffmpeg silencedetect (-30 dB, 0,10 sn; konuşmanın altında müzik varsa -25 dB) → sessiz aralıklar,
dosya imzasıyla önbellekte. oturt(tut, sessizlik, kelimeler): her tutulan aralığın kenarını, tutulan son kelimeyle
çıkarılan ilk kelime arasındaki sessizliğe taşır; konuşmanın yanında en çok PAY kadar sessizlik bırakır (nefes). Sessizlik
yoksa iki kelimenin arasına keser; yumuşatmayı (_kes_birlestir, 30 ms) bu durumlar için de uygular.
konusma_bosluklari(): seste konuşma var ama hiçbir kelimeye düşmeyen kısa parçalar (çoğu 'ee/ıı'; dolgu.py kullanır)."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
ONBELLEK = KLASOR / ".onbellek" / "ses_haritasi"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
ESIK_DB = -30.0
EN_KISA = 0.10          # haritanın çözünürlüğü; kesim eşiği değil (kelime arası 0,1-0,2 sn boşluklar da gerekli)
PAY = 0.12              # konuşmanın yanında bırakılan sessizlik (nefes payı)
ARA = 0.15              # kelime zamanının kayabileceği kadar pencere genişler
BUTCE = 0.5             # bir kenar özgün yerinden en çok bu kadar oynar (aradaki yazısız ses, müzik korunur)
_BAS = re.compile(r"silence_start:\s*(-?[\d.]+)")
_BIT = re.compile(r"silence_end:\s*(-?[\d.]+)")


def _sure(medya):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nokey=1:noprint_wrappers=1", str(medya)],
                       capture_output=True, text=True, timeout=60)
    return float(r.stdout.strip() or 0)


def _ayikla(metin, sure):
    out, acik = [], None
    for satir in metin.splitlines():
        m = _BAS.search(satir)
        if m:
            acik = float(m.group(1)); continue
        m = _BIT.search(satir)
        if m and acik is not None:
            out.append((max(0.0, acik), min(sure, float(m.group(1))))); acik = None
    if acik is not None:
        out.append((max(0.0, acik), sure))
    out = sorted((a, b) for a, b in out if b - a > 1e-3)
    birles = []
    for a, b in out:
        if birles and a <= birles[-1][1] + 1e-3:
            birles[-1] = (birles[-1][0], max(birles[-1][1], b))
        else:
            birles.append((a, b))
    return birles


def _silencedetect(medya, esik):
    r = subprocess.run([FFMPEG, "-nostdin", "-hide_banner", "-nostats", "-i", str(medya), "-vn", "-af",
                        f"silencedetect=noise={esik}dB:d={EN_KISA}", "-f", "null", "-"], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-400:])
    return r.stderr


def ses_haritasi(medya, esik=None):
    """{'sure', 'esik', 'sessizlik': [(bas, bit), ...]}. Dosya değişmedikçe önbellekten."""
    medya = Path(medya)
    st = medya.stat()
    anahtar = hashlib.sha1(f"{medya.resolve()}|{st.st_size}|{int(st.st_mtime)}|{esik}|{EN_KISA}".encode()).hexdigest()[:20]
    yol = ONBELLEK / f"{anahtar}.json"
    if yol.exists():
        try:
            d = json.loads(yol.read_text())
            d["sessizlik"] = [tuple(x) for x in d["sessizlik"]]
            return d
        except Exception:  # noqa: BLE001
            pass
    sure = _sure(medya)
    secilen = esik if esik is not None else ESIK_DB
    ses = _ayikla(_silencedetect(medya, secilen), sure)
    if esik is None and sure > 20 and len(ses) < sure / 30:      # altta müzik/oda sesi: -30 dB'de neredeyse hiç sessizlik yok
        ses2 = _ayikla(_silencedetect(medya, -25.0), sure)
        if len(ses2) > len(ses) * 2:
            ses, secilen = ses2, -25.0
    d = {"sure": round(sure, 3), "esik": secilen, "sessizlik": [(round(a, 3), round(b, 3)) for a, b in ses]}
    try:
        ONBELLEK.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps(d))
    except OSError:
        pass
    return d


def kelimeler(segmentler, pencereler=None):
    """[(bas, bit, kelime)] zaman sırasıyla; segmentte kelime zamanı yoksa karakter oranıyla. pencereler (dolgu.py:
    [[bas, bit, [[b, e, w], ...]]]) verilirse o aralıklarda yeniden dinlenmiş kelimeler (duraksamalar ayrı kelime) kullanılır."""
    out = []
    for s in segmentler:
        if s.get("kelimeler"):
            out += [(float(k[0]), float(k[1]), str(k[2])) for k in s["kelimeler"]]
            continue
        parca = (s.get("metin") or "").split()
        if not parca:
            continue
        toplam = sum(len(p) + 1 for p in parca); t = s["bas"]; sure = max(0.5, s["bit"] - s["bas"])
        for p in parca:
            dt = sure * (len(p) + 1) / toplam
            out.append((t, t + dt, p)); t += dt
    for a, b, sozler in pencereler or []:
        out = [w for w in out if not a <= (w[0] + w[1]) / 2 <= b] + [(float(x[0]), float(x[1]), str(x[2])) for x in sozler]
    return sorted(out)


def _sessiz_mi(ses, t):
    for a, b in ses:
        if a <= t <= b:
            return True
        if a > t:
            break
    return False


def _sessizlik_sec(ses, lo, hi, hedef):
    """[lo, hi] penceresine değen sessizliklerden hedefe en yakın olanı (pencereyle kesişimi)."""
    en = None
    for a, b in ses:
        if b < lo:
            continue
        if a > hi:
            break
        x, y = max(a, lo), min(b, hi)
        if y - x < 0.03:
            continue
        uzak = 0.0 if x <= hedef <= y else min(abs(hedef - x), abs(hedef - y))
        if en is None or uzak < en[0]:
            en = (uzak, a, b)
    return None if en is None else (en[1], en[2])


def sessiz_oran(ses, a, b):
    """[a, b] aralığının ne kadarı sessiz (0-1)."""
    if b <= a:
        return 1.0
    ortu = sum(max(0.0, min(y, b) - max(x, a)) for x, y in ses if y > a and x < b)
    return ortu / (b - a)


def _uyan(kel, tut):
    """Her kelime için hangi aralıkta tutulduğu (ortası aralıktaysa), yoksa None."""
    out = []
    for b, e, _ in kel:
        o = (b + e) / 2
        out.append(next((i for i, (x, y) in enumerate(tut) if x <= o <= y), None))
    return out


def oturt(tut, ses, kel, toplam, pay=PAY, butce=BUTCE):
    """tut=[(bas, bit)] (sıralı ya da kurgu sırası). Döner (yeni_tut, rapor). Ortası tutulan aralıkta kalan kelime tutulmuş
    sayılır. Kenar, o kelimeyle komşu (çıkarılan) kelime arasındaki ve özgün kenarın en çok `butce` sn ötesindeki sessizliğe
    taşınır; konuşmanın yanında `pay` kadar sessizlik kalır. Sessizlik yoksa iki kelimenin arasına, o da yoksa yerinde kalır
    (Manticore snap_spans: güvenli olmayan kenar 'oturmadı' diye sayılır, saklanmaz)."""
    rapor = {"kenar": 0, "sessizlige": 0, "kelime_arasina": 0, "oturmadi": 0, "kaydirma_ms": []}
    if not tut:
        return tut, rapor
    uye = _uyan(kel, tut)
    yeni = [list(x) for x in tut]
    for i, (a, b) in enumerate(tut):
        ici = [j for j, u in enumerate(uye) if u == i]
        if not ici:
            continue
        ilk, son = ici[0], ici[-1]
        if a > 0.05:                         # başlangıç: önceki (çıkarılan) kelime ile ilk tutulan kelime arası
            rapor["kenar"] += 1
            F = kel[ilk]; Pe = kel[ilk - 1][1] if ilk > 0 else 0.0
            lo, hi = max(min(Pe, F[0]) - ARA, a - butce), min(F[0] + ARA, a + butce)
            s = _sessizlik_sec(ses, lo, hi, F[0]) if hi > lo else None
            if s:
                yeni_a = max(s[0], lo, min(s[1], hi) - pay); rapor["sessizlige"] += 1
            elif abs(F[0] - a) <= butce:             # sessizlik yok (akıcı konuşmada duraksama): tutulan kelimenin kendi başı
                yeni_a = (Pe + F[0]) / 2 if Pe < F[0] else F[0]; rapor["kelime_arasina"] += 1
            else:
                yeni_a = a; rapor["oturmadi"] += 1
            rapor["kaydirma_ms"].append(round((yeni_a - a) * 1000))
            yeni[i][0] = max(0.0, yeni_a)
        if b < toplam - 0.05:                # bitiş: son tutulan kelime ile sonraki (çıkarılan) kelime arası
            rapor["kenar"] += 1
            L = kel[son]; Nb = kel[son + 1][0] if son + 1 < len(kel) else toplam
            lo, hi = max(L[1] - ARA, b - butce), min(max(Nb, L[1]) + ARA, b + butce)
            s = _sessizlik_sec(ses, lo, hi, L[1]) if hi > lo else None
            if s:
                yeni_b = min(s[1], hi, max(s[0], lo) + pay); rapor["sessizlige"] += 1
            elif abs(L[1] - b) <= butce:
                yeni_b = (L[1] + Nb) / 2 if Nb > L[1] else L[1]; rapor["kelime_arasina"] += 1
            else:
                yeni_b = b; rapor["oturmadi"] += 1
            rapor["kaydirma_ms"].append(round((yeni_b - b) * 1000))
            yeni[i][1] = min(toplam, yeni_b)
    if all(tut[k][0] <= tut[k + 1][0] for k in range(len(tut) - 1)):    # sıralı kesimde komşular birbirine taşmasın
        for k in range(1, len(yeni)):
            if yeni[k][0] < yeni[k - 1][1]:
                yeni[k - 1][1] = yeni[k][0] = (yeni[k][0] + yeni[k - 1][1]) / 2
    return [(round(x, 3), round(y, 3)) for x, y in yeni if y - x >= 0.05], rapor


def olc(tut, ses, kel, toplam):
    """Kesim kenarlarının kaçı bir kelimenin içine, kaçı seste konuşmanın ortasına düşüyor."""
    kelime_ici = konusma_ici = kenar = 0
    for a, b in tut:
        for t in ((a,) if a > 0.05 else ()) + ((b,) if b < toplam - 0.05 else ()):
            kenar += 1
            if any(x + 0.03 < t < y - 0.03 for x, y, _ in kel):
                kelime_ici += 1
            if not _sessiz_mi(ses, t):
                konusma_ici += 1
    return {"kenar": kenar, "kelime_ici": kelime_ici, "konusma_ici": konusma_ici}


def konusma_bosluklari(ses, kel, toplam, en_az=0.20, en_cok=1.6):
    """Seste konuşma olan ama hiçbir kelimenin değmediği, iki kelime arasındaki kısa parçalar [(bas, bit)]."""
    konusma, t = [], 0.0
    for a, b in ses:
        if a - t > 1e-3:
            konusma.append((t, a))
        t = max(t, b)
    if toplam - t > 1e-3:
        konusma.append((t, toplam))
    out, j = [], 0
    for a, b in konusma:
        while j < len(kel) and kel[j][1] < a:
            j += 1
        # parçadaki kelime kapsamını çıkar; kalan en uzun boşluk
        imlec, bosluk = a, []
        k = j
        while k < len(kel) and kel[k][0] < b:
            if kel[k][0] - imlec >= en_az:
                bosluk.append((imlec, kel[k][0]))
            imlec = max(imlec, kel[k][1]); k += 1
        if b - imlec >= en_az:
            bosluk.append((imlec, b))
        for x, y in bosluk:
            onceki = j > 0 or any(w[1] <= x + 0.01 for w in kel[max(0, j - 1):k])
            sonraki = k < len(kel)
            if en_az <= y - x <= en_cok and onceki and sonraki:
                out.append((round(x, 3), round(y, 3)))
    return out

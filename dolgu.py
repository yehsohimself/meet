"""Duraksama sesi (ee, ıı, hmm) bulucu; Studio'nun "Duraksamaları temizle" seçeneği için (2026-10-29).

Sorun: Whisper "ee/ıı" seslerini çoğu zaman yazmaz, ya da yanındaki kelimenin süresine katar ("bir" 0,64 sn). Kitaplıktaki
transkriptlerin hemen hepsinde kelime listesinde hiç duraksama yoktu; eski bulucu (yalnız kelime listesine bakan) boş dönüyordu.
BMad Manticore duraksamaları kelimesi kelimesine yazan parakeet-tdt-0.6b-v3 kullanıyor, ama o model Türkçe bilmiyor (25 Avrupa
dili) ve ~2,4 GB. Ölçüm (3 dk Türkçe toplantı): Whisper'a dosyanın tamamını "Eee, ııı, şey..." ipucuyla yeniden çözdürmek 1,
yalnız şüpheli kısa parçaları (normalinden uzun süren kelimeler, sesi olup yazısı olmayan boşluklar) ipucuyla yeniden çözdürmek 2
duraksama buldu ve yarı süreye mal oldu. Bu modül ikinciyi yapar: kelime zamanları düzelmiş pencereleri ve bulunan duraksamaları
veri["dolgu"]'ya yazar; kesim (kesim_sinir.kelimeler) bu pencerelerin kelimelerini kullanır, böylece duraksamayı yutmuş kelime
duraksamayla birlikte silinmez.

Elle: python dolgu.py <temel> [medya]"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
MODEL = "mlx-community/whisper-large-v3-turbo"
IPUCU = "Eee, ııı, şey... hmm, ee."
DOLGU = re.compile(r"^(e{2,}h?|ı{2,}|i{3,}|ö{2,}|a{3,}|h+m+|m{2,}|ı+m+|e+m+|eh|öh|ıh|uh+|um+)$")
PENCERE_EN_COK = 12.0
IPUCU_SOZ = ["eee", "ııı", "şey", "hmm", "ee"]


def sozcuk(w):
    return re.sub(r"[^\wığüşöç]", "", str(w).replace("İ", "i").replace("I", "ı").lower())


def dolgu_mu(w):
    return bool(DOLGU.match(sozcuk(w)))


def _yanki(metin):
    """Whisper ipucunu kopyaladı ya da döngüye girdi mi: ipucundaki ardışık iki sözcük aynı sırayla geçiyor, parçada 4'ten çok
    duraksama ya da aynı duraksama üst üste 3 kez var ("Hmm, hmm, hmm..."), ya da bilinen uydurma kalıp ("Altyazı")."""
    s = [sozcuk(w) for w in metin.split()]
    if any((x, y) in zip(IPUCU_SOZ, IPUCU_SOZ[1:]) for x, y in zip(s, s[1:])):
        return True
    if sum(1 for w in s if DOLGU.match(w)) > 4 or any(a == b == c and DOLGU.match(a) for a, b, c in zip(s, s[1:], s[2:])):
        return True
    return any(w in ("altyazı", "altyazi", "abone") for w in s)


def imza(segmentler):
    """Kelime zamanları değişirse (yeniden yazıya dökme) eski bulgu geçersiz olur."""
    h = hashlib.sha1()
    for s in segmentler:
        h.update(f"{s['bas']:.2f}-{s['bit']:.2f}|".encode())
    return h.hexdigest()[:16]


def adaylar(kel, ses, toplam):
    """Yeniden çözülecek pencereler [(bas, bit)]: süresi metnine göre uzun kelimeler ve sesi olup kelimesi olmayan boşluklar,
    birer komşu kelimeyle; çakışanlar birleşir (en çok PENCERE_EN_COK sn)."""
    import kesim_sinir
    ham = []
    for i, (b, e, w) in enumerate(kel):
        if e - b > 0.25 + 0.09 * len(sozcuk(w) or w):
            ham.append((kel[i - 1][0] if i else b, kel[i + 1][1] if i + 1 < len(kel) else e))
    for x, y in kesim_sinir.konusma_bosluklari(ses, kel, toplam):
        onceki = [w for w in kel if w[1] <= x + 0.05]
        sonraki = [w for w in kel if w[0] >= y - 0.05]
        ham.append((onceki[-1][0] if onceki else x, sonraki[0][1] if sonraki else y))
    ham.sort()
    out = []
    for a, b in ham:
        a, b = max(0.0, a - 0.1), min(toplam, b + 0.1)
        if out and a <= out[-1][1] and b - out[-1][0] <= PENCERE_EN_COK:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _ses_oku(medya):
    import subprocess
    import numpy as np
    r = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(medya), "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "-"], capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError("Ses okunamadı.")
    return np.frombuffer(r.stdout, dtype=np.float32)


def bul(js, medya, log=print):
    """{'imza', 'araliklar': [[bas, bit, kelime]], 'pencereler': [[bas, bit, [[b, e, w], ...]]], 'aday', 'sn', 'tarih'}."""
    import mlx_whisper
    import kesim_sinir
    d = json.loads(Path(js).read_text(encoding="utf-8"))
    harita = kesim_sinir.ses_haritasi(medya)
    toplam = harita["sure"]
    kel = kesim_sinir.kelimeler(d["segmentler"])
    pen = adaylar(kel, harita["sessizlik"], toplam)
    log(f"{len(pen)} şüpheli parça yeniden dinleniyor")
    ses = _ses_oku(medya)
    dil = d["veri"].get("dil") if re.match(r"^[a-z]{2}$", str(d["veri"].get("dil") or "")) else None
    t0 = time.time()
    import difflib
    araliklar, pencereler, elenen = [], [], 0
    for n, (a, b) in enumerate(pen, 1):
        parca = ses[int(a * 16000):int(b * 16000)]
        if len(parca) < 1600:
            continue
        ortak = dict(path_or_hf_repo=MODEL, language=dil, initial_prompt=IPUCU, condition_on_previous_text=False, temperature=0.0, verbose=None)
        # 1) hızlı dinleme (kelime zamanı yok, ~3 sn): parçada duraksama var mı
        metin = mlx_whisper.transcribe(parca, **ortak)["text"]
        if not any(dolgu_mu(w) for w in metin.split()):
            continue
        ilk = [sozcuk(w[2]) for w in kel if a <= (w[0] + w[1]) / 2 <= b]
        yeni_soz = [sozcuk(w) for w in metin.split() if not dolgu_mu(w)]
        # ipucunun kendisi yazıldıysa (sessizlikte "Eee, ııı, şey..." yankısı) ya da parçanın geri kalanı ilk yazıya dökmeyle
        # uyuşmuyorsa güvenilmez: kesim gerçek kelimeyi silebilir (ölçümde yankı "%10" kelimesinin üstüne oturmuştu)
        if _yanki(metin) or (ilk and difflib.SequenceMatcher(None, ilk, [w for w in yeni_soz if w]).ratio() < 0.6):
            elenen += 1
            continue
        # 2) kelime zamanlı dinleme (~8 sn) yalnız duraksama duyulan parçada
        r = mlx_whisper.transcribe(parca, word_timestamps=True, **ortak)
        sozler = [[round(a + w["start"], 3), round(a + w["end"], 3), w["word"].strip()] for s_ in r.get("segments") or [] for w in s_.get("words") or []]
        sozler = [w for w in sozler if w[1] > w[0] and w[2]]
        if _yanki(" ".join(w[2] for w in sozler)):
            elenen += 1
            continue
        kelime = [w for w in sozler if not dolgu_mu(w[2])]
        bulunan = [w for w in sozler if dolgu_mu(w[2]) and w[1] - w[0] >= 0.12
                   and not any(min(w[1], k[1]) - max(w[0], k[0]) > 0.03 for k in kelime)
                   and kesim_sinir.sessiz_oran(harita["sessizlik"], w[0], w[1]) < 0.7]
        if bulunan:
            pencereler.append([round(a, 3), round(b, 3), sozler])
            araliklar += bulunan
        if n % 20 == 0:
            log(f"  {n}/{len(pen)} parça · {len(araliklar)} duraksama")
    if elenen:
        log(f"  {elenen} parçada duyulan güvenilir bulunmadı, atlandı")
    sn = round(time.time() - t0, 1)
    log(f"{len(araliklar)} duraksama bulundu ({sn} sn)")
    return {"imza": imza(d["segmentler"]), "araliklar": araliklar, "pencereler": pencereler, "aday": len(pen), "elenen": elenen, "sn": sn,
            "tarih": time.strftime("%Y-%m-%d %H:%M")}


def kelime_listesinden(segmentler):
    """İlk yazıya dökmede yazılmış duraksamalar (eski yöntem)."""
    out = []
    for s in segmentler:
        for k in s.get("kelimeler") or []:
            if dolgu_mu(k[2]) and k[1] - k[0] >= 0.12:
                out.append([round(k[0], 2), round(k[1], 2), str(k[2])])
    return out


def birlesik(d):
    """Kesim için bütün duraksamalar: kelime listesindekiler + (geçerliyse) yeniden dinlemede bulunanlar, çakışanlar tek."""
    ar = kelime_listesinden(d["segmentler"])
    dv = d["veri"].get("dolgu") or {}
    if dv.get("imza") == imza(d["segmentler"]):
        ar += [[round(x[0], 2), round(x[1], 2), x[2]] for x in dv.get("araliklar") or []]
    ar.sort()
    out = []
    for x in ar:
        if out and x[0] < out[-1][1]:
            out[-1][1] = max(out[-1][1], x[1])
        else:
            out.append(list(x))
    return out


def gecerli_pencereler(d):
    dv = d["veri"].get("dolgu") or {}
    return dv.get("pencereler") if dv.get("imza") == imza(d["segmentler"]) else None


def main():
    temel = sys.argv[1]
    js = KLASOR / f"{temel}.json"
    medya = Path(sys.argv[2])
    sonuc = bul(js, medya)
    import kayit_json
    def yaz(d):
        d["veri"]["dolgu"] = sonuc
    kayit_json.guncelle(js, yaz)
    print("Bitti.", len(sonuc["araliklar"]), "duraksama", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
dublaj.py - Çevrilmiş transkripti konuşmacının kendi sesiyle başka dilde seslendirir (yerel, dışarı veri gitmez).

Model: Chatterbox Multilingual (Resemble AI, MIT; 23 dil, Türkçe dahil), ayrı ortamda: .venv-dublaj (torch, CPU).
Hız (M4): ~4x gerçek zaman (5 sn ses ≈ 20 sn); 3 dk video ≈ 12 dk. Türkçe örnek: scratchpad tts_tr_mps.wav.
Akış: transkript JSON'daki çeviri (veri["ceviriler"][dil]) → aynı konuşmacının ardışık cümleleri ≤12 sn'lik parçalara
toplanır → her konuşmacı için kaynak sesten 6-10 sn referans kesilir (ses klonlama) → her parça seslendirilir →
süre özgün aralığa sığdırılır (gerekirse ≤1,35x hızlandırma) → zaman çizelgesine yerleştirilir → özgün ses kısılarak
(-18 dB) ya da tamamen kaldırılarak videoya basılır.

Kullanım: .venv/bin/python dublaj.py transkript_x.json --dil en --video kaynak.mp4 [--cikti yol.mp4] [--ozgun-sil]
Son satır: "Bitti. Dosya: ..."
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"
TTS_PY = KLASOR / ".venv-dublaj" / "bin" / "python"
PARCA_EN_COK = 12.0
HIZ_EN_COK = 1.35
DIL_KODU = {"en": "en", "de": "de", "fr": "fr", "es": "es", "it": "it", "pt": "pt", "ru": "ru", "ar": "ar", "nl": "nl",
            "ja": "ja", "ko": "ko", "zh": "zh", "tr": "tr", "pl": "pl", "sv": "sv", "hi": "hi", "el": "el", "da": "da",
            "fi": "fi", "no": "no", "he": "he", "ms": "ms", "sw": "sw"}


def log(m):
    print(m, flush=True)


def hazir():
    return TTS_PY.exists()


def _parcalar(seg, cevirili, en_cok=PARCA_EN_COK):
    """Aynı konuşmacının ardışık cümlelerini birleştirir: [{"k","bas","bit","metin"}]"""
    out = []
    for s, m in zip(seg, cevirili):
        m = (m or "").strip()
        if not m:
            continue
        if out and out[-1]["k"] == s.get("k") and s["bas"] - out[-1]["bit"] < 0.8 and s["bit"] - out[-1]["bas"] <= en_cok:
            out[-1]["bit"] = s["bit"]; out[-1]["metin"] += " " + m
        else:
            out.append({"k": s.get("k", "0"), "bas": s["bas"], "bit": s["bit"], "metin": m})
    return out


def _referanslar(ses, seg, klasor, log):
    """Her konuşmacı için en uzun temiz cümlelerden 6-10 sn referans wav (24 kHz mono)."""
    refs = {}
    for k in sorted({s.get("k", "0") for s in seg}):
        adaylar = sorted((s for s in seg if s.get("k", "0") == k and s["bit"] - s["bas"] >= 2.0), key=lambda s: -(s["bit"] - s["bas"]))
        parcalar, toplam = [], 0.0
        for s in adaylar:
            parcalar.append((s["bas"], min(s["bit"], s["bas"] + 10.0))); toplam += parcalar[-1][1] - parcalar[-1][0]
            if toplam >= 8.0:
                break
        if not parcalar:
            continue
        hedef = klasor / f"ref_{k}.wav"
        fc = "".join(f"[0:a]atrim=start={b:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}];" for i, (b, e) in enumerate(parcalar))
        fc += "".join(f"[a{i}]" for i in range(len(parcalar))) + f"concat=n={len(parcalar)}:v=0:a=1,aresample=24000[o]"
        r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(ses), "-filter_complex", fc, "-map", "[o]", "-ac", "1", str(hedef)], capture_output=True, text=True)
        if r.returncode == 0 and hedef.exists() and _sure(hedef) >= 1.5:
            refs[k] = hedef
    log(f"      {len(refs)} konuşmacı için ses referansı alındı")
    return refs


def _ayir(video, klasor, log):
    """Demucs (htdemucs, iki kanal): konuşma (vocals) ve arka plan (no_vocals: müzik, efekt, ortam). Olmazsa (None, None)."""
    wav = klasor / "ozgun.wav"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "2", "-ar", "44100", str(wav)], capture_output=True)
    if not wav.exists():
        return None, None
    t = time.time()
    for cihaz in ("mps", "cpu"):
        r = subprocess.run(["/usr/bin/nice", "-n", "5", str(TTS_PY), "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-d", cihaz,
                            "-o", str(klasor / "ayrim"), str(wav)], capture_output=True, text=True)
        k = klasor / "ayrim" / "htdemucs" / "ozgun"
        if r.returncode == 0 and (k / "vocals.wav").exists():
            log(f"      konuşma ve arka plan ayrıldı ({cihaz}, {time.time() - t:.0f} sn)")
            return k / "vocals.wav", k / "no_vocals.wav"
    log("      ayrım yapılamadı; özgün ses kısılarak kullanılacak")
    return None, None


def _kisalt(parcalar, oranlar, dil, log):
    """Seslendirmesi özgün süreden belirgin uzun kalan parçaların çevirisini Claude ile aynı anlamda kısaltır (dublaj eşzamanlılığı)."""
    uzun = [(i, o) for i, o in enumerate(oranlar) if o and o > 1.25]
    if not uzun:
        return []
    try:
        import claude_yaz
        if not claude_yaz.hazir():
            return []
        satirlar = "\n".join(f'{n + 1}. (en çok {max(3, int(len(parcalar[i]["metin"].split()) / o * 0.95))} kelime) {parcalar[i]["metin"]}' for n, (i, o) in enumerate(uzun))
        cevap = claude_yaz.sor_json(f"Bunlar bir videonun {dil} dublaj metinleri; seslendirme özgün konuşmadan uzun kalıyor. Her satırı AYNI ANLAMLA, doğal "
                                    f"konuşma diliyle, parantezdeki kelime sayısını geçmeyecek şekilde kısalt. Anlam ekleme, bilgi atma. "
                                    f'JSON döndür: {{"satirlar": ["...", ...]}} (toplam {len(uzun)} satır, sırayla).\n\n{satirlar}')
        yeni = (cevap or {}).get("satirlar") or []
    except Exception as e:  # noqa: BLE001
        log(f"      kısaltma yapılamadı: {str(e)[:80]}")
        return []
    degisen = []
    for (i, _o), m in zip(uzun, yeni):
        m = (m or "").strip()
        if m and len(m.split()) < len(parcalar[i]["metin"].split()):
            parcalar[i]["metin"] = m; degisen.append(i)
    log(f"      {len(degisen)} parça süreye sığsın diye kısaltıldı")
    return degisen


def _telaffuz(parcalar, dil, log):
    """Özel adlar (kişi, marka, yer) seslendirme motoru hedef dilin kurallarıyla okuyup bozmasın diye, YALNIZCA ses için orijinal okunuşa en
    yakın biçimde yeniden yazılır (Türkçede "Keanu Reeves" → "Kiyanu Rivz"). Altyazı ve çeviri metni değişmez. Örnek: 2026-10-20 dublaj önizlemesi."""
    try:
        import claude_yaz
        if not claude_yaz.hazir() or not parcalar:
            return [p["metin"] for p in parcalar]
        satirlar = "\n".join(f"{i + 1}. {p['metin']}" for i, p in enumerate(parcalar))
        cevap = claude_yaz.sor_json(
            f"Aşağıdaki satırlar bir seslendirme (text-to-speech) motoruna '{dil}' dilinde okutulacak. Motor her kelimeyi bu dilin okuma kurallarıyla okur. "
            "Görevin: satırlardaki ÖZEL ADLARI (kişi, marka, ürün, yer, kısaltma) bu dilin harfleriyle, orijinal dildeki gerçek okunuşa en yakın duyulacak "
            "şekilde yeniden yaz (ör. Türkçe için 'Keanu Reeves' → 'Kiyanu Rivz', 'iPhone' → 'Ayfon'; Japonca için katakana). Bu dilde zaten doğru okunan "
            "adlara ve diğer kelimelere DOKUNMA; anlamı, sırayı ve noktalamayı değiştirme. "
            f'JSON döndür: {{"satirlar": ["...", ...]}} (toplam {len(parcalar)} satır, sırayla).\n\n{satirlar}')
        yeni = (cevap or {}).get("satirlar") or []
        if len(yeni) != len(parcalar):
            return [p["metin"] for p in parcalar]
        degisen = sum(1 for a, b in zip(parcalar, yeni) if a["metin"].strip() != (b or "").strip())
        if degisen:
            log(f"      {degisen} parçada özel adların okunuşu düzeltildi")
        return [(b or a["metin"]).strip() for a, b in zip(parcalar, yeni)]
    except Exception as e:  # noqa: BLE001
        log(f"      okunuş düzeltmesi yapılamadı: {str(e)[:80]}")
        return [p["metin"] for p in parcalar]


MLX_PY = KLASOR / ".venv-mlxtts" / "bin" / "python"
MLX_MODEL = "mlx-community/chatterbox-multilingual-v3"


def _motor():
    """Seslendirme motoru: DUBLAJ_MOTOR=mlx|torch; yoksa MLX ortamı ve modeli varsa mlx (Apple GPU), değilse eski PyTorch/CPU yolu."""
    m = os.environ.get("DUBLAJ_MOTOR", "")
    if m in ("mlx", "torch"):
        return m
    model_var = (Path.home() / ".cache" / "huggingface" / "hub" / ("models--" + MLX_MODEL.replace("/", "--")) / "snapshots").exists()
    return "mlx" if MLX_PY.exists() and model_var else "torch"


# MLX yolu: konuşmacı başına koşul (ses referansı) bir kez hazırlanır; PyTorch yolundaki varsayılanlar korunur (exaggeration 0,5, cfg 0,5, sıcaklık 0,8);
# tekrar cezası 1,2 (MLX'te 2,0 bozuk çıktı veriyor: voicebox #1162). Kaçak üretim (uzun tıslama/yarım ses) için süre denetimi: beklenen sürenin
# 2,2 katını aşarsa ya da yarısından kısaysa daha düşük sıcaklıkla bir kez yeniden.
KOD_MLX = r'''
import json, sys, time, wave, numpy as np
import mlx.core as mx
from mlx_audio.tts.utils import load_model
istek = json.load(open(sys.argv[1], encoding="utf-8"))
model = load_model("''' + MLX_MODEL + r'''")
print("model hazır (mlx)", flush=True)
conds = {}
def kaydet(yol, ses, sr):
    a = np.clip(np.asarray(ses, dtype=np.float32).reshape(-1), -1, 1)
    with wave.open(yol, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32767).astype(np.int16).tobytes())
t0 = time.time()
for p in istek["parcalar"]:
    try:
        ref = p.get("ref") or ""
        if ref not in conds:
            conds[ref] = model.prepare_conditionals(ref, model.sample_rate, exaggeration=0.5) if ref else None
        beklenen = max(1.0, len(p["metin"]) / 14.0)          # ~14 harf/sn
        enfazla = min(1000, int(beklenen * 25 * 2.4) + 60)  # konuşma birimi 25/sn
        ses = None
        for sicaklik in (0.8, 0.5):
            kw = dict(text=p["metin"], lang_code=istek["dil"], exaggeration=0.5, cfg_weight=0.5, temperature=sicaklik,
                      repetition_penalty=1.2, max_new_tokens=enfazla, verbose=False)
            if conds[ref] is not None:
                kw["conds"] = conds[ref]
            sonuc = list(model.generate(**kw))
            ses = np.concatenate([np.asarray(r.audio).reshape(-1) for r in sonuc]) if sonuc else None
            sure = 0 if ses is None else len(ses) / model.sample_rate
            if ses is not None and beklenen * 0.45 <= sure <= beklenen * 2.2:
                break
            print(f"parça {p['i']} süresi beklenmedik ({sure:.1f} sn / ~{beklenen:.1f}); yeniden", flush=True)
        if ses is None:
            raise RuntimeError("ses çıkmadı")
        kaydet(p["cikti"], ses, model.sample_rate)
        mx.clear_cache()
    except Exception as e:
        print(f"parça {p['i']} üretilemedi: {str(e)[:100]}", flush=True); continue
    print(f"ses {p['i'] + 1}/{len(istek['parcalar'])} ({time.time() - t0:.0f} sn)", flush=True)
'''


def _tts(parcalar, refs, dil, klasor, log, sadece=None):
    """Ayrı ortamda toplu seslendirme: girdi JSON → çıktı wav'lar."""
    istek = [{"i": i, "metin": p.get("ses_metni") or p["metin"], "ref": str(refs.get(p["k"], "")) or None, "cikti": str(klasor / f"tts_{i:04d}.wav")} for i, p in enumerate(parcalar)
             if sadece is None or i in sadece]
    (klasor / "istek.json").write_text(json.dumps({"dil": DIL_KODU.get(dil, dil), "parcalar": istek}, ensure_ascii=False), encoding="utf-8")
    kod = r'''
import json, sys, time, torch, torchaudio as ta, perth
if getattr(perth, "PerthImplicitWatermarker", None) is None:
    perth.PerthImplicitWatermarker = perth.DummyWatermarker      # filigran modülü bu Mac'te yüklenemiyor; filigransız sür
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
istek = json.load(open(sys.argv[1], encoding="utf-8"))
import os
dev = os.environ.get("DUBLAJ_CIHAZ", "cpu")        # ölçüm (M4): CPU ~4x gerçek zaman, MPS 7-15x → CPU varsayılan
torch.set_num_threads(max(1, (os.cpu_count() or 4) - 2))
model = ChatterboxMultilingualTTS.from_pretrained(device=dev)
print(f"model hazır ({dev})", flush=True)
t0 = time.time()
for p in istek["parcalar"]:
    kw = {"language_id": istek["dil"]}
    if p.get("ref"): kw["audio_prompt_path"] = p["ref"]
    try:
        wav = model.generate(p["metin"], **kw)
    except Exception as e:
        print(f"parça {p['i']} üretilemedi: {str(e)[:100]}", flush=True); continue
    ta.save(p["cikti"], wav.cpu() if hasattr(wav, "cpu") else wav, model.sr)
    print(f"ses {p['i'] + 1}/{len(istek['parcalar'])} ({time.time() - t0:.0f} sn)", flush=True)
'''
    if _motor() == "mlx":                                    # 23 Ekim: aynı model ailesi, Apple GPU'da (mlx-audio); ölçüm CLAUDE.md'de
        kod = KOD_MLX
    (klasor / "tts_calistir.py").write_text(kod, encoding="utf-8")
    env = dict(os.environ, PYTHONUNBUFFERED="1", TOKENIZERS_PARALLELISM="false")
    p = subprocess.Popen([str(MLX_PY if _motor() == "mlx" else TTS_PY), "-I", str(klasor / "tts_calistir.py"), str(klasor / "istek.json")],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    for satir in p.stdout:
        satir = satir.rstrip()
        if satir.startswith("model hazır"):
            TTS_HAZIR[0] = time.time()
        if satir and not satir.startswith(("Warning", "/", "  ")) and "Sampling:" not in satir and "it/s" not in satir and "WARNING" not in satir:
            log("      " + satir[:160])
    p.wait()
    return [Path(klasor / f"tts_{i:04d}.wav") if (klasor / f"tts_{i:04d}.wav").exists() else None for i in range(len(parcalar))]


TTS_HAZIR = [0.0]                                           # model yüklenip seslendirmenin başladığı an (önizleme tahmini için)


def _sure(yol):
    r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(yol)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _zaman_cizelgesi(parcalar, wavlar, toplam, klasor, log):
    """Parçaları özgün zamanlarına yerleştirir (gerekirse hızlandırır); tek dublaj wav'ı döner."""
    girdiler, filtre, etiketler = [], "", []
    n = 0
    kaymalar = 0
    for i, (p, w) in enumerate(zip(parcalar, wavlar)):
        if not w:
            continue
        sure_w = _sure(w); aralik = max(0.5, p["bit"] - p["bas"])
        hiz = 1.0
        if sure_w > aralik:
            hiz = min(HIZ_EN_COK, sure_w / aralik)
            if sure_w / hiz > aralik + 0.6:
                kaymalar += 1
        girdiler += ["-i", str(w)]
        filtre += f"[{n}:a]aresample=48000,loudnorm=I=-17:TP=-1.5:LRA=7,aresample=48000,atempo={hiz:.3f},adelay={int(p['bas'] * 1000)}|{int(p['bas'] * 1000)}[d{n}];"
        etiketler.append(f"[d{n}]"); n += 1
    if not etiketler:
        raise SystemExit("HATA: Hiç ses üretilemedi.")
    filtre += "".join(etiketler) + f"amix=inputs={n}:duration=longest:normalize=0,apad=whole_dur={toplam:.2f},alimiter=limit=0.95[o]"
    cikti = klasor / "dublaj.wav"
    r = subprocess.run([FFMPEG, "-y", "-v", "error"] + girdiler + ["-filter_complex", filtre, "-map", "[o]", "-ac", "1", str(cikti)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("HATA: Dublaj zaman çizelgesi kurulamadı: " + r.stderr[-300:])
    if kaymalar:
        log(f"      {kaymalar} parça özgün süreden uzun kaldı (hızlandırma sınırı 1,35x); sonraki cümleye taşabilir")
    return cikti


def dublaj(json_yolu, dil, video, cikti=None, ozgun_sil=False, log=log, onizleme=0):
    """onizleme > 0 (2026-10-23, ChatGPT brifi Studio 5): yalnız ilk N saniye seslendirilir (adların okunuşu, çeviri ve senkron dinlenir); parça başına
    süre ölçülüp tamamı için 'Tahmin: tamamı ~X dk' yazılır."""
    d = json.loads(Path(json_yolu).read_text(encoding="utf-8")); veri, seg = d["veri"], d["segmentler"]
    cev = (veri.get("ceviriler") or {}).get(dil)
    if not cev:
        raise SystemExit(f"HATA: Bu transkriptin {dil} çevirisi yok; önce çevirin.")
    if not hazir():
        raise SystemExit("HATA: Seslendirme ortamı kurulu değil (.venv-dublaj).")
    video = Path(video)
    cikti = Path(cikti) if cikti else video.with_name(f"{video.stem} [dublaj {dil.upper()}].mp4")
    gecici = Path(tempfile.mkdtemp(prefix="dublaj_"))
    log(f"[1/4] Parçalar hazırlanıyor ({len(seg)} cümle)")
    parcalar = _parcalar(seg, cev["segmentler"])
    tum_parca = len(parcalar); tum_parcalar = list(parcalar)
    if onizleme:
        parcalar = [x for x in parcalar if x["bit"] <= onizleme + 2] or parcalar[:2]
        sinir = max(onizleme, max(x["bit"] for x in parcalar) + 0.5)
        kesit = gecici / "onizleme.mp4"
        r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-t", f"{sinir:.2f}", "-c:v", "h264_videotoolbox", "-b:v", "6M", "-c:a", "aac", str(kesit)],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:                                 # donanım kodlayıcı olmazsa yazılım (2026-10-25)
            r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-t", f"{sinir:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(kesit)],
                               capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not kesit.exists():
            raise SystemExit("HATA: Önizleme kesiti hazırlanamadı.")
        video = kesit
        log(f"      Önizleme: ilk {sinir:.0f} sn, {len(parcalar)}/{tum_parca} parça")
    log(f"      {len(parcalar)} seslendirme parçası")
    log("[2/4] Konuşma ile arka plan ayrılıyor, konuşmacı ses referansları")
    vokal, arka = _ayir(video, gecici, log)
    # önizlemede ses yalnızca ilk N saniye: örnekler de o aralıktan seçilir (yoksa kesilmiş sesin dışında kalır, boş referans → hiç ses çıkmaz)
    refs = _referanslar(vokal or video, [s for s in seg if s["bit"] <= sinir] if onizleme else seg, gecici, log)
    log(f"[3/4] Seslendirme ({DIL_KODU.get(dil, dil)}) — ilk seferde model iner, sonra her parça birkaç saniye")
    for p, sm in zip(parcalar, _telaffuz(parcalar, dil, log)):
        p["ses_metni"] = sm
    t_tts = time.time()
    wavlar = _tts(parcalar, refs, dil, gecici, log)
    if onizleme and parcalar:
        bitis = time.time(); bas = TTS_HAZIR[0] if TTS_HAZIR[0] > t_tts else t_tts
        yukleme = bas - t_tts                               # model yükleme bir kez; seslendirme metin uzunluğuyla orantılı
        harf = sum(len(x.get("ses_metni") or x.get("metin") or "") for x in parcalar) or 1
        tum_harf = sum(len(x.get("metin") or "") for x in tum_parcalar) or harf
        tahmin = yukleme + (bitis - bas) * tum_harf / harf
        log(f"Tahmin: tamamı ~{max(1, round(tahmin * 1.15 / 60))} dk ({tum_parca} parça; önizlemede {len(parcalar)} parça {bitis - bas:.0f} sn)")
    oranlar = [(_sure(w) / max(0.5, p["bit"] - p["bas"])) if w else None for p, w in zip(parcalar, wavlar)]
    degisen = _kisalt(parcalar, oranlar, dil, log)
    if degisen:
        for i, sm in zip(degisen, _telaffuz([parcalar[i] for i in degisen], dil, log)):
            parcalar[i]["ses_metni"] = sm
            (gecici / f"tts_{i:04d}.wav").unlink(missing_ok=True)
        wavlar = _tts(parcalar, refs, dil, gecici, log, sadece=set(degisen))
    uretilen = sum(1 for w in wavlar if w)
    log(f"      {uretilen}/{len(parcalar)} parça seslendirildi")
    toplam = _sure(video)
    dub = _zaman_cizelgesi(parcalar, wavlar, toplam, gecici, log)
    log("[4/4] Video yazılıyor")
    yeni_ses = "anull"                                      # ses yüksekliği her cümlede ayrı ayarlandı (tüm izde loudnorm sessizlik yüzünden kısık bırakıyordu)
    if arka and not ozgun_sil:
        fc = f"[2:a]aresample=48000[bg];[1:a]aresample=48000,{yeni_ses}[dub];[bg][dub]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[o]"
        ek = ["-i", str(arka)]
    elif ozgun_sil:
        fc = f"[1:a]aresample=48000,{yeni_ses}[o]"; ek = []
    else:
        fc = f"[0:a]aresample=48000,volume=0.12[orj];[1:a]aresample=48000,{yeni_ses}[dub];[orj][dub]amix=inputs=2:duration=first:normalize=0[o]"; ek = []
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-i", str(dub)] + ek + ["-filter_complex", fc, "-map", "0:v?", "-map", "[o]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(cikti)], capture_output=True, text=True)
    if r.returncode != 0 or not cikti.exists():
        raise SystemExit("HATA: Video yazılamadı: " + r.stderr[-300:])
    import shutil
    shutil.rmtree(gecici, ignore_errors=True)                 # geçici ses, ayrım ve seslendirme parçaları (her işte ~25 MB+)
    log(f"Bitti. Dosya: {cikti}")
    return cikti


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); raise SystemExit(1)
    js = args[0]; dil = "en"; video = None; cikti = None; ozgun_sil = False; onizleme = 0
    i = 1
    while i < len(args):
        if args[i] == "--dil":
            dil = args[i + 1].lower(); i += 2
        elif args[i] == "--video":
            video = args[i + 1]; i += 2
        elif args[i] == "--cikti":
            cikti = args[i + 1]; i += 2
        elif args[i] == "--ozgun-sil":
            ozgun_sil = True; i += 1
        elif args[i] == "--onizleme":
            onizleme = float(args[i + 1]); i += 2
        else:
            i += 1
    if not video:
        raise SystemExit("HATA: --video gerekli.")
    dublaj(js, dil, video, cikti, ozgun_sil, onizleme=onizleme)

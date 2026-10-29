#!/usr/bin/env python3
"""
canli.py - Süren bir toplantı kaydını (büyümekte olan m4a) canlı yazıya döker ve "şu ana kadar" özet çıkarır.

Kullanım: .venv/bin/python canli.py "kayitlar/Toplantı 2026-10-16 10.00.m4a" "kayitlar/.canli/durum.json"
Durum dosyası (her turda yeniden yazılır):
  {"dosya", "baslangic", "guncelleme", "islenen_sn", "dil", "segmentler": [{"bas","bit","metin"}],
   "ozet": {"ozet", "kararlar", "yapilacaklar", "zaman"}|null, "bitti": false}
Kayıt 90 sn büyümeyince (toplantı bitti) son parça işlenir, bitti=true yazılır ve çıkılır.
Ses motoru: mlx-whisper (bir kez yüklenir); özet: Ollama gemma3:4b (3 dakikada bir, kısa istem).
"""
import os
os.environ["VH_TOPLANTI"] = "1"          # canlı yazıya dökme yalnızca toplantılar içindir (Claude izni ayrı)
import json
import os
import subprocess
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))

ARALIK = 8.0            # kaç saniyede bir yeni ses bakılır
PAY = 1.5               # dosyanın en sonundaki (henüz tamamlanmamış) saniyeler işlenmez
OZET_ARALIGI = 180.0    # şu ana kadar özeti
BITIS_BEKLE = 90.0      # dosya bu kadar süre büyümezse toplantı bitmiş sayılır
GERIDE_SN = 150.0       # tampon bundan uzunsa (Mac yoğun, çözüm gerçek zamanın gerisinde) eski kısım atlanır; tam metin toplantıdan sonra ayrıca çıkar
TUT_SN = 60.0           # atlarken son bu kadar saniye tutulur
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"


def log(m):
    print(m, flush=True)


def _kayit(yol):
    """Kaydedicinin canlı durum dosyası (kayitlar/.kayit_canli.json): {kayit, hedef, parcalar: [{sistem, mik, ofset}]}."""
    try:
        return json.loads(Path(yol).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def sure_sn(yol):
    """Büyüyen (parçalı) m4a'nın şu anki okunabilir süresi. Kaydedici durum dosyasında: son parçanın ofseti + süresi
    (2026-10-27: kaydedici sesi toplantı boyunca ara dosyalara yazıyor, asıl m4a ancak bitince oluşuyordu; canlı yazı hiç başlamıyordu)."""
    if str(yol).endswith(".json"):
        k = _kayit(yol); P = k.get("parcalar") or []
        if not P:
            return 0.0
        son = P[-1]
        return float(son.get("ofset", 0)) + max(sure_sn(son.get("sistem", "")), sure_sn(son.get("mik", "")))
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(yol)],
                           capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def ses_oku(yol, bas, bit):
    import numpy as np
    if str(yol).endswith(".json"):                              # parçalar: sistem sesi + mikrofon karıştırılır, kopukluk yerleri sessiz
        out = np.zeros(max(0, int((bit - bas) * 16000)), dtype=np.float32)
        for p in _kayit(yol).get("parcalar") or []:
            o = float(p.get("ofset", 0)); d = max(sure_sn(p.get("sistem", "")), sure_sn(p.get("mik", "")))
            s, e = max(bas, o), min(bit, o + d)
            if e - s < 0.05:
                continue
            girdi = [x for x in (p.get("sistem"), p.get("mik")) if x and Path(x).exists() and Path(x).stat().st_size > 2000]
            if not girdi:
                continue
            a = [FFMPEG, "-v", "error"]
            for x in girdi:
                a += ["-ss", f"{s - o:.3f}", "-to", f"{e - o:.3f}", "-i", x]
            if len(girdi) == 2:
                a += ["-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest:normalize=0"]
            r = subprocess.run(a + ["-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, timeout=120)
            x = np.frombuffer(r.stdout, dtype=np.float32)
            i = int((s - bas) * 16000); x = x[:max(0, len(out) - i)]
            out[i:i + len(x)] = x
        return out
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{bas:.3f}", "-to", f"{bit:.3f}", "-i", str(yol),
                        "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, timeout=120)
    return np.frombuffer(r.stdout, dtype=np.float32)


def yaz(durum_yolu, durum):
    tmp = Path(str(durum_yolu) + ".tmp")
    tmp.write_text(json.dumps(durum, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, durum_yolu)


def ozet_cikar(segmentler, onceki):
    import ozet as ozet_modulu
    if not ozet_modulu.hazir():
        return None
    metin = " ".join(s["metin"] for s in segmentler)
    kelimeler = metin.split()
    son = " ".join(kelimeler[-2500:])
    onceki_metin = ""
    if onceki:
        onceki_metin = ("Önceki özet: " + (onceki.get("ozet") or "") + "\nÖnceki kararlar: " + "; ".join(onceki.get("kararlar") or [])
                        + "\nÖnceki yapılacaklar: " + "; ".join(onceki.get("yapilacaklar") or []) + "\n\n")
    istem = (
        "Süren bir toplantının şu ana kadarki konuşması aşağıda. Türkçe, kısa ve somut yaz.\n"
        "- ozet: 2-3 cümle, şu ana kadar ne konuşuldu.\n- kararlar: konuşmacıların açıkça aldığı kararlar (yoksa boş).\n"
        "- yapilacaklar: birinin yapacağını söylediği işler (yoksa boş). Önceki listeyi koru, yenileri ekle, tekrarı birleştir.\n"
        "- Bu bir sunum, anlatı ya da sohbetse ve açık karar/iş yoksa kararlar ve yapilacaklar BOŞ kalsın; uydurma.\n"
        "Yalnızca JSON: {\"ozet\": \"...\", \"kararlar\": [\"...\"], \"yapilacaklar\": [\"...\"]}\n\n" + onceki_metin + "Konuşma:\n" + son
    )
    try:
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=8192, zaman_asimi=240)) or {}
    except Exception as e:  # noqa: BLE001
        log(f"özet hatası: {e}"); return onceki
    if not c.get("ozet"):
        return onceki
    return {"ozet": str(c.get("ozet"))[:800], "kararlar": [str(x) for x in (c.get("kararlar") or [])][:12],
            "yapilacaklar": [str(x) for x in (c.get("yapilacaklar") or [])][:12], "zaman": time.time()}


def main():
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(1)
    yol, durum_yolu = Path(sys.argv[1]), Path(sys.argv[2])
    durum_yolu.parent.mkdir(parents=True, exist_ok=True)
    import numpy as np
    import mlx.core as mx
    import mlx_whisper
    from mlx_whisper.transcribe import ModelHolder
    from mlx_whisper.audio import log_mel_spectrogram, pad_or_trim, N_FRAMES
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    import terimler
    from transkript import MLX_MODELLER, halusinasyon_mu, _pencereler_olustur

    repo = MLX_MODELLER["large-v3-turbo"]
    model = ModelHolder.get_model(repo, mx.float16)
    kayit_modu = str(yol).endswith(".json")
    dosya_ad = (_kayit(yol).get("hedef") or str(yol)) if kayit_modu else str(yol)
    durum = {"dosya": dosya_ad, "kaynak": str(yol), "baslangic": time.time(), "guncelleme": time.time(), "islenen_sn": 0.0, "dil": None,
             "segmentler": [], "ozet": None, "bitti": False, "atlanan_sn": 0.0, "gecikme": 0.0}
    if durum_yolu.exists():                                     # site yeniden başladıysa kaldığı yerden sür
        try:
            eski = json.loads(durum_yolu.read_text(encoding="utf-8"))
            if not eski.get("bitti") and eski.get("dosya") == dosya_ad:
                durum.update({k: eski[k] for k in ("baslangic", "islenen_sn", "dil", "segmentler", "ozet") if k in eski})
                log(f"Kaldığı yerden sürüyor: {durum['islenen_sn']:.0f} sn, {len(durum['segmentler'])} segment")
        except Exception:  # noqa: BLE001
            pass
    yaz(durum_yolu, durum)
    log(f"Canlı yazıya dökme başladı: {Path(dosya_ad).name}")
    son_buyume, son_sure, son_ozet = time.time(), 0.0, time.time()
    kuyruk = np.zeros(0, dtype=np.float32); kuyruk_bas = durum["islenen_sn"]     # henüz çözülmemiş ses tamponu ve başlangıç saniyesi
    son_ozet_seg = len(durum["segmentler"])

    def dil_tani(kesit):
        mel = log_mel_spectrogram(kesit, n_mels=model.dims.n_mels)
        mel = pad_or_trim(mel, N_FRAMES, axis=-2).astype(mx.float16)
        _, p = model.detect_language(mel)
        p = p[0] if isinstance(p, list) else p
        d = max(p, key=p.get)
        return d, float(p[d])

    while True:
        if not yol.exists():
            log("Kayıt dosyası kayboldu; bitiriliyor."); break
        toplam = sure_sn(yol)
        bitti = False
        if kayit_modu:
            k = _kayit(yol)
            if k.get("hedef") != dosya_ad or not k.get("kayit") or time.time() - float(k.get("guncelleme", 0)) > 60:
                bitti = True                                    # kayıt bitti (kaydedici kayit:false yazdı) ya da başka kayda geçildi
        if bitti:
            pass
        elif toplam > son_sure + 0.5:
            son_sure, son_buyume = toplam, time.time()
        elif time.time() - son_buyume > BITIS_BEKLE:
            bitti = True
        hedef = toplam if bitti else max(0.0, toplam - PAY)
        if hedef > durum["islenen_sn"] + (0.5 if bitti else 4.0):
            yeni = ses_oku(yol, durum["islenen_sn"], hedef)
            if len(yeni):
                if not len(kuyruk):
                    kuyruk_bas = durum["islenen_sn"]
                kuyruk = np.concatenate([kuyruk, yeni])
                durum["islenen_sn"] = hedef
            # 2026-10-24: 22 dk'lık toplantıda yoğun Mac'te yalnız ilk 6 dk çözülebilmişti; fısıltı kartları hiç gelmedi. Çok geride kalınca atla.
            if not bitti and len(kuyruk) / 16000 > GERIDE_SN:
                atla = len(kuyruk) / 16000 - TUT_SN
                kuyruk = kuyruk[int(atla * 16000):]; kuyruk_bas += atla
                durum["atlanan_sn"] = round(durum.get("atlanan_sn", 0) + atla, 1)
                log(f"Gerçek zamanın gerisinde kalındı; {atla:.0f} sn atlandı (tam metin toplantıdan sonra çıkar)")
            # Tampondaki konuşma aralıkları: sondaki (bitmemiş olabilecek) aralık bekletilir
            if len(kuyruk) >= 16000 * 2:
                vad = get_speech_timestamps(kuyruk, VadOptions(min_silence_duration_ms=500, speech_pad_ms=300, threshold=0.4))
                konusma = [(v["start"] / 16000, v["end"] / 16000) for v in vad]
                tampon_sn = len(kuyruk) / 16000
                if konusma and not bitti and tampon_sn - konusma[-1][1] < 0.8:
                    konusma = konusma[:-1]                              # son aralık hâlâ sürüyor olabilir
                if konusma or bitti:
                    if durum["dil"] is None and konusma:
                        ilk = kuyruk[int(konusma[0][0] * 16000):int(min(konusma[0][0] + 30, tampon_sn) * 16000)]
                        if len(ilk) >= 16000 * 3:
                            try:
                                d, p = dil_tani(ilk); durum["dil"] = d if p >= 0.5 else "tr"
                            except Exception:  # noqa: BLE001
                                durum["dil"] = "tr"
                    dil = durum["dil"] or "tr"
                    ipucu = terimler.ipucu_yap(dil, [], [])
                    pencereler = _pencereler_olustur(konusma, tampon_sn) if konusma else []
                    islenen_son = 0.0
                    for pb, pe in pencereler:
                        kesit = kuyruk[int(max(0, pb - 0.3) * 16000):int(min(tampon_sn, pe + 0.3) * 16000)]
                        if len(kesit) < 16000 * 0.5:
                            continue
                        try:
                            r = mlx_whisper.transcribe(kesit, path_or_hf_repo=repo, language=dil, word_timestamps=False,
                                                       condition_on_previous_text=False, no_speech_threshold=0.6,
                                                       temperature=(0.0, 0.2, 0.4), initial_prompt=ipucu, verbose=None)
                        except Exception as e:  # noqa: BLE001
                            log(f"çözüm hatası: {e}"); continue
                        for seg in r.get("segments", []):
                            m = (seg.get("text") or "").strip()
                            if not m or seg.get("compression_ratio", 0) > 2.6:
                                continue
                            if seg.get("avg_logprob", 0) < -1.2 and seg.get("no_speech_prob", 0) > 0.5:
                                continue
                            sb = kuyruk_bas + max(0, pb - 0.3) + float(seg["start"]); se = kuyruk_bas + max(0, pb - 0.3) + float(seg["end"])
                            if halusinasyon_mu(m, dil, sb, 10 ** 9):
                                continue
                            durum["segmentler"].append({"bas": round(sb, 2), "bit": round(se, 2), "metin": m})
                            log(f"[{int(sb) // 60:02d}:{int(sb) % 60:02d}] {m}")
                        islenen_son = max(islenen_son, pe)
                        durum["gecikme"] = round(max(0.0, sure_sn(yol) - (kuyruk_bas + pe)), 1)
                        durum["guncelleme"] = time.time(); yaz(durum_yolu, durum)      # her pencereden sonra: asistan ve arayüz ilerlemeyi görsün
                    # Tamponu kırp: işlenen son aralığa kadar olan kısım atılır
                    if bitti:
                        kuyruk = np.zeros(0, dtype=np.float32)
                    elif islenen_son > 0:
                        kes = int(islenen_son * 16000)
                        kuyruk = kuyruk[kes:]; kuyruk_bas += islenen_son
                durum["guncelleme"] = time.time()
                yaz(durum_yolu, durum)
        # Şu ana kadar özeti
        if durum["segmentler"] and (time.time() - son_ozet >= OZET_ARALIGI or bitti) and len(durum["segmentler"]) - son_ozet_seg >= 6:
            durum["ozet"] = ozet_cikar(durum["segmentler"], durum["ozet"])
            son_ozet, son_ozet_seg = time.time(), len(durum["segmentler"])
            durum["guncelleme"] = time.time(); yaz(durum_yolu, durum)
            log("özet güncellendi")
        if bitti:
            durum["bitti"] = True; durum["guncelleme"] = time.time(); yaz(durum_yolu, durum)
            log("Kayıt bitti; canlı yazıya dökme kapandı.")
            break
        time.sleep(ARALIK)


if __name__ == "__main__":
    main()

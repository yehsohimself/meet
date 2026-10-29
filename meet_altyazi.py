"""Toplantı altyazıları (2026-10-25; Tactiq'in yolu): Chrome uzantısı Google Meet / Teams altyazı satırlarını konuşmacı adı ve mutlak zamanla
toplar (`kayitlar/uzanti_altyazi.jsonl`). Toplantı bitince ses kaydının yazısıyla birlikte kullanılır:

1. Konuşmacı: her ses bölümü altyazı satırlarıyla metin (yoksa zaman) üzerinden eşlenir; bölümün altyazıdaki konuşanı, kümesinin çoğunluğundan
   farklıysa ve o ad başka bir kümenin çoğunluğuysa bölüm o kümeye taşınır. Altyazının konuşanları ayrıca ad eşleme olayı olur.
2. Metin: altyazı ses yazısıyla aynı dildeyse (örtüşme ≥ ESIK) ses yazısında boş kalan yerlere altyazıdaki söz eklenir. Sonra Claude konuşmanın
   bütününü yorumlar ve yanlış duyulduğunu düşündüğü 1-4 kelimelik ifadeleri düzeltir: doğrusu altyazıda görünüyorsa kaynak 'altyazi', konuşmanın
   bağlamından çıkıyorsa 'baglam' ("muhtemelen şunu demiştir"). Her düzeltme sesçe benzer olmalı (terimler._claude_oneri_gecerli); duyulan hali
   `ham_metin` ve `duzeltmeler`de kalır, okuma ekranında görünür. Altyazı yoksa da bağlam düzeltmesi çalışır.
Ses yazısı esas kalır. Toplantı sohbetine bildirim yazılmaz (kullanıcı kararı).
"""
import json
import re
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
KAYIT = KLASOR / "kayitlar"
DOSYA = KAYIT / "uzanti_altyazi.jsonl"
ESIK = 0.3                      # metin örtüşmesi bundan azsa altyazı başka dilde (ör. Türkçe konuşmaya İngilizce altyazı): metin için kullanılmaz


def kaydet(satirlar, platform=""):
    """Uzantıdan gelen satırları ekler; dosya 8 MB'ı aşınca son 30 bin satır kalır."""
    KAYIT.mkdir(exist_ok=True)
    n = 0
    with open(DOSYA, "a", encoding="utf-8") as f:
        for x in (satirlar or [])[:500]:
            try:
                metin = re.sub(r"\s+", " ", str(x.get("metin") or "")).strip()[:2000]
                if not metin:
                    continue
                ts = float(x.get("ts", 0)); son = float(x.get("son") or ts)
                f.write(json.dumps({"ts": round(ts, 2), "son": round(max(son, ts), 2), "ad": str(x.get("ad") or "")[:60], "metin": metin,
                                    "platform": str(platform or "")[:12]}, ensure_ascii=False) + "\n")
                n += 1
            except (TypeError, ValueError, AttributeError):
                continue
    try:
        if DOSYA.stat().st_size > 8 * 1024 * 1024:
            satir = DOSYA.read_text(encoding="utf-8").splitlines()[-30000:]
            gecici = DOSYA.with_suffix(".tmp"); gecici.write_text("\n".join(satir) + "\n", encoding="utf-8"); gecici.replace(DOSYA)
    except OSError:
        pass
    return n


def aralik(bas, bit):
    """Kayıt aralığına düşen satırlar, kayıt saniyesine göre: [{t, son, ad, metin}]."""
    if not DOSYA.exists():
        return []
    out = []
    for satir in DOSYA.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(satir)
        except ValueError:
            continue
        if bas - 5 <= o.get("ts", 0) <= bit + 5:
            out.append({"t": round(max(0.0, o["ts"] - bas), 2), "son": round(max(0.0, o.get("son", o["ts"]) - bas), 2),
                        "ad": o.get("ad") or "", "metin": o.get("metin") or ""})
    out.sort(key=lambda x: x["t"])
    return out


def _kokler(s):
    return {w[:5] for w in re.findall(r"[^\W\d_]{2,}|\d{2,}", (s or "").casefold())}


def hizala(segmentler, altyazi, pencere=240.0, komsu=300.0):
    """Altyazı zamanlarını ses yazısının zaman çizgisine yerel olarak kaydırır (2026-10-27: 26 Ekim toplantısında kayma başta +30 sn, sonda
    −50 sn idi; ±6 sn'lik eşleşme penceresi çoğu cümleyi kaçırıyordu). Çapa: ≥5 kökü olan bölümün ±pencere içindeki en iyi altyazı eşi
    (kök örtüşmesi ≥0,7). Her altyazı satırının kayması, ±komsu sn içindeki çapaların ortancası. Döner: kaydırılmış kopya ve çapa sayısı."""
    import statistics
    ak = [_kokler(a["metin"]) for a in altyazi]
    capa = []
    for sg in segmentler:
        sk = _kokler(sg.get("metin"))
        if len(sk) < 5:
            continue
        en, ep = None, 0.0
        for j, a in enumerate(altyazi):
            if abs(a["t"] - sg["bas"]) > pencere:
                continue
            p = len(sk & ak[j]) / len(sk)
            if p > ep:
                en, ep = j, p
        if en is not None and ep >= 0.7:
            capa.append((altyazi[en]["t"], sg["bas"] - altyazi[en]["t"]))
    if len(capa) < 5:
        return altyazi, len(capa)
    capa.sort()
    out = []
    for a in altyazi:
        yakin = [f for t, f in capa if abs(t - a["t"]) <= komsu] or [f for _t, f in sorted(capa, key=lambda x: abs(x[0] - a["t"]))[:5]]
        k = statistics.median(yakin)
        out.append(dict(a, t=round(a["t"] + k, 2), son=round(a["son"] + k, 2)))
    return out, len(capa)


def eslestir(segmentler, altyazi):
    """Her bölüm için en uygun altyazı satırı: (segment no → (satır no, puan, yol)). yol 'metin' (kök örtüşmesi) ya da 'zaman'."""
    out = {}
    ak = [_kokler(a["metin"]) for a in altyazi]
    for i, sg in enumerate(segmentler):
        sk = _kokler(sg.get("metin"))
        en, ep, yol = None, 0.0, ""
        for j, a in enumerate(altyazi):
            if a["son"] < sg["bas"] - 6 or a["t"] > sg["bit"] + 6:
                continue
            if len(sk) >= 3:
                p = len(sk & ak[j]) / len(sk)
                if p > ep:
                    en, ep, yol = j, p, "metin"
        if en is not None and ep >= 0.4:
            out[i] = (en, ep, yol); continue
        # metin tutmadı: zaman örtüşmesi (altyazı sözden ~1 sn geç gelir)
        sure = max(0.3, sg["bit"] - sg["bas"]); en, ep = None, 0.0
        for j, a in enumerate(altyazi):
            c = min(sg["bit"], a["son"] - 0.5) - max(sg["bas"], a["t"] - 1.5)
            if c > 0 and c / sure > ep:
                en, ep = j, c / sure
        if en is not None and ep >= 0.5:
            out[i] = (en, round(ep, 2), "zaman")
    return out


def uyum(segmentler, esler):
    """Altyazı ile ses yazısının aynı dilde olduğunun ölçüsü: ≥3 kelimelik bölümlerin metinle eşlenen payı."""
    uzun = [i for i, s in enumerate(segmentler) if len(_kokler(s.get("metin"))) >= 3]
    if not uzun:
        return 0.0
    return round(sum(1 for i in uzun if esler.get(i, (0, 0, ""))[2] == "metin") / len(uzun), 2)


KENDI = {"you", "siz", "sen", "du", "sie"}                  # Meet/Teams altyazısı kullanıcının kendisini adıyla değil böyle yazar


def kendini_adlandir(altyazi, ben):
    """Altyazıda 'You/Siz' diye geçen satırlar kullanıcının adını alır (2026-10-27: 26 Ekim toplantısında 64 satır 'You' idi)."""
    if not ben:
        return altyazi
    for a in altyazi:
        if str(a.get("ad") or "").strip().casefold() in KENDI:
            a["ad"] = ben
    return altyazi


def kume_adlari(segmentler, altyazi, esler):
    """Küme ↔ ad: kümedeki bölümlerin altyazı adlarının süreyle ağırlıklı çoğunluğu (≥%60); bir ad tek kümeye. Döner: {küme: ad}."""
    oy = {}
    for i, (j, _p, _y) in esler.items():
        ad = altyazi[j]["ad"]
        if not ad:
            continue
        k = str(segmentler[i]["k"]); sure = segmentler[i]["bit"] - segmentler[i]["bas"]
        oy.setdefault(k, {}).setdefault(ad, 0.0); oy[k][ad] += sure
    kume_ad, ad_kume = {}, {}
    for k, d in sorted(oy.items(), key=lambda x: -sum(x[1].values())):
        ad, s = max(d.items(), key=lambda x: x[1])
        if s / sum(d.values()) >= 0.6 and ad not in ad_kume:
            kume_ad[k] = ad; ad_kume[ad] = k
    return kume_ad


def konusmaci_duzelt(segmentler, altyazi, esler):
    """Kümeyle altyazıdaki konuşan çelişen bölümleri doğru kümeye taşır. Döner: taşınan bölüm sayısı."""
    kume_ad = kume_adlari(segmentler, altyazi, esler)
    ad_kume = {ad: k for k, ad in kume_ad.items()}
    tasinan = 0
    for i, (j, p, yol) in esler.items():
        ad = altyazi[j]["ad"]; k = str(segmentler[i]["k"])
        if not ad or kume_ad.get(k) == ad or ad not in ad_kume or (yol == "zaman" and p < 0.8):
            continue
        segmentler[i]["k"] = ad_kume[ad]; segmentler[i]["k_altyazi"] = k; tasinan += 1
    return tasinan


def konusmaci_altyazidan(segmentler, altyazi, esler, etiket, esik=0.5):
    """Cümle düzeyinde konuşan (2026-10-27): 13 kişilik toplantıda konuşmacı ayırma birkaç kişiyi aynı kümeye koymuştu (bir kümenin %69'u bir kişi, %16'sı başkası). Meet/Teams altyazısı her cümleyi kimin söylediğini bilir: metinle güçlü eşleşen (kök örtüşmesi ≥ esik) bölüm altyazıdaki
    kişiye geçer. Kişinin zaten bir kümesi varsa (etiket ya da çoğunluk) oraya, yoksa yeni bir küme açılır. Zaman eşleşmesine güvenilmez.
    Döner: (taşınan bölüm sayısı, {küme: ad} etikete eklenecekler/değişecekler)."""
    kume_ad = kume_adlari(segmentler, altyazi, esler)
    etiket = {str(k): v for k, v in (etiket or {}).items()}
    yeni = {}
    for k, ad in kume_ad.items():                                    # adsız küme çoğunluğun adını alır
        if str(etiket.get(k, "")).startswith("Konuşmacı") or k not in etiket:
            yeni[k] = ad
    tum = {**etiket, **yeni}
    ad_kume = {}
    for k, ad in tum.items():
        ad_kume.setdefault(str(ad).casefold(), k)
    sayilar = [int(k) for k in tum if str(k).isdigit()] + [int(s.get("k")) for s in segmentler if str(s.get("k")).isdigit()]
    sira = (max(sayilar) + 100) if sayilar else 100
    tasinan = 0
    for i, (j, p, yol) in esler.items():
        ad = (altyazi[j].get("ad") or "").strip()
        if not ad or yol != "metin" or p < esik:
            continue
        k = ad_kume.get(ad.casefold())
        if k is None:
            k = str(sira); sira += 1; ad_kume[ad.casefold()] = k; yeni[k] = ad
        if str(segmentler[i].get("k")) != k:
            segmentler[i].setdefault("k_altyazi", segmentler[i].get("k")); segmentler[i]["k"] = k; tasinan += 1
    return tasinan, yeni


def olaylar(altyazi):
    """Altyazı satırlarından ad eşleme olayları ({t, ad}); _adlari_esle bunları uzantı olaylarıyla birlikte kullanır."""
    return [{"t": a["t"], "ad": a["ad"]} for a in altyazi if a.get("ad")]


def bosluk_doldur(segmentler, altyazi, esler):
    """Ses yazısının hiç değmediği altyazı satırlarını (≥4 kelime, ≥2 sn) bölüm olarak ekler. Döner: eklenen sayı."""
    kullanilan = {j for j, _p, _y in esler.values()}
    ad_kume = _ad_kume(segmentler, altyazi, esler)
    eklenen = []
    for j, a in enumerate(altyazi):
        if j in kullanilan or len(a["metin"].split()) < 4 or a["son"] - a["t"] < 2:
            continue
        bas, bit = max(0.0, a["t"] - 1.0), max(a["t"], a["son"] - 0.5)
        if any(min(bit, s["bit"]) - max(bas, s["bas"]) > 0.3 for s in segmentler):
            continue
        onceki = [s for s in segmentler if s["bit"] <= bas]
        k = ad_kume.get(a["ad"]) or str((onceki[-1] if onceki else segmentler[0] if segmentler else {"k": "0"})["k"])
        eklenen.append({"bas": round(bas, 2), "bit": round(bit, 2), "k": k, "metin": a["metin"], "kaynak": "altyazi"})
    if eklenen:
        segmentler.extend(eklenen); segmentler.sort(key=lambda s: s["bas"])
    return len(eklenen)


def _ad_kume(segmentler, altyazi, esler):
    sayac = {}
    for i, (j, _p, _y) in esler.items():
        ad = altyazi[j]["ad"]
        if ad and i < len(segmentler):
            sayac.setdefault(ad, {}).setdefault(str(segmentler[i]["k"]), 0); sayac[ad][str(segmentler[i]["k"])] += 1
    return {ad: max(d.items(), key=lambda x: x[1])[0] for ad, d in sayac.items()}


def _norm(s):
    return re.sub(r"[^\w]+", " ", (s or "").casefold()).strip()


def metin_duzelt(segmentler, altyazi, esler, dil="tr", log=print, adlar=None, altyazi_kullan=True):
    """Claude ses yazısını yorumlar ve yanlış duyulduğunu düşündüğü yerleri düzeltir ("muhtemelen şunu değil bunu demiştir"): doğrusu altyazıda
    görünüyorsa kaynak 'altyazi', konuşmanın bağlamından çıkıyorsa 'baglam' (neden yazılır). Her öneri terimler._claude_oneri_gecerli süzgecinden
    geçer (sesçe benzer olmalı; anlamı değiştiren düzeltme kabul edilmez); altyazı kaynaklıda doğrusu altyazıda geçmeli. Döner: [(eski, yeni, kaynak)]."""
    import claude_yaz
    import terimler
    if not claude_yaz.hazir():
        return []
    satirlar = []
    for i, sg in enumerate(segmentler):
        m = (sg.get("metin") or "").strip()
        if not m or sg.get("kaynak") == "altyazi":
            continue
        satir = f"[{i}] {m}"
        e = esler.get(i) if altyazi_kullan else None
        if e and e[2] == "metin":
            a = altyazi[e[0]]["metin"]
            if _norm(a) != _norm(m) and _norm(m) not in _norm(a):
                satir += f"\n     ALTYAZI: {a[:400]}"
        satirlar.append(satir)
    if not satirlar:
        return []
    ozel, musteriler = terimler.ayar_sozlugu()
    sozluk = list(dict.fromkeys([*(adlar or []), *[x["ad"] for x in altyazi if x.get("ad")], *ozel, *musteriler]))[:150]
    yapilan = []
    sistem = "Sen titiz bir toplantı transkripti editörüsün. Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun."
    for p in range(0, len(satirlar), 1200):
        istem = (f"Aşağıda bir toplantının ses kaydından otomatik çıkarılmış yazısı var (dil: {dil}); numaralı satırlar. Bazı satırların altında "
                 "toplantı uygulamasının canlı ALTYAZISI var: özel adları, marka/ürün adlarını, İngilizce terimleri ve sayıları çoğu zaman doğru yazar, "
                 "ama cümleleri kısaltır ve o da yanılabilir.\n"
                 "Görev: konuşmanın bütününü okuyup yorumla; ses tanımanın YANLIŞ DUYDUĞUNU düşündüğün 1-4 kelimelik ifadeleri bul ve kişinin "
                 "muhtemelen ne dediğini yaz. Kaynak 'altyazi': doğrusu satırın altyazısında görünüyor. Kaynak 'baglam': doğrusu konuşmanın akışından, "
                 "geçen adlardan ve konudan anlaşılıyor (ör. aynı toplantıda 'bütçe' konuşulurken bir yerde 'büyüce'; kişi adının yanlış yazımı).\n"
                 "DOKUNMA: konuşmacının kendi söylediği (dil sürçmesi, yanlış bilgi, devrik cümle, dolgu kelimeleri, argo, lakap), noktalama, üslup. "
                 "Doğru Türkçe kelimeleri İngilizceye çevirme. Sesçe benzemeyen, anlamı değiştiren düzeltme yapma. Emin değilsen listeleme.\n"
                 + (f"Toplantıda geçen adlar ve terimler (doğru yazım): {', '.join(sozluk)}\n" if sozluk else "")
                 + 'Biçim: {"duzeltmeler": [{"satir": 12, "eski": "satırda AYNEN geçen ifade", "yeni": "muhtemelen söylenen", '
                   '"kaynak": "altyazi|baglam", "neden": "kısa gerekçe"}]}. Yoksa boş liste.\n\n'
                 + "\n".join(satirlar[p:p + 1200]))
        try:
            c = claude_yaz.sor_json(istem, sistem, zaman_asimi=900)
        except Exception as e:  # noqa: BLE001
            log(f"      Metin yorumlanamadı ({str(e)[:100]})"); return yapilan
        for o in c.get("duzeltmeler") or []:
            try:
                i = int(o.get("satir"))
            except (TypeError, ValueError, AttributeError):
                continue
            if i < 0 or i >= len(segmentler):
                continue
            sg = segmentler[i]
            eski = str(o.get("eski") or "").strip(" .,;:!?\""); yeni = str(o.get("yeni") or "").strip(" .,;:!?\"")
            kaynak = "altyazi" if o.get("kaynak") == "altyazi" else "baglam"
            e = esler.get(i)
            if kaynak == "altyazi" and not (altyazi_kullan and e and _norm(yeni) in _norm(altyazi[e[0]]["metin"])):
                kaynak = "baglam"                                      # altyazıda yoksa bağlam tahmini sayılır
            if not terimler._claude_oneri_gecerli(eski, yeni, sg.get("metin") or ""):
                continue
            sg.setdefault("ham_metin", sg["metin"])
            sg.setdefault("duzeltmeler", []).append({"eski": eski, "yeni": yeni, "kaynak": kaynak, "neden": str(o.get("neden") or "")[:160]})
            sg["metin"] = sg["metin"].replace(eski, yeni, 1)
            terimler._kelimelere_uygula(sg.get("kelimeler") or [], eski, yeni)
            yapilan.append((eski, yeni, kaynak))
    return yapilan


def uygula(segmentler, altyazi, dil="tr", claude=True, log=print, adlar=None, etiket=None):
    """Bütün adımlar; segmentler yerinde değişir. Döner: özet sözlüğü (veri["altyazi"]); etiket verildiyse ozet["etiket"] = etikete
    eklenecek/değişecek adlar (cümle düzeyinde konuşan, konusmaci_altyazidan)."""
    ozet = {"satir": len(altyazi), "zaman": time.strftime("%Y-%m-%d %H:%M")}
    if not segmentler:
        return ozet
    if altyazi:
        altyazi, ozet["capa"] = hizala(segmentler, altyazi)
    esler = eslestir(segmentler, altyazi) if altyazi else {}
    ozet["uyum"] = uyum(segmentler, esler) if altyazi else 0.0
    if altyazi and etiket is not None:
        ozet["konusmaci_duzeltme"], ozet["etiket"] = konusmaci_altyazidan(segmentler, altyazi, esler, etiket)
    else:
        ozet["konusmaci_duzeltme"] = konusmaci_duzelt(segmentler, altyazi, esler) if altyazi else 0
    kullan = bool(altyazi) and ozet["uyum"] >= ESIK
    if kullan:
        ozet["eklenen"] = bosluk_doldur(segmentler, altyazi, esler)
        esler = eslestir(segmentler, altyazi)
    elif altyazi:
        log(f"      Altyazı ses yazısıyla örtüşmüyor (%{int(ozet['uyum'] * 100)}; başka dilde olabilir); yalnız konuşmacı adları için kullanıldı")
    if claude:
        d = metin_duzelt(segmentler, altyazi, esler, dil=dil, log=log, adlar=adlar, altyazi_kullan=kullan)
        ozet["metin_duzeltme"] = len(d)
        ozet["altyazidan"] = sum(1 for x in d if x[2] == "altyazi")
        if d:
            log("      Yorumlanıp düzeltilenler: " + ", ".join(f"{a} → {b}" for a, b, _k in d[:12]))
    ozet["adlar"] = sorted({a["ad"] for a in altyazi if a.get("ad")})[:30]
    if altyazi:
        log(f"      Altyazı: {len(altyazi)} satır, uyum %{int(ozet['uyum'] * 100)}, {ozet['konusmaci_duzeltme']} bölümün konuşmacısı düzeltildi"
            + (f", {ozet.get('eklenen', 0)} boşluk dolduruldu" if ozet.get("eklenen") else ""))
    return ozet

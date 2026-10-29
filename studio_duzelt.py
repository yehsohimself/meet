"""Studio: transkriptte metni yerinde düzeltme ve düzeltmelerden öğrenme (2026-10-24).

paragraf_duzelt(segmentler, bas, bit, yeni_metin): paragrafın (zaman aralığındaki segmentlerin) metnini kullanıcının yazdığı
yeni metinle değiştirir. Kelime kelime karşılaştırılır (difflib); değişmeyen kelimeler zamanını korur, değişenler eski
kelimelerin zaman aralığına yayılır, eklenenler komşu kelimenin segmentine girer. Kelime zamanları (`kelimeler`) olan
segmentlerde ikisi birlikte güncellenir; altyazı ve videoya yakılan altyazı da bu yüzden doğru yerde kalır.

Öğrenme: kısa değişiklikler (≤4 kelime) `profil/studio_duzeltmeler.json`'a yazılır. Özel ad gibi görünen (büyük harfle
başlayan, cümle başı değil), yabancı harf (w, q, x) taşıyan ya da iki kez düzeltilmiş doğru yazımlar `ogrenilen_terimler()`
ile ses modelinin ipucuna ve Claude temizliğinin sözlüğüne girer (terimler.ayar_sozlugu). Böylece aynı ad bir daha
yanlış yazılmaz.
"""
import difflib
import json
import re
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
DOSYA = KLASOR / "profil" / "studio_duzeltmeler.json"
NOKTA = ".,;:!?…\"'“”‘’()"


def _kelime_zamanlari(s):
    """Segmentin kelimeleri [(b, e, w)]: kelime zamanı varsa o, yoksa süre karakter oranıyla bölünür."""
    kel = s.get("kelimeler")
    sozler = (s.get("metin") or "").split()
    if kel and [w for _b, _e, w in kel] == sozler:
        return [tuple(k) for k in kel], True
    toplam = sum(len(w) + 1 for w in sozler) or 1
    t, sure = float(s["bas"]), max(0.01, float(s["bit"]) - float(s["bas"]))
    out = []
    for w in sozler:
        d = sure * (len(w) + 1) / toplam
        out.append((round(t, 3), round(t + d, 3), w)); t += d
    return out, False


def paragraf_duzelt(segmentler, bas, bit, yeni_metin):
    """segmentler yerinde değişir. Döner: {"degisen": n, "ciftler": [(eski, yeni)], "silinen_segment": n} ya da hata için ValueError."""
    idx = [i for i, s in enumerate(segmentler) if s["bas"] >= bas - 0.05 and s["bit"] <= bit + 0.05]
    if not idx:
        raise ValueError("Paragraf bulunamadı.")
    eski = []                                  # (segment sırası, b, e, w)
    zamanli = {}
    for i in idx:
        kel, var = _kelime_zamanlari(segmentler[i])
        zamanli[i] = var
        eski += [(i, b, e, w) for b, e, w in kel]
    yeni = (yeni_metin or "").split()
    if not yeni:
        raise ValueError("Metin boş olamaz.")
    a = [w for *_x, w in eski]
    if a == yeni:
        return {"degisen": 0, "ciftler": [], "silinen_segment": 0}
    yeni_kel = {i: [] for i in idx}
    ciftler = []
    sm = difflib.SequenceMatcher(None, a, yeni, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i1, i2):
                si, b, e, w = eski[k]
                yeni_kel[si].append((b, e, w))
        elif op in ("replace", "delete"):
            if op == "replace":
                b0, e0 = eski[i1][1], eski[i2 - 1][2]
                n = j2 - j1
                for j in range(n):
                    k = i1 + int(j * (i2 - i1) / n)                 # yeni kelime, eski aralıkta orantılı yerdeki segmente
                    b = b0 + (e0 - b0) * j / n
                    yeni_kel[eski[k][0]].append((round(b, 3), round(b + (e0 - b0) / n, 3), yeni[j1 + j]))
                ciftler.append((" ".join(a[i1:i2]), " ".join(yeni[j1:j2])))
            else:
                ciftler.append((" ".join(a[i1:i2]), ""))
        elif op == "insert":
            if i1 > 0:
                si, _b, e, _w = eski[i1 - 1]; t = e
            else:
                si, t, _e, _w = eski[0]
            for j in range(j1, j2):
                yeni_kel[si].append((round(t, 3), round(t + 0.05, 3), yeni[j]))
            ciftler.append(("", " ".join(yeni[j1:j2])))
    silinen = 0
    for i in sorted(idx, reverse=True):
        kel = yeni_kel[i]                          # sıra: metindeki sıra korunur
        s = segmentler[i]
        if not kel:
            segmentler.pop(i); silinen += 1
            continue
        metin = " ".join(w for _b, _e, w in kel)
        if metin != s.get("metin"):
            s["metin"] = metin
            s["elle"] = True
            if zamanli[i]:
                s["kelimeler"] = [[b, e, w] for b, e, w in kel]
            s.pop("guven", None)                   # güven listesi eski kelime sırasına aitti
    return {"degisen": sum(1 for c in ciftler), "ciftler": ciftler, "silinen_segment": silinen}


# ----------------------------------------------------------------------------- öğrenme
def _oku():
    try:
        return json.loads(DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"ciftler": []}


def _yaz(d):
    DOSYA.parent.mkdir(exist_ok=True)
    tmp = DOSYA.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DOSYA)


def _sade(s):
    return s.strip(NOKTA)


def _terim_mi(eski, yeni, cumle_basi):
    """Ses modeline öğretilecek bir yazım mı? Yalnızca noktalama/büyük-küçük harf değişikliği değil; özel ad ya da yabancı terim."""
    e, y = _sade(eski), _sade(yeni)
    if not y or not e or e.lower() == y.lower() or len(y) < 3:
        return False
    if any(ch.isdigit() for ch in y):
        return False
    kelimeler = y.split()
    if len(kelimeler) > 3:
        return False
    if re.search(r"[wqxWQX]", y):
        return True
    if cumle_basi and len(kelimeler) == 1 and y[1:] == y[1:].lower():
        return False                               # cümle başındaki büyük harf ad olduğunu göstermez
    return any(k[:1].isupper() for k in kelimeler)


def kaydet(temel, ciftler, eski_metin):
    """Kısa değişiklikleri kaydeder. Döner: bu düzeltmeyle öğrenilen terimler."""
    if not ciftler:
        return []
    d = _oku()
    once = set(ogrenilen_terimler())
    for eski, yeni in ciftler:
        if not eski or not yeni or len(eski.split()) > 4 or len(yeni.split()) > 4:
            continue
        konum = eski_metin.find(eski)
        cumle_basi = konum == 0 or (konum > 1 and eski_metin[konum - 2] in ".!?")
        d["ciftler"].append({"eski": eski, "yeni": yeni, "temel": temel, "t": time.time(), "terim": _terim_mi(eski, yeni, cumle_basi)})
    d["ciftler"] = d["ciftler"][-600:]
    _yaz(d)
    return [t for t in ogrenilen_terimler() if t not in once]


def ogrenilen_terimler(n=40):
    """Ses modeli ipucuna girecek doğru yazımlar: terim sayılan ya da en az iki kez aynı biçimde düzeltilenler; sık ve yeni olan önce."""
    sayac, son = {}, {}
    for c in _oku().get("ciftler") or []:
        y = _sade(c.get("yeni") or "")
        if not y:
            continue
        k = y.lower()
        sayac.setdefault(k, [y, 0, False])
        sayac[k][1] += 1
        sayac[k][2] = sayac[k][2] or bool(c.get("terim"))
        sayac[k][0] = y
        son[k] = max(son.get(k, 0), c.get("t") or 0)
    secilen = [(v[0], v[1], son[k]) for k, v in sayac.items() if v[2] or (v[1] >= 2 and (v[0][:1].isupper() or re.search(r"[wqx]", v[0], re.I)))]
    secilen.sort(key=lambda x: (-x[1], -x[2]))
    return [x[0] for x in secilen[:n]]


def bilinen_duzeltmeler(n=30):
    """Claude temizliğine örnek: kullanıcının tekrar tekrar yaptığı 'eski → yeni' düzeltmeleri."""
    sayac = {}
    for c in _oku().get("ciftler") or []:
        if c.get("eski") and c.get("yeni"):
            k = (c["eski"], c["yeni"])
            sayac[k] = sayac.get(k, 0) + 1
    return [f"{e} → {y}" for (e, y), n_ in sorted(sayac.items(), key=lambda x: -x[1]) if n_ >= 1][:n]


def ozet():
    d = _oku().get("ciftler") or []
    return {"duzeltme": len(d), "terimler": ogrenilen_terimler()}


if __name__ == "__main__":
    print(json.dumps(ozet(), ensure_ascii=False, indent=1))

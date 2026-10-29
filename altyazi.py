"""altyazi.py - Anlamlı altyazı kırılımı: satırlar ve altyazı parçaları cümlenin anlam birimlerinden bölünür.

Claude kelime dizisini okur ve her anlam biriminin bittiği kelimeyi işaretler (1 = cümle sonu, 2 = yan cümle / virgüllü
bölüm, 3 = söz öbeği: "ana fikir | bunun nedeni", "önümüzdeki hafta | teslim edeceğiz"). Kurallar (satır ≤42 karakter,
1-2 satır, 1,2-7 sn) yine kodla uygulanır; ama kesim her zaman en güçlü anlamlı noktadan yapılır. Sonuç bir kez
hesaplanıp veri["altyazi_kirilim"] = {"imza", "k": {kelime_no: güç}} olarak saklanır; kelimeler değişirse (imza tutmazsa)
eski kural tabanlı bölme kullanılır.

plan_uret(segmentler, dil, log) -> {"imza","k"} | None;  parcalar(segmentler, plan) -> transkript.altyazi_parcalari biçimi
Elle: python altyazi.py transkript_x.json   ·   python altyazi.py --hepsi   (toplantılar hariç tüm videolar)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
SATIR = 42
# Satır/parça bu kelimelerden SONRA bölünmesin (tamlama, belirteç: "büyük | bir risk", "geçen | ay")
BAGLI = set("""bir bu şu o her hiç çok daha en pek gayet geçen gelecek önümüzdeki büyük küçük yeni eski ilk son aynı
başka diğer bazı birçok tüm bütün kendi böyle şöyle öyle the a an of to in on at for with and very""".split())
# Bu kelimelerin ÖNÜNDEN bölmek doğaldır (bağlaç, söylem işaretleyici)
BASLATICI = set("""ve veya ya ama fakat ancak çünkü yani dolayısıyla eğer şimdi örneğin mesela ise hem ne ki oysa
but and so because which that when if""".split())


def _temiz(w):
    return str(w).strip().strip(".,;:!?…\"'“”()").lower()


EKLER = {"da", "de", "ta", "te", "ki", "mi", "mı", "mu", "mü", "misin", "mısın", "musun", "müsün", "miyiz", "mıyız", "midir", "mıdır"}
SIFAT_FIIL = re.compile(r"(dığ|diğ|duğ|düğ|tığ|tiğ|tuğ|tüğ)(ı|i|u|ü)(m|n|mız|miz|muz|müz|nız|niz|nuz|nüz)?$|^(olan|gelen|giden|yapan|eden|denen)$")
TAMLAMA = re.compile(r"[^aeıioöuü](ı|i|u|ü)$|s(ı|i|u|ü)$")


def _puan(kel, i, kirilim):
    """i. kelimeden sonra bölmenin maliyeti (küçük = iyi)."""
    g = kirilim.get(i)
    if g in (1, 2):
        return g
    if str(kel[i][2]).rstrip()[-1:] in ",;:.?!…":
        return 2
    w = _temiz(kel[i][2]); son = _temiz(kel[i + 1][2]) if i + 1 < len(kel) else ""
    if w in BAGLI or son in EKLER:                    # "borçlanmanın | da", "geliyor | mu" bölünmesin
        return 8
    if SIFAT_FIIL.search(w) or (son and TAMLAMA.search(son) and not SIFAT_FIIL.search(son) and len(son) > 3):
        return 7                                       # "çektiğim | parayla", "kredi | kartı"
    if g == 3:
        return 3
    if son in BASLATICI:
        return 4
    return 5


def _kelimeler(segmentler):
    """altyazi_parcalari ile AYNI kelime dizisi: [(b, e, w)]."""
    out = []
    for s in segmentler:
        if s.get("kelimeler"):
            out += [(k[0], k[1], str(k[2]).strip()) for k in s["kelimeler"] if str(k[2]).strip()]
        else:
            parca = s["metin"].split()
            if not parca:
                continue
            toplam = sum(len(p) + 1 for p in parca); t = s["bas"]; sure = max(0.5, s["bit"] - s["bas"])
            for p in parca:
                dt = sure * (len(p) + 1) / toplam
                out.append((t, t + dt, p)); t += dt
    return out


def imza(kelimeler):
    return hashlib.sha1(" ".join(str(k[2]).strip() for k in kelimeler).encode("utf-8")).hexdigest()[:16]


def plan_uret(segmentler, dil="tr", log=print, parca=700):
    import claude_yaz
    if not claude_yaz.hazir():
        return None
    from concurrent.futures import ThreadPoolExecutor
    kel = _kelimeler(segmentler)
    if not kel:
        return None
    gruplar = [list(range(i, min(i + parca, len(kel)))) for i in range(0, len(kel), parca)]
    sistem = ("Sen deneyimli bir altyazı editörüsün. Altyazının okunması kolay olsun diye metni anlam birimlerine ayırırsın. "
              "Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun.")
    sonuc = {}

    def _tek(g):
        satir = " ".join(f"{i}:{str(kel[i][2]).strip()}" for i in g)
        istem = (f"Aşağıda bir konuşmanın kelimeleri numaralarıyla var (dil: {dil}). Her anlam biriminin BİTTİĞİ kelimenin numarasını "
                 "ve gücünü ver: 1 = cümle sonu (düşünce tamamlanıyor), 2 = yan cümle ya da virgüllü bölüm sonu, 3 = söz öbeği sonu "
                 "(özne öbeği | yüklem öbeği gibi doğal nefes yeri; 'büyük bir | sorun' gibi isim tamlamasını ASLA bölme, sıfatı "
                 "isminden, edatı (için, gibi, ile, kadar) öncesinden, 'geçen ay' gibi zaman öbeklerini, 'değil/mi' gibi ekleri fiilden ayırma). Yaklaşık her 2-5 kelimede "
                 "bir işaret olsun; noktalama olmasa da konuşmanın anlamına bak. Biçim: {\"k\": [[numara, güç], ...]}\n\n" + satir)
        try:
            c = claude_yaz.sor_json(istem, sistem, zaman_asimi=600)
        except Exception as e:  # noqa: BLE001
            log(f"      Altyazı kırılımı alınamadı ({str(e)[:80]})"); return
        for x in c.get("k") or []:
            try:
                i, gu = int(x[0]), int(x[1])
            except (TypeError, ValueError, IndexError):
                continue
            if g[0] <= i <= g[-1] and gu in (1, 2, 3):
                sonuc[i] = min(gu, sonuc.get(i, 9))

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(_tek, gruplar))
    if len(sonuc) < len(kel) / 20:                   # neredeyse boş yanıt: kullanma
        return None
    return {"imza": imza(kel), "k": {str(i): g for i, g in sorted(sonuc.items())}, "dil": dil}


def parcalar(segmentler, plan):
    """Anlamlı kırılımla altyazı parçaları. Döner: [{"bas","bit","metin","satirlar","kelimeler"}]."""
    kel = _kelimeler(segmentler)
    k = {int(i): g for i, g in (plan.get("k") or {}).items()}
    for i in range(len(kel) - 1):                    # uzun duraklama da güçlü bir kırılımdır
        if kel[i + 1][0] - kel[i][1] > 1.0:
            k[i] = min(k.get(i, 9), 1)
    if kel:
        k[len(kel) - 1] = 1
    uzun = lambda a, b: len(" ".join(str(x[2]) for x in kel[a:b + 1]))  # noqa: E731
    sinir = 2 * SATIR - 4
    out, bas = [], 0
    while bas < len(kel):
        # bu parçaya sığan en uzak kelime
        son = bas
        while son + 1 < len(kel) and uzun(bas, son + 1) <= sinir and kel[son + 1][1] - kel[bas][0] <= 6.5:
            son += 1
        if son + 1 >= len(kel):
            kes = son
        else:
            # sığan aralıkta en güçlü (en küçük güç numarası) kırılım; eşitse daha uzak olan; çok kısa parça olmasın
            adaylar = [(k[i], -i) for i in range(bas, son + 1) if i in k and (uzun(bas, i) >= 14 or k[i] == 1)
                       and not (i + 1 < len(kel) and _temiz(kel[i + 1][2]) in EKLER)]
            # kart iyi bir satır bölmesine izin vermiyorsa ("hem kredi | kartı" tek seçenekse) daha erken bitir
            iyiler = [a_ for a_ in sorted(adaylar) if _satir_puani(kel[bas:-a_[1] + 1], {j - bas: g for j, g in k.items() if bas <= j < -a_[1]}) < 7]
            if iyiler:
                adaylar = iyiler
            # cümle sonu yeterince doluysa orada bitir (bir sonraki cümleyi aynı karta taşıma)
            erken = [i for i in range(bas, son + 1) if k.get(i) == 1 and uzun(bas, i) >= 18 and kel[i][1] - kel[bas][0] >= 1.0]
            if erken:
                kes = erken[0]
            elif adaylar:
                kes = -min(adaylar)[1]
            else:
                kes = son
                while kes > bas and _puan(kel, kes, k) >= 8:      # "bir", "büyük" gibi bağlı kelimeyle bitirme
                    kes -= 1
        while kes > bas and _satir_puani(kel[bas:kes + 1], {}) >= 99:   # iki satıra hiç sığmıyorsa kısalt
            kes -= 1
        out.append(_parca(kel[bas:kes + 1], {i - bas: g for i, g in k.items() if bas <= i < kes}))
        bas = kes + 1
    # zamanlar: en az 1,2 sn, çakışma yok
    for i, p in enumerate(out):
        p["bit"] = max(p["bit"] + 0.15, p["bas"] + 1.2)
        if i + 1 < len(out):
            p["bit"] = min(p["bit"], out[i + 1]["bas"] - 0.04)
            if p["bit"] <= p["bas"]:
                p["bit"] = p["bas"] + 0.6
    return out


def _satir_puani(kel, kirilim):
    """Kartın en iyi satır bölmesinin maliyeti (tek satıra sığıyorsa 0)."""
    if len(" ".join(str(x[2]) for x in kel)) <= SATIR:
        return 0
    en = 99
    for i in range(len(kel) - 1):
        if len(" ".join(str(x[2]) for x in kel[:i + 1])) <= SATIR and len(" ".join(str(x[2]) for x in kel[i + 1:])) <= SATIR:
            en = min(en, _puan(kel, i, kirilim))
    return en


def _parca(kel, kirilim):
    metin = " ".join(str(x[2]) for x in kel)
    satirlar = [metin]
    if len(metin) > SATIR:
        # satır sonu: her iki satır ≤42 olan noktalardan en güçlü kırılım, eşitse ortaya en yakın
        en = None
        for i in range(len(kel) - 1):
            s1 = " ".join(str(x[2]) for x in kel[:i + 1]); s2 = " ".join(str(x[2]) for x in kel[i + 1:])
            if len(s1) > SATIR or len(s2) > SATIR:
                continue
            puan = (_puan(kel, i, kirilim), abs(len(s1) - len(s2)))
            if en is None or puan < en[0]:
                en = (puan, [s1, s2])
        if en:
            satirlar = en[1]
        else:
            from transkript import _satira_bol
            satirlar = _satira_bol(metin)
    return {"bas": kel[0][0], "bit": kel[-1][1], "metin": metin, "satirlar": satirlar, "kelimeler": [(x[0], x[1], x[2]) for x in kel]}


def gecerli_plan(veri, segmentler):
    p = veri.get("altyazi_kirilim")
    return p if p and p.get("imza") == imza(_kelimeler(segmentler)) else None


def uret_ve_kaydet(json_yolu, log=print):
    json_yolu = Path(json_yolu)
    d = json.loads(json_yolu.read_text(encoding="utf-8")); v, seg = d["veri"], d["segmentler"]
    p = plan_uret(seg, v.get("dil", "tr"), log)
    if not p:
        return False
    v["altyazi_kirilim"] = p
    json_yolu.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    from transkript import yaz_srt
    yaz_srt(json_yolu.with_suffix(".srt"), v, seg)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    if sys.argv[1] == "--hepsi":
        for js in sorted(KLASOR.glob("transkript_*.json")):
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
            if v.get("toplanti") or v.get("altyazi_kirilim"):
                continue
            print(js.stem, "→", "tamam" if uret_ve_kaydet(js) else "atlandı", flush=True)
    else:
        print("tamam" if uret_ve_kaydet(sys.argv[1]) else "olmadı")

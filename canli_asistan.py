"""canli_asistan.py - Toplantı sürerken anlık hatırlatma ve gerçek zamanlı mentörlük (2026-10-22; kullanıcının Transcript tanıtımındaki "toplantı
sırasında anlık hatırlatmalar yapıyor" ve "gerçek zamanlı mentörlük yapıyor, buna şöyle cevap verebilirsin gibi").

Site her ~45 sn'de, canlı yazıya dökmede yeni konuşma biriktiyse çağırır. Girdi: son ~2 dakikanın konuşması (canli.py segmentleri) + bağlam (bu
toplantının hazırlık notu: önceki toplantılardaki kararlar, açık işler, bekleyen sorular; yoksa kullanıcının açık sözleri). Claude (sonnet, toplantı
izniyle) yalnızca gerçekten işe yarıyorsa üretir: {hatirlatma: {metin, dayanak} | null, oneri: {durum, soyle} | null}. Daha önce verilenler istemde;
aynı şey tekrar edilmez. Kartlar `kayitlar/.canli/<ad>.asistan.json` (son 12), `/api/canli` → `asistan`; Transcript canlı kartı ve Chrome yan paneli gösterir.
"""
import json
import os
import re
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent


def _ayar():
    import ortak                                           # tek sürüm (sırlar dahil; 2026-10-25)
    return ortak.ayar()


def baglam(durum):
    """Bu toplantının hazırlık notu (takvimden), yoksa kullanıcının açık sözleri."""
    try:
        import onbrifing
        bas = durum.get("baslangic") or time.time()
        notlar = [k for k in onbrifing.son_kayitlar(saat_once=3, saat_sonra=1) if abs(k.get("bas", 0) - bas) < 40 * 60 and k.get("metin")]
        notlar.sort(key=lambda k: abs(k.get("bas", 0) - bas))     # takvimden ya da canlı (uzantının katılımcı adlarından) hazırlanmış not
        if notlar:
            k = notlar[0]
            return f"Toplantı: {k.get('ad')}\nKatılımcılar: {', '.join(k.get('kisiler') or [])}\nHAZIRLIK NOTU (önceki toplantılardan):\n{k['metin']}"
    except Exception:  # noqa: BLE001
        pass
    try:
        import sozler
        s = sozler.liste()
        acik = (s.get("sozlerin") or [])[:8]
        bek = (s.get("bekledigin") or [])[:6]
        if acik or bek:
            return ("KULLANICININ AÇIK SÖZLERİ (önceki toplantılardan):\n" + "\n".join(f"- {x.get('is')} ({x.get('konu') or ''}, {x.get('ne_zaman') or 'tarihsiz'})" for x in acik)
                    + "\nBAŞKALARINDAN BEKLEDİKLERİ:\n" + "\n".join(f"- {x.get('kim')}: {x.get('is')} ({x.get('konu') or ''})" for x in bek))
    except Exception:  # noqa: BLE001
        pass
    return ""


BEN = re.compile(r"^(you|siz|sen|ben|me)$", re.I)


def _kayit(durum):
    """Kayıt sürerken canlı yazının kaynağı kaydedicinin durum dosyası (kayitlar/.kayit_canli.json; 2026-10-27): başlangıç ve parçalar oradan."""
    k = str(durum.get("kaynak") or "")
    if not k.endswith(".json"):
        return None
    try:
        return json.loads(Path(k).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _baslangic(durum):
    """Kaydın gerçek başlangıcı: canlı süreç dosya büyüdükten sonra başlıyor (≤1 dk gecikme); dosyanın oluşma zamanı daha doğru."""
    k = _kayit(durum)
    if k and k.get("baslangic"):
        return float(k["baslangic"])
    try:
        st = os.stat(durum.get("dosya") or "")
        return getattr(st, "st_birthtime", 0) or durum.get("baslangic") or time.time()
    except OSError:
        return durum.get("baslangic") or time.time()


def konusmacilar(durum):
    """Canlı bölümlere konuşmacı adı (uzantının Meet/Teams altyazısından okuduğu 'kim konuşuyor' olayları, mutlak zamanla) ve konuşma payları
    (sn). Döner: (etiketli bölümler [(ad|'', metin, bas, bit)], paylar {ad: sn}, toplam_sn)."""
    seg = durum.get("segmentler") or []
    bas = _baslangic(durum)
    olay = []
    try:
        for satir in (KLASOR / "kayitlar" / "uzanti_olaylar.jsonl").read_text(encoding="utf-8").splitlines()[-4000:]:
            try:
                o = json.loads(satir)
            except ValueError:
                continue
            if bas - 30 <= o.get("ts", 0) <= time.time() + 5 and o.get("ad"):
                olay.append((o["ts"], o["ad"]))
    except OSError:
        pass
    olay.sort()
    ben = (_ayar().get("benim_adim") or "").strip()
    out, pay = [], {}
    j = 0
    for s in seg:
        t = bas + s["bas"] + 1.5
        while j + 1 < len(olay) and olay[j + 1][0] <= t:
            j += 1
        ad = olay[j][1] if olay and olay[j][0] <= t and t - olay[j][0] < 90 else ""
        if ad and (BEN.match(ad) or (ben and ad.casefold().startswith(ben.split()[0].casefold()))):
            ad = ben.split()[0] if ben else "Ben"
        out.append((ad, s["metin"], s["bas"], s["bit"]))
        if ad:
            pay[ad] = pay.get(ad, 0) + max(0.0, s["bit"] - s["bas"])
    if not pay:                                    # uzantı yok (Zoom/Teams masaüstü): kullanıcının payı kaydedicinin ayrı mikrofon dosyasından, yaklaşık
        sn = _mik_konusma_sn(durum)
        konusma = sum(max(0.0, s["bit"] - s["bas"]) for s in seg)
        if sn is not None and konusma >= 60:
            ad = ben.split()[0] if ben else "Ben"
            sn = min(sn, konusma)
            pay = {ad: sn, "Diğerleri": max(0.0, konusma - sn)}
    return out, pay, sum(pay.values())


_MIK = {}


def _mik_konusma_sn(durum):
    """'Toplantı X.mik.m4a' (yalnız mikrofon) içinde sessiz olmayan süre (ffmpeg silencedetect, -30 dB, 0,6 sn). Ayar: 21 Ekim'deki bir toplantı kaydında
    -30 dB = 11,7 dk, transkript etiketi 11,5 dk (-32 dB hoparlör sızıntısıyla 16,6 dk). Mikrofon kazancı değişirse kayabilir; yaklaşık. 45 sn önbellek."""
    k = _kayit(durum)
    if k:                                                    # kayıt sürüyor: mikrofon parçalarının toplamı (parça başına boyutla önbellek)
        toplam, var_ = 0.0, False
        for p in k.get("parcalar") or []:
            m = p.get("mik") or ""
            if os.path.exists(m):
                sn = _sessiz_olmayan(m); var_ = var_ or sn is not None; toplam += sn or 0.0
        return toplam if var_ else None
    yol = str(durum.get("dosya") or "")
    if not yol.endswith(".m4a"):
        return None
    mik = yol[:-4] + ".mik.m4a"
    if not os.path.exists(mik):
        return None
    return _sessiz_olmayan(mik)


def _sessiz_olmayan(mik):
    import subprocess
    try:
        boy = os.path.getsize(mik)
    except OSError:
        return None
    onb = _MIK.get(mik)
    if onb and (time.time() - onb[0] < 45 or onb[2] == boy):
        return onb[1]
    try:
        r = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-nostdin", "-i", mik, "-af", "silencedetect=n=-30dB:d=0.6", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=60)
        sure = re.findall(r"time=(\d+):(\d+):([\d.]+)", r.stderr)
        toplam = (int(sure[-1][0]) * 3600 + int(sure[-1][1]) * 60 + float(sure[-1][2])) if sure else 0
        sessiz = sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r.stderr))
        sn = max(0.0, toplam - sessiz)
    except Exception:  # noqa: BLE001
        return None
    _MIK[mik] = (time.time(), sn, boy)
    return sn


def _amac():
    """Son 3 saatte yazılmış toplantı amacı (Sıradaki toplantı kartı, kayıt paneli ya da yan panel)."""
    try:
        d = json.loads((KLASOR / "kayitlar" / "amaclar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    L = sorted((v for v in d.values() if isinstance(v, dict) and v.get("metin") and time.time() - v.get("zaman", 0) < 3 * 3600), key=lambda v: -v.get("zaman", 0))
    return L[0]["metin"] if L else ""


def _dersler():
    """Danışman notlarından tekrar eden dersler ve kişinin daha iyi ifade kalıpları (son 6 toplantı)."""
    try:
        L = json.loads((KLASOR / "profil" / "danisman.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return [], []
    dersler, kalip = [], []
    for x in L[-6:]:
        dersler += [d for d in x.get("dersler") or [] if d not in dersler]
        kalip += [k for k in x.get("kalip") or [] if k not in kalip]
    return dersler[-10:], kalip[-6:]


def _kalan_dk(durum):
    try:
        import takvim
        e = takvim.suren()
        if e and e.get("bit"):
            return max(0, round((e["bit"] - time.time()) / 60))
    except Exception:  # noqa: BLE001
        pass
    return None


def uret(durum, onceki, log=print):
    """Üç kart türü (2026-10-23 mentörlük genişletildi; kullanıcı: "toplantı sırasında mentör önerilerde bulunuyor" demiştik): hatırlatma (bağlamla
    ilgili), öneri (soruya/itiraza cevap cümlesi), MENTÖR (toplantının gidişatına koçluk: konuşma dengesi, sahipsiz karar, fiyatsız kapsam, amaçtan
    sapma, karşı tarafın çekincesi, kapanış; kişinin danışman notlarındaki tekrar eden dersleri). Mentör en çok 3 dakikada bir."""
    seg = durum.get("segmentler") or []
    if not seg:
        return None
    son_bit = seg[-1]["bit"]
    etiketli, pay, toplam = konusmacilar(durum)
    son = [x for x in etiketli if x[3] >= son_bit - 150]
    metin = "\n".join((f"{a}: " if a else "") + m for a, m, _b, _e in son)
    if len(metin.split()) < 15:
        return None
    import claude_yaz
    ben = (_ayar().get("benim_adim") or "Kullanıcı").split()[0]
    son_mentor = max([k.get("sn", 0) for k in onceki if k.get("tur") == "mentor"] or [-1e9])
    mentor_serbest = son_bit - son_mentor >= 180
    hatirlatma_serbest = son_bit - max([k.get("sn", 0) for k in onceki if k.get("tur") == "hatirlatma"] or [-1e9]) >= 180
    yakin_turler = sorted({k.get("konu_turu") for k in onceki if k.get("tur") == "mentor" and son_bit - k.get("sn", 0) < 360 and k.get("konu_turu")})
    pay_metni = ", ".join(f"{a} %{round(100 * v / toplam)}" for a, v in sorted(pay.items(), key=lambda x: -x[1])) if toplam >= 60 else ""
    if pay_metni and "Diğerleri" in pay:
        pay_metni += " (mikrofondan ölçüldü, yaklaşık; yalnız belirgin dengesizlikte kullan)"
    son5 = [x for x in etiketli if x[3] >= son_bit - 300 and x[0]]
    pay5 = {}
    for a, _m, b, e in son5:
        pay5[a] = pay5.get(a, 0) + (e - b)
    t5 = sum(pay5.values())
    pay5_metni = ", ".join(f"{a} %{round(100 * v / t5)}" for a, v in sorted(pay5.items(), key=lambda x: -x[1])) if t5 >= 45 else ""
    dersler, kalip = _dersler()
    amac = _amac()
    kalan = _kalan_dk(durum)
    oz = durum.get("ozet") or {}
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return None
        c = claude_yaz.sor_json(
            f"Bir toplantı şu an sürüyor ({round(son_bit / 60)}. dakika{f', takvime göre ~{kalan} dk kaldı' if kalan is not None else ''}). Sen {ben}'in yanında oturan, "
            "işini bilen bir mentörsün; kulağına fısıldıyorsun. Yalnızca GERÇEKTEN işe yarayacaksa konuş; gereksiz kart dikkat dağıtır.\n"
            "Üç tür kart var, her biri null olabilir (çoğu zaman en az ikisi null):\n"
            + ("1) hatirlatma: SON konuşmadaki bir konu aşağıdaki bağlamla (önceki toplantıların kararları, açık işler, sözler, bekleyen sorular) doğrudan "
               "ilgiliyse ve şu an söylenmezse kaçacaksa tek cümle hatırlatma + dayanak. Bağlamda yoksa uydurma. Küçük bağlantılar için null.\n"
               if hatirlatma_serbest else "1) hatirlatma: bu turda null (az önce verildi).\n")
            + f"2) oneri: SON konuşmada kullanıcıya ({ben}) bir soru, itiraz ya da talep geldiyse: durum (kısa) + onun söyleyebileceği TEK doğal cümle (onun ağzından).\n"
            + (f"3) mentor: toplantının GİDİŞATINA dair koçluk; şu durumlardan biri açıkça oluyorsa: {ben} çok konuşuyor ya da hiç konuşmuyor (paylara bak); "
               "bir karar konuşuldu ama sahibi/tarihi yok; ek iş/kapsam isteniyor ve süre-ücret konuşulmadan kabul ediliyor; konu toplantının amacından uzaklaştı; "
               "karşı taraf çekince gösteriyor, geri çekiliyor ya da tekrar ediyor ve bu kaçıyor; zaman azalıyor ve kararlar toparlanmadı; "
               f"{ben}'in danışman notlarındaki tekrar eden derslerinden biri şu an YİNE yaşanıyor. Kart: konu_turu (denge | karar | kapsam | amac | cekince | kapanis | "
               "ders), gozlem (TEK kısa cümle, ≤110 karakter, sen dili, somut: kim, ne), yap (tek eylem, emir kipi, ≤10 kelime), soyle (isteğe bağlı: onun ağzından "
               "tek doğal cümle). Genel tavsiye ('dinlemeyi unutma') YASAK; yalnızca bu andaki duruma özgü."
               + (f" Son dakikalarda şu türlerde kart verildi, bunları TEKRARLAMA: {', '.join(yakin_turler)}." if yakin_turler else "") + "\n"
               if mentor_serbest else "3) mentor: bu turda null (az önce verildi).\n") +
            "Önceki kartları tekrar etme. Kurumsal klişe yok, doğal Türkçe.\n"
            'JSON: {"hatirlatma": {"metin": "...", "dayanak": "..."} | null, "oneri": {"durum": "...", "soyle": "..."} | null, '
            '"mentor": {"konu_turu": "denge", "gozlem": "...", "yap": "...", "soyle": "..."} | null}\n\n'
            + (f"TOPLANTININ AMACI ({ben} yazdı): {amac}\n" if amac else "")
            + (f"KONUŞMA PAYLARI (şu ana kadar): {pay_metni}\n" if pay_metni else "")
            + (f"KONUŞMA PAYLARI (son 5 dk): {pay5_metni}\n" if pay5_metni else "")
            + (f"ŞU ANA KADAR: {oz.get('ozet', '')}\nKararlar: {'; '.join(oz.get('kararlar') or [])}\nYapılacaklar: {'; '.join(map(str, oz.get('yapilacaklar') or []))}\n" if oz else "")
            + (f"{__import__('harfler').ust(ben)}'İN TEKRAR EDEN DERSLERİ (önceki toplantıların danışman notlarından):\n" + "\n".join(f"- {d}" for d in dersler) + "\n" if dersler else "")
            + (f"{__import__('harfler').ust(ben)}'İN DAHA İYİ İFADE ÖRNEKLERİ (öneri ve mentör cümlelerinin tonu böyle):\n" + "\n".join(f"- {k}" for k in kalip) + "\n" if kalip else "")
            + f"\nBAĞLAM:\n{baglam(durum) or '(önceki toplantı bilgisi yok)'}\n\nÖNCEKİ KARTLAR:\n"
            + ("\n".join(f"- {k.get('metin') or k.get('soyle') or k.get('gozlem')}" for k in onceki[-8:]) or "-")
            + f"\n\nSON KONUŞMA (yaklaşık son 2,5 dakika{'; satır başında konuşan' if any(x[0] for x in son) else ''}):\n{metin}",
            model_adi="sonnet", zaman_asimi=90)
    kartlar = []
    h, o, mt = c.get("hatirlatma"), c.get("oneri"), c.get("mentor")
    if hatirlatma_serbest and isinstance(h, dict) and str(h.get("metin") or "").strip():
        kartlar.append({"tur": "hatirlatma", "metin": str(h["metin"]).strip()[:240], "dayanak": str(h.get("dayanak") or "")[:200], "sn": son_bit, "zaman": time.time()})
    if isinstance(o, dict) and str(o.get("soyle") or "").strip():
        kartlar.append({"tur": "oneri", "durum": str(o.get("durum") or "")[:160], "soyle": str(o["soyle"]).strip()[:280], "sn": son_bit, "zaman": time.time()})
    tur_ = str(mt.get("konu_turu") or "")[:20] if isinstance(mt, dict) else ""
    if (mentor_serbest and isinstance(mt, dict) and str(mt.get("gozlem") or "").strip() and str(mt.get("yap") or "").strip()
            and not (tur_ and tur_ in yakin_turler)):                # aynı tür koçluk 6 dk içinde tekrar etmez
        kartlar.append({"tur": "mentor", "konu_turu": tur_, "gozlem": str(mt["gozlem"]).strip()[:220], "yap": str(mt["yap"]).strip()[:120],
                        "soyle": str(mt.get("soyle") or "").strip()[:240], "sn": son_bit, "zaman": time.time()})
    if kartlar:
        log(f"Canlı asistan: {', '.join(k['tur'] for k in kartlar)}")
    return kartlar

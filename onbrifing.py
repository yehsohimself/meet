"""onbrifing.py - Toplantıdan önce bağlam hatırlatması.

Takvimde 5-15 dk içinde başlayacak, başkalarının da davetli olduğu bir toplantı varsa: aynı kişilerle (e-posta, ad) ya da
aynı müşteriyle yapılan son toplantılar bulunur; açık işler, bekleyen sorular, son kararlar Claude ile kısa bir
hazırlık notuna dönüşür (Claude yoksa notlardan düz liste). Site bildirim gösterir; Toplantılar sayfasında ve Chrome
uzantısının yan panelinde görünür. Kayıt: kayitlar/.on_brifing/<uid>.json

hazirla(etkinlik) -> {...}; siradaki(saat=24) -> en yakın uygun etkinlik; adaylar(5, 15) -> zamanı gelmiş olanlar.
Elle: python onbrifing.py            (sıradaki toplantı için hazırlar ve yazdırır)
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
KLASOR_BRIF = KLASOR / "kayitlar" / ".on_brifing"
GENEL_ALAN = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "icloud.com", "yahoo.com", "yandex.com", "proton.me"}


def _ayar():
    import ortak                                           # tek sürüm (sırlar dahil; 2026-10-25)
    return ortak.ayar()


def _benim(ay=None):
    ay = ay or _ayar()
    return {a.strip().lower() for a in (ay.get("benim_epostalar") or []) if a.strip()}, (ay.get("benim_adim") or "").strip().casefold()


def _etkinlikler(pencere_bas, pencere_bit):
    import takvim
    metin = takvim.ics_getir()
    out = []
    for e in takvim.etkinlikler(metin or ""):
        if e["tumgun"] or e["iptal"]:
            continue
        for ob, oe in takvim._oluslar(e, pencere_bas, pencere_bit):
            if pencere_bas <= ob <= pencere_bit:
                out.append({**e, "bas": ob, "bit": oe})
    return sorted(out, key=lambda x: x["bas"])


def _baskalari(e, ay=None):
    """Kullanıcı dışındaki katılımcılar: [{"ad","eposta"}]."""
    benim_ep, benim_ad = _benim(ay)
    out = []
    for k in e.get("katilimcilar") or []:
        ep = (k.get("eposta") or "").lower()
        if not ep and not k.get("ad"):          # canlı toplantıda uzantı yalnızca adları bilir (e-posta yok)
            continue
        if ep and (ep in benim_ep or "resource.calendar" in ep or ep.endswith("group.calendar.google.com")):
            continue
        if benim_ad and (k.get("ad") or "").casefold().startswith(benim_ad):
            continue
        out.append({"ad": k.get("ad") or ep.split("@")[0], "eposta": ep})
    return out


def _toplanti_mi(e, ay=None):
    import takvim
    if not takvim.gorusme_mi(e):          # 23 Ekim: bütün günlük 'OOO', yalnız kişinin kendisinin olduğu bloklar
        return False
    return bool(_baskalari(e, ay)) or bool(re.search(r"meet\.google\.com|zoom\.us|teams\.microsoft", (e.get("konum") or "") + (e.get("aciklama") or "")))


def adaylar(dk_min=5, dk_max=15):
    simdi = time.time()
    return [e for e in _etkinlikler(simdi + dk_min * 60, simdi + dk_max * 60) if _toplanti_mi(e)]


def siradaki(saat=24):
    simdi = time.time()
    L = [e for e in _etkinlikler(simdi - 10 * 60, simdi + saat * 3600) if _toplanti_mi(e)]
    return L[0] if L else None


def _kimlik(e):
    return hashlib.sha1(f"{e.get('uid')}|{int(e['bas'])}".encode()).hexdigest()[:16]


def _musteri_bul(e, ay):
    """Etkinliğin müşterisi: başlıkta geçen müşteri adı, katılımcı alan adı ya da kişi adları (Müşteriler ve kişiler)."""
    musteriler = ay.get("musteriler") or []
    kisiler = ay.get("musteri_kisiler") or {}
    baslik = (e.get("ad") or "").casefold()
    for m in musteriler:
        if m.casefold() in baslik:
            return m
    alanlar = {k["eposta"].split("@")[-1] for k in _baskalari(e, ay) if "@" in k["eposta"]} - GENEL_ALAN
    for m in musteriler:
        if any(m.casefold().replace(" ", "") in a for a in alanlar):
            return m
    adlar = {k["ad"].casefold().split()[0] for k in _baskalari(e, ay) if k.get("ad")}
    for m, ks in kisiler.items():
        if adlar & {k.casefold().split()[0] for k in ks if k}:
            return m
    return ""


def gecmis(e, gun=120, en_cok=4):
    """Aynı kişiler ya da müşteriyle son toplantılar (puana göre): [(puan, temel, veri)]."""
    ay = _ayar()
    benim_ep, benim_ad = _benim(ay)
    ep = {k["eposta"] for k in _baskalari(e, ay) if k["eposta"]}
    adlar = {k["ad"].casefold().split()[0] for k in _baskalari(e, ay) if k.get("ad")}
    musteri = _musteri_bul(e, ay)
    sinir = time.time() - gun * 86400
    out = []
    for js in KLASOR.glob("transkript_*.json"):
        try:
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        if not v.get("toplanti") or (v.get("olusturma") or 0) < sinir:
            continue
        v_ep = {str(k.get("eposta") or "").lower() for k in ((v.get("takvim") or {}).get("katilimcilar") or []) if isinstance(k, dict)}
        v_ad = {str(a).casefold().split()[0] for a in list(v.get("katilimcilar") or []) + list((v.get("etiket") or {}).values())
                if a and not str(a).startswith("Konuşmacı ") and str(a).casefold().split()[0] != benim_ad}
        puan = 3 * len(ep & v_ep) + len(adlar & v_ad) + (2 if musteri and (v.get("musteri") or "") == musteri else 0)
        if (e.get("ad") or "").strip() and (e.get("ad") or "").casefold() in (v.get("baslik") or "").casefold():
            puan += 2
        if puan > 0:
            out.append((puan, js.stem, v))
    out.sort(key=lambda x: (-x[0], -(x[2].get("olusturma") or 0)))
    return out[:en_cok], musteri


def _duz_metin(gecmisler):
    s = []
    for _p, _t, v in gecmisler:
        n = v.get("notlar") or {}; o = v.get("ozet") or {}
        s.append(f"**{v.get('baslik')}**")
        for y in (n.get("yapilacaklar") or [{"is": x} for x in o.get("yapilacaklar") or []])[:6]:
            s.append(f"- {y.get('is')}" + (f" — {y['kim']}" if y.get("kim") else ""))
        for q in (n.get("acik_sorular") or [])[:4]:
            s.append(f"- Soru: {q}")
    return "\n".join(s)


def _sinyal_metni(v):
    """Önceki toplantının sinyalleri (sinyaller.py): onarılmamış kırılmalar, çelişkiler, kapsam dışı istekler."""
    sy = v.get("sinyaller") or {}
    s = []
    for k in sy.get("kirilmalar") or []:
        if not k.get("onarildi"):
            s.append(f"Kırılma ({k.get('kim')}): {k.get('sinyal')} — önerilen onarma: {k.get('onarim')}")
    for c in sy.get("celiskiler") or []:
        s.append(f"Çelişki: {c.get('konu')}: şimdi '{c.get('simdi')}', önce '{c.get('once')}'")
    kd = [x for x in sy.get("kapsam") or [] if x.get("kapsam_disi")]
    if kd:
        s.append("Kapsam dışı istekler: " + "; ".join(f"{x.get('istek')} (~{x.get('saat')} sa)" for x in kd[:4]))
    return ("\nSinyaller: " + " | ".join(s)) if s else ""


def hazirla(e, log=print):
    """Etkinlik için hazırlık notu üretir ve kaydeder. Döner: kayıt sözlüğü."""
    KLASOR_BRIF.mkdir(parents=True, exist_ok=True)
    kimlik = _kimlik(e)
    gecmisler, musteri = gecmis(e)
    kisiler = _baskalari(e)
    kayit = {"id": kimlik, "ad": e.get("ad") or "Toplantı", "bas": e["bas"], "bit": e["bit"], "kisiler": [k["ad"] for k in kisiler],
             "musteri": musteri, "gecmis": [{"temel": t, "baslik": v.get("baslik"), "tarih": v.get("olusturma")} for _p, t, v in gecmisler],
             "zaman": time.time(), "metin": "", "yazan": ""}
    try:                                               # Couple'ın müşteri dosyası (devam eden işler, açık konular, takvim) notu besler (2026-10-24)
        import meet_gelisim
        couple = meet_gelisim.couple_dosyasi(musteri)
    except Exception:  # noqa: BLE001
        couple = ""
    if couple:
        kayit["couple"] = True
    if not gecmisler and not couple:
        kayit["metin"] = "Bu kişilerle kayıtlı bir önceki toplantı yok." + (f" Müşteri: {musteri}." if musteri else "")
    else:
        import claude_yaz
        with claude_yaz.toplanti():
            if claude_yaz.hazir():
                bloklar = []
                for _p, t, v in gecmisler:
                    n = v.get("notlar") or {}; o = v.get("ozet") or {}
                    bloklar.append(f"### {v.get('baslik')} ({time.strftime('%d.%m.%Y', time.localtime(v.get('olusturma') or 0))})\n"
                                   f"Bağlam: {n.get('baglam') or o.get('ozet', '')}\nKararlar: {'; '.join(n.get('kararlar') or o.get('kararlar') or [])}\n"
                                   f"Yapılacaklar: {'; '.join((y.get('is', '') + (' — ' + y['kim'] if y.get('kim') else '') + (' (' + y['ne_zaman'] + ')' if y.get('ne_zaman') else '')) for y in (n.get('yapilacaklar') or [{'is': x} for x in o.get('yapilacaklar') or []]) if isinstance(y, dict))}\n"
                                   f"Açık sorular: {'; '.join(n.get('acik_sorular') or [])}\nSonraki adımlar: {'; '.join(n.get('sonraki_adimlar') or [])}"
                                   + _sinyal_metni(v))
                istem = (f"{_ayar().get('benim_adim') or 'Kullanıcı'} birazdan '{kayit['ad']}' toplantısına girecek "
                         f"(katılımcılar: {', '.join(kayit['kisiler']) or 'bilinmiyor'}{'; müşteri: ' + musteri if musteri else ''}). "
                         + (f"Takvim açıklaması: {(e.get('aciklama') or '')[:800]}\n" if e.get("aciklama") else "")
                         + "Aşağıdaki önceki toplantı notlarından ona 30 saniyede okunacak bir hazırlık notu yaz. Markdown, en çok 12 satır:\n"
                         "**Son görüşme:** tarih ve tek cümle nerede kalındı\n**Açık işler:**\n- (önce kullanıcının kendi işleri; kim, ne zaman)\n"
                         "**Bekleyen sorular:**\n- ...\n**Dikkat:**\n- (varsa) onarılmamış kırılma ve önerilen onarma cümlesi; önceki toplantıyla çelişen bir söz; "
                         "konuşulmamış kapsam dışı iş\n**Bu toplantıda konuşulabilecekler:**\n- 2-3 öneri\n"
                         "Boş başlığı yazma; yalnızca notlardaki bilgi; uydurma yok; doğal Türkçe.\n\n" + ("\n\n".join(bloklar) or "(Bu kişilerle kayıtlı toplantı yok.)")
                         + (f"\n\n### Müşteri dosyası ({musteri}; e-posta, Drive, Asana ve önceki işlerden derlendi)\n{couple}" if couple else ""))
                try:
                    kayit["metin"] = claude_yaz.sor(istem, "Sen kullanıcının toplantı asistanısın; kısa ve net yazarsın.", zaman_asimi=180).strip()
                    kayit["yazan"] = claude_yaz.etiket()
                except Exception as ex:  # noqa: BLE001
                    log(f"Ön hazırlık Claude ile yazılamadı ({ex})")
        if not kayit["metin"]:
            kayit["metin"] = _duz_metin(gecmisler) or (f"Müşteri dosyası ({musteri}):\n{couple[:900]}" if couple else "")
    (KLASOR_BRIF / f"{kimlik}.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    return kayit


def canli_hazirla(baslik, katilimcilar, platform="", log=print):
    """Takvimde olmayan (ya da takvimi bağlı olmayan) süren toplantı için hazırlık notu (2026-10-23). Uzantı toplantı adını ve katılımcıların
    ADLARINI biliyor; bu kişilerle (ilk ad eşleşmesi) ve aynı müşteriyle yapılmış önceki toplantılardan aynı not yazılır. Yan panel ve canlı
    asistan bunu kullanır. Takvimde bu saate denk gelen ve notu hazır bir görüşme varsa onu döndürür."""
    import takvim
    try:
        e = takvim.suren()
        if e:
            for k in son_kayitlar(saat_once=2, saat_sonra=1):
                if k.get("ad") == e.get("ad") and abs(k.get("bas", 0) - e["bas"]) < 1800:
                    return k
    except Exception:  # noqa: BLE001
        pass
    simdi = time.time()
    uid = "canli:" + hashlib.sha1(f"{platform}|{baslik}|{time.strftime('%Y-%m-%d %H')}".encode()).hexdigest()[:10]
    e = {"ad": baslik or "Süren toplantı", "bas": simdi, "bit": simdi + 3600, "uid": uid, "aciklama": "", "konum": "",
         "katilimcilar": [{"ad": str(a), "eposta": ""} for a in katilimcilar or [] if str(a).strip()]}
    k = hazirla(e, log=log)
    k["canli"] = True
    (KLASOR_BRIF / f"{k['id']}.json").write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
    return k


def hazir_mi(e):
    return (KLASOR_BRIF / f"{_kimlik(e)}.json").exists()


def son_kayitlar(saat_once=1, saat_sonra=24):
    """Başlamasına en çok `saat_sonra` saat olan ya da `saat_once` saat içinde başlamış etkinliklerin hazırlık notları."""
    simdi = time.time()
    out = []
    for f in KLASOR_BRIF.glob("*.json") if KLASOR_BRIF.exists() else []:
        try:
            k = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if simdi - saat_once * 3600 <= k.get("bas", 0) <= simdi + saat_sonra * 3600:
            out.append(k)
    return sorted(out, key=lambda k: k["bas"])


if __name__ == "__main__":
    e = siradaki(saat=72)
    if not e:
        print("Önümüzdeki 72 saatte başkalarının da olduğu bir toplantı yok."); raise SystemExit(0)
    k = hazirla(e)
    print(time.strftime("%d.%m %H:%M", time.localtime(k["bas"])), k["ad"], "·", ", ".join(k["kisiler"]))
    print(k["metin"])

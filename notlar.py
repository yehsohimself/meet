"""notlar.py - Toplantı sonrası bağlamı yüksek toplantı notları üretir ve e-postayla gönderir.

Notlar: bağlam (bu toplantı neydi, aynı kişilerle/müşteriyle önceki görüşmelerden devam eden konular), konular
(her biri 2-4 cümle), kararlar, yapılacaklar (kim, ne zaman), açık sorular, sonraki adımlar. Model: Ollama gemma3:4b,
uzun toplantılar parçalanıp birleştirilir. veri["notlar"] = {...}; dosya <temel>.notlar.txt.
Gönderim: Mac'teki Mail uygulamasıyla (şifre gerekmez); alıcı = kullanıcının toplantıya girdiği adres
(takvim katılımcıları içindeki kendi adresi; yoksa ayarlardaki ilk adres). Gönderen hesap da aynı adres.

Elle: python notlar.py transkript_x.json [--gonder]
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))

PARCA_KELIME = 2500


def _ayar():
    import ortak                                           # tek sürüm (sırlar dahil; 2026-10-25)
    return ortak.ayar()


def _parcala(paragraflar):
    gruplar, cur, k = [], [], 0
    for p in paragraflar:
        n = len(p["metin"].split())
        if cur and k + n > PARCA_KELIME:
            gruplar.append(cur); cur, k = [], 0
        cur.append(p); k += n
    if cur:
        gruplar.append(cur)
    return gruplar


def _onceki_baglam(veri, temel):
    """Aynı müşteri ya da aynı kişilerle yapılmış son 2 toplantının özeti/kararları (bağlam için)."""
    import glob
    adlar = {str(a).lower() for a in (veri.get("katilimcilar") or [])} | {str(a).lower() for a in (veri.get("etiket") or {}).values() if not str(a).startswith("Konuşmacı ")}
    musteri = (veri.get("musteri") or "").strip()
    adaylar = []
    for f in glob.glob(str(KLASOR / "transkript_*.json")):
        if Path(f).stem == temel:
            continue
        try:
            v = json.loads(Path(f).read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        if not v.get("toplanti") or not v.get("ozet"):
            continue
        onlar = {str(a).lower() for a in (v.get("katilimcilar") or [])} | {str(a).lower() for a in (v.get("etiket") or {}).values() if not str(a).startswith("Konuşmacı ")}
        puan = (3 if musteri and musteri != "Diğer" and v.get("musteri") == musteri else 0) + len(adlar & onlar)
        if puan:
            adaylar.append((puan, v.get("olusturma") or 0, v))
    adaylar.sort(key=lambda x: (-x[0], -x[1]))
    parcalar = []
    for _p, _z, v in adaylar[:2]:
        o = v["ozet"]
        parcalar.append(f"- {v.get('baslik')}: {o.get('ozet', '')[:600]}" + (" Kararlar: " + "; ".join(o.get("kararlar") or []) if o.get("kararlar") else "")
                        + (" Yapılacaklar: " + "; ".join(o.get("yapilacaklar") or []) if o.get("yapilacaklar") else ""))
    return "\n".join(parcalar)


def uret(veri, segmentler, temel="", log=print):
    import claude_yaz
    with claude_yaz.toplanti():
        return _uret(veri, segmentler, temel, log)


def _notlarim_ek(veri):
    try:
        import notlarim
        return notlarim.istem_ek(veri)
    except Exception:  # noqa: BLE001
        return ""


def _uret(veri, segmentler, temel="", log=print):
    import ozet as ozet_modulu
    from transkript import paragrafla
    if not ozet_modulu.hazir():
        return None
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(segmentler, etiket)
    if not par:
        return None
    # Claude bütün toplantıyı tek seferde okuyabilir (bağlam kopmaz); yerel model için parçalar
    gruplar = [par] if ozet_modulu.claude_hazir() and sum(len(p["metin"].split()) for p in par) < 50000 else _parcala(par)
    kisi = ", ".join(sorted({p["ad"] for p in par}))
    parca_notlari = []
    for gi, g in enumerate(gruplar, 1):
        if len(gruplar) > 1:
            log(f"      Notlar: parça {gi}/{len(gruplar)}")
        metin = "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in g)
        istem = (
            "Aşağıda bir iş toplantısının yazıya dökülmüş bir bölümü var (konuşmacı adlarıyla). Bu bölüm için ayrıntılı toplantı notu çıkar. "
            "Türkçe, somut, bağlam veren cümleler kur; genel laflar etme; isimleri ve sayıları koru.\n"
            "- konular: bu bölümde konuşulan her konu için {\"baslik\", \"ozet\": 2-4 cümle (ne tartışıldı, kim ne dedi, hangi gerekçeyle)}\n"
            "- kararlar: açıkça alınan kararlar\n- yapilacaklar: {\"is\", \"kim\": söyleyen/üstlenen kişi ya da \"\", \"ne_zaman\": YALNIZCA açıkça bir tarih/gün söylendiyse, yoksa \"\"}\n"
            "- acik_sorular: yanıtsız kalan sorular / belirsizlikler\n"
            "Yalnızca JSON: {\"konular\": [...], \"kararlar\": [...], \"yapilacaklar\": [...], \"acik_sorular\": [...]}\n\n" + metin
        )
        try:
            c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=16384, zaman_asimi=600)) or {}
        except Exception as e:  # noqa: BLE001
            log(f"      Not üretilemedi ({e})"); c = {}
        parca_notlari.append(c)
    onceki = _onceki_baglam(veri, temel)
    if len(parca_notlari) == 1 and not onceki:
        birlesik = parca_notlari[0]
        baglam_istem_gerek = True
    else:
        birlesik = None; baglam_istem_gerek = True
    # Birleştirme + bağlam (tek sorgu)
    ham = json.dumps(parca_notlari, ensure_ascii=False)[:(60000 if ozet_modulu.claude_hazir() else 14000)]
    istem = (
        f"Toplantı: {veri.get('baslik')}\nKatılımcılar/konuşmacılar: {kisi}\n"
        + (f"Aynı kişiler/müşteriyle ÖNCEKİ toplantılar (bağlam için):\n{onceki}\n" if onceki else "")
        + _notlarim_ek(veri)
        + "\nAşağıda bu toplantının bölüm bölüm çıkarılmış ham notları var. Bunları TEK bir toplantı notuna dönüştür:\n"
        "- baglam: 2-4 cümle; bu toplantı ne hakkındaydı, önceki görüşmelerden devam eden ne vardı (varsa), nerede kalındı.\n"
        "- konular: birleştirilmiş, tekrarsız; her biri {\"baslik\", \"ozet\": 2-5 cümle, bağlam ve gerekçe içeren}\n"
        "- kararlar: tekrarsız liste\n- yapilacaklar: {\"is\", \"kim\", \"ne_zaman\"} tekrarsız\n- acik_sorular\n"
        "- sonraki_adimlar: 2-4 madde, bir sonraki toplantıya kadar ne olmalı\n"
        "Uydurma; ham notlarda olmayan bilgi ekleme. Yalnızca JSON: {\"baglam\": \"...\", \"konular\": [...], \"kararlar\": [...], "
        "\"yapilacaklar\": [...], \"acik_sorular\": [...], \"sonraki_adimlar\": [...]}\n\nHam notlar:\n" + ham
    )
    try:
        son = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=16384, zaman_asimi=600)) or {}
    except Exception as e:  # noqa: BLE001
        log(f"      Notlar birleştirilemedi ({e})"); son = birlesik or {}
    if not son.get("konular") and not son.get("baglam"):
        return None
    def liste(x):
        return [str(i) for i in (x or []) if str(i).strip()]
    yap = []
    for y in son.get("yapilacaklar") or []:
        if isinstance(y, dict):
            yap.append({"is": str(y.get("is") or "").strip(), "kim": str(y.get("kim") or "").strip(), "ne_zaman": str(y.get("ne_zaman") or "").strip()})
        elif str(y).strip():
            yap.append({"is": str(y).strip(), "kim": "", "ne_zaman": ""})
    return {
        "baglam": str(son.get("baglam") or "").strip(),
        "konular": [{"baslik": str(k.get("baslik") or "").strip(), "ozet": str(k.get("ozet") or "").strip()} for k in (son.get("konular") or []) if isinstance(k, dict)],
        "kararlar": liste(son.get("kararlar")), "yapilacaklar": [y for y in yap if y["is"]],
        "acik_sorular": liste(son.get("acik_sorular")), "sonraki_adimlar": liste(son.get("sonraki_adimlar")),
        "zaman": time.time(), "model": ozet_modulu.SON_MODEL,
    }


def metin(veri, n):
    """Notları e-posta/txt metnine çevirir."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})", veri.get("baslik") or "")
    tarih = f"{m.group(3)}.{m.group(2)}.{m.group(1)} {m.group(4)}:{m.group(5)}" if m else time.strftime("%d.%m.%Y %H:%M", time.localtime(veri.get("olusturma") or time.time()))
    kat = ", ".join(veri.get("katilimcilar") or sorted({str(a) for a in (veri.get("etiket") or {}).values()}))
    s = [veri.get("baslik") or "Toplantı notları", f"{tarih}" + (f" · {kat}" if kat else ""), ""]
    if n.get("baglam"):
        s += ["BAĞLAM", n["baglam"], ""]
    if n.get("konular"):
        s.append("KONUŞULANLAR")
        for k in n["konular"]:
            s += [f"• {k['baslik']}", f"  {k['ozet']}", ""]
    if n.get("kararlar"):
        s += ["KARARLAR"] + [f"• {k}" for k in n["kararlar"]] + [""]
    if n.get("yapilacaklar"):
        s += ["YAPILACAKLAR"] + [f"☐ {y['is']}" + (f" — {y['kim']}" if y.get("kim") else "") + (f" ({y['ne_zaman']})" if y.get("ne_zaman") else "") for y in n["yapilacaklar"]] + [""]
    if n.get("acik_sorular"):
        s += ["AÇIK SORULAR"] + [f"? {q}" for q in n["acik_sorular"]] + [""]
    if n.get("sonraki_adimlar"):
        s += ["SONRAKİ ADIMLAR"] + [f"→ {a}" for a in n["sonraki_adimlar"]] + [""]
    s.append("Bu not, Video Hub tarafından toplantı kaydından çıkarıldı.")
    return "\n".join(s)


def alici_sec(veri, ay=None):
    """Kullanıcının toplantıya girdiği adres: takvim katılımcıları içindeki kendi adresi; yoksa ayarlardaki ilk adres."""
    ay = ay or _ayar()
    adresler = [a.strip().lower() for a in (ay.get("benim_epostalar") or []) if a.strip()]
    if not adresler:
        return ""
    katilan = {str(k.get("eposta") or k).lower() for k in (veri.get("takvim", {}).get("katilimcilar") or []) if k}
    for a in adresler:
        if a in katilan:
            return a
    return adresler[0]


def gonder(konu, govde, alici, gonderen=""):
    """Mail uygulamasıyla gönderir (AppleScript). Hata varsa metin döner, başarıda ''."""
    def q(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = ['tell application "Mail"',
              f'set m to make new outgoing message with properties {{subject:"{q(konu)}", content:"{q(govde)}", visible:false}}',
              f'tell m to make new to recipient at end of to recipients with properties {{address:"{q(alici)}"}}']
    if gonderen:
        script.append(f'try\nset sender of m to "{q(gonderen)}"\nend try')
    script += ["send m", "end tell"]
    try:
        r = subprocess.run(["osascript", "-e", "\n".join(script)], capture_output=True, text=True, timeout=60)
        return "" if r.returncode == 0 else (r.stderr.strip() or "Mail gönderemedi")
    except Exception as e:  # noqa: BLE001
        return str(e)


def taslak_ac(konu, govde, alicilar, gonderen=""):
    """Mail uygulamasında GÖNDERİLMEMİŞ bir taslak açar (kullanıcı okuyup kendisi gönderir). Hata varsa metin döner."""
    def q(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = ['tell application "Mail"',
              f'set m to make new outgoing message with properties {{subject:"{q(konu)}", content:"{q(govde)}", visible:true}}']
    for a in alicilar:
        script.append(f'tell m to make new to recipient at end of to recipients with properties {{address:"{q(a)}"}}')
    if gonderen:
        script.append(f'try\nset sender of m to "{q(gonderen)}"\nend try')
    script += ["activate", "end tell"]
    try:
        r = subprocess.run(["osascript", "-e", "\n".join(script)], capture_output=True, text=True, timeout=60)
        return "" if r.returncode == 0 else (r.stderr.strip() or "Mail taslağı açılamadı")
    except Exception as e:  # noqa: BLE001
        return str(e)


def main():
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    yol = Path(sys.argv[1]); d = json.loads(yol.read_text(encoding="utf-8")); veri, seg = d["veri"], d["segmentler"]
    n = uret(veri, seg, yol.stem)
    if not n:
        print("Not üretilemedi."); raise SystemExit(1)
    veri["notlar"] = n
    yol.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    m = metin(veri, n); Path(str(yol.with_suffix("")) + ".notlar.txt").write_text(m, encoding="utf-8")
    print(m)
    if "--gonder" in sys.argv:
        a = alici_sec(veri)
        h = gonder(f"Toplantı notları · {veri.get('baslik')}", m, a, a)
        print("Gönderildi:" if not h else "Gönderilemedi:", a, h)


if __name__ == "__main__":
    main()

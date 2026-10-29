"""gorevler.py - Toplantı sonrasında kullanıcının işlerini kendiliğinden görev olarak atar (2026-10-22; kullanıcının Transcript tanıtımındaki
"toplantı sonrasında otomatik task atıyor" özelliği). Kaynak: Kısaca'daki "Kim ne yapacak" listesinde kullanıcının (Ayarlar → Adınız) bitmemiş işleri.

Hedef YALNIZ Asana (kullanıcı, 22 Ekim: "Anımsatıcılar'a değil, ajansla girilen Asana'ya"): ayarlardaki çalışma alanında kullanıcıya
atanmış görev; toplantının müşterisinin Asana'da projesi varsa o projede; söylendiyse son tarih (sozler.son_tarih). Asana bağlı değilse işler
`gorev_atama["_bekliyor"]` ile bekler, bağlantı kurulunca site kendiliğinden ekler (Anımsatıcılar yedeği kaldırıldı).
Her iş bir kez atanır: `veri["gorev_atama"][is] = {yer, zaman, id, url}`. Başkalarının işleri atanmaz (takip e-postası onlar için).
"""
import json
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
LISTE = "Transcript"


def _ayar():
    import ortak                                           # tek sürüm (sırlar dahil; 2026-10-25)
    return ortak.ayar()


def benim_isler(veri):
    ben = ((_ayar().get("benim_adim") or "").strip().split() or [""])[0].casefold()
    if not ben:
        return []
    out = []
    for k in (veri.get("kisaca") or {}).get("kisiler") or []:
        if str(k.get("ad") or "").strip().split()[:1] and str(k["ad"]).strip().split()[0].casefold() == ben:
            out += [i for i in k.get("isler") or [] if i.get("is") and not i.get("bitti")]
    return out


def _gun(veri):
    import re
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", veri.get("baslik") or "")
    return date(int(m[1]), int(m[2]), int(m[3])) if m else date.today()


def _as(s):
    return str(s or "").replace("\\", "\\\\").replace('"', '\\"')


def _animsatici(ad, not_, son):
    """Anımsatıcılar'a bir görev ekler (AppleScript). Döner: hata metni ya da ''."""
    tarih = ""
    if son:
        tarih = (f'set t to current date\nset year of t to {son.year}\nset month of t to {son.month}\nset day of t to {son.day}\n'
                 'set time of t to 10 * hours\n')
    betik = (f'tell application "Reminders"\nif not (exists list "{LISTE}") then make new list with properties {{name:"{LISTE}"}}\n'
             + tarih +
             f'tell list "{LISTE}" to make new reminder with properties {{name:"{_as(ad)}", body:"{_as(not_)}"' + (", due date:t" if son else "") + "}\nend tell")
    try:
        r = subprocess.run(["osascript", "-e", betik], capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001
        return str(e)[:200]
    return "" if r.returncode == 0 else (r.stderr.strip() or "Anımsatıcılar'a eklenemedi")[:200]


def ata(veri, temel, asana_ekle=None, log=print):
    """Kullanıcının atanmamış işlerini atar; veri["gorev_atama"]'yı günceller (çağıran dosyaya yazar). Döner: eklenen iş sayısı."""
    if _ayar().get("oto_gorev", True) is False:
        return 0
    atama = veri.setdefault("gorev_atama", {})
    isler = [i for i in benim_isler(veri) if i["is"] not in atama]
    if not isler:
        return 0
    try:
        import sozler
        gun = _gun(veri)
        son = {i["is"]: sozler.son_tarih(i.get("ne_zaman") or "", gun) for i in isler}
    except Exception:  # noqa: BLE001
        son = {}
    konu = str(veri.get("baslik") or "").split(" · ")[1] if " · " in str(veri.get("baslik") or "") else str(veri.get("baslik") or "")
    eklenen = 0
    if not asana_ekle:                                     # Asana bağlı değil: işler bekler, bağlanınca eklenir
        atama["_bekliyor"] = {"zaman": time.time(), "adet": len(isler)}
        log(f"      {len(isler)} iş Asana bağlantısını bekliyor")
        return 0
    try:
        sonuc = asana_ekle([{"is": i["is"], "ne_zaman": i.get("ne_zaman") or "", "son": son[i["is"]].isoformat() if son.get(i["is"]) else "",
                             "musteri": i.get("musteri") or ""} for i in isler],   # çok müşterili toplantıda işin kendi müşterisi (kisaca.musteri_ata)
                           konu, temel) or {}
        for i in isler:
            if sonuc.get(i["is"]):
                atama[i["is"]] = {"yer": "Asana", "zaman": time.time(), **sonuc[i["is"]]}; eklenen += 1
    except Exception as e:  # noqa: BLE001
        atama["_hata"] = {"metin": str(e)[:200], "zaman": time.time()}
        log(f"      Asana'ya eklenemedi ({e})")
        return 0
    if eklenen:
        atama.pop("_hata", None); atama.pop("_bekliyor", None)
        log(f"      {eklenen} iş Asana'ya eklendi")
    return eklenen


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
    print(ata(d["veri"], p.stem)); p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(datetime.now())

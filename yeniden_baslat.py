"""yeniden_baslat.py - Siteyi GÜVENLİ yeniden başlatır: iş, kayıt, çeviri, paket vb. sürüyorsa bitmesini bekler.
`launchctl kickstart -k` yerine her zaman bunu kullan (iki gerçek toplantı işi doğrudan yeniden başlatmayla yarıda kalmıştı).
Kullanım: .venv/bin/python yeniden_baslat.py [--bekle 30] [--simdi]
  --bekle N : en çok N dakika bekle (varsayılan 30); süre dolarsa yeniden BAŞLATMAZ, nedenleri yazar.
  --simdi   : beklemeden başlat (yarım işler açılışta kendiliğinden yeniden sıraya girer).
  --testsiz : duman testini atla (yalnızca acil durumda). Varsayılan: önce hizli+birim; geçmezse yeniden başlatılmaz; sonra canli.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

SITE = "http://127.0.0.1:8765"
KAPILAR = range(8765, 8772)


def yabanci_kapilar():
    """Sitenin kapılarını (8765-8771) siteden BAŞKA bir program tutuyor mu? 26 Ekim: başka bir çalışmanın açtığı `python -m http.server 8765`
    yüzünden yeniden başlatılan site kapıyı alamadı ve bütün ürünler kapalı kaldı. Döner: ["8765: Python -m http.server 8765 (klasör)"]."""
    out = []
    try:
        r = subprocess.run(["/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpn"], capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return out
    pid, gor = None, set()
    for satir in r.stdout.splitlines():
        if satir.startswith("p"):
            pid = satir[1:]
        elif satir.startswith("n") and pid:
            try:
                kapi = int(satir.rsplit(":", 1)[-1])
            except ValueError:
                continue
            if kapi not in KAPILAR or (pid, kapi) in gor:
                continue
            gor.add((pid, kapi))
            komut = subprocess.run(["/bin/ps", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout.strip()
            if "site.py" in komut:
                continue
            cwd = subprocess.run(["/usr/sbin/lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
            klasor = next((x[1:] for x in cwd.splitlines() if x.startswith("n")), "")
            out.append(f"{kapi}: {komut[-80:]} (süreç {pid}{', klasör ' + klasor if klasor else ''})")
    return out


def nedenler():
    """Site kapalıysa [] (beklenecek bir şey yok). Açık ama yanıt vermiyorsa 3 deneme (30 sn); yine olmazsa "yanıt vermiyor" diye
    başlatılır (2026-10-25: eskiden her hata [] sayılıp işin ortasında yeniden başlatılabiliyordu)."""
    for deneme in range(3):
        try:
            with urllib.request.urlopen(SITE + "/api/mesgul", timeout=10) as r:
                return json.load(r).get("nedenler") or []
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
                return []
        except Exception:  # noqa: BLE001
            pass
        time.sleep(10)
    # 2026-10-27: site yoğunken ~50 sn takıldı, araç "yanıt vermiyor" deyip 15.29 toplantısının işini yarıda kesti. Artık kayıtlı işlere bakılır:
    # süren ya da sırada iş varsa beklenir; yoksa (gerçekten donmuş, kaybedilecek iş yok) yeniden başlatılır.
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".isler.json"), encoding="utf-8") as f:
            I = json.load(f)
        I = I.values() if isinstance(I, dict) else I
        suren = sum(1 for i in I if isinstance(i, dict) and i.get("durum") in ("sirada", "calisiyor"))
    except Exception:  # noqa: BLE001
        suren = 0
    if suren:
        return [f"Site yanıt vermiyor; kayıtlarda {suren} süren iş var"]
    print("Site yanıt vermiyor ve süren iş yok; yeniden başlatılıyor.", flush=True)
    return []


def main():
    bekle = 30
    if "--bekle" in sys.argv:
        bekle = float(sys.argv[sys.argv.index("--bekle") + 1])
    if "--testsiz" not in sys.argv:                 # bozuk kod devreye girmesin: önce duman testi (derleme, içe aktarma, betik, birim)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import duman_testi
        t = duman_testi.calistir(("hizli", "birim", "testler"))   # 2026-10-25: pytest (sanal kök) de yeniden başlatma kapısında
        if not t["basarili"]:
            print("Duman testi GEÇMEDİ; site yeniden BAŞLATILMADI:", flush=True)
            for k, h in t["hatalar"].items():
                for x in h:
                    print(f"  [{k}] {x}", flush=True)
            raise SystemExit(3)
        print("Duman testi geçti.", flush=True)
    if "--simdi" not in sys.argv:
        bitis = time.time() + bekle * 60; son = None
        while True:
            n = nedenler()
            if not n:
                break
            if n != son:
                print("Bekleniyor: " + "; ".join(n), flush=True); son = n
            if time.time() > bitis:
                print("Süre doldu; site yeniden BAŞLATILMADI.", flush=True); raise SystemExit(2)
            time.sleep(10)
    yab = yabanci_kapilar()
    if yab:
        print("Sitenin kapılarını başka bir program tutuyor; yeniden başlatılsaydı site açılamazdı. Site yeniden BAŞLATILMADI:", flush=True)
        for x in yab:
            print("  " + x, flush=True)
        raise SystemExit(4)
    subprocess.run(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.yehso.transkript"], check=False)
    for _ in range(30):
        time.sleep(1)
        try:
            with urllib.request.urlopen(SITE + "/ping", timeout=2):
                print("Site yeniden başladı.", flush=True)
                if "--testsiz" not in sys.argv:
                    time.sleep(3)
                    h = duman_testi.calistir(("canli",))["hatalar"].get("canli") or []
                    print("Canlı kontrol geçti." if not h else "Canlı kontrolde sorun: " + "; ".join(h), flush=True)
                return
        except Exception:  # noqa: BLE001
            continue
    yab = yabanci_kapilar()
    print("Site 30 sn içinde yanıt vermedi; " + ("kapıyı başka program tutuyor: " + "; ".join(yab) if yab else "site.log'a bakın."), flush=True)
    raise SystemExit(1)


if __name__ == "__main__":
    main()

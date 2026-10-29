"""gizli.py - Şifre/anahtar niteliğindeki ayarları macOS Anahtar Zinciri'nde tutar (ayarlar.json'da değil).

Neden (2026-10-19 teknik değerlendirme): Asana belirteci, YouTube/Pexels API anahtarları ve gizli takvim adresi düz metin
ayarlar.json'daydı (yedeğe ve olası paylaşımlara giriyordu). Anahtar Zinciri girişleri: hizmet "Video Hub", hesap = ayar adı.
Göç: `goc(d)` ayarlar.json'da bulunan sırları Anahtar Zinciri'ne taşır ve dosyadan siler. Okuyanlar `birlestir(d)` ile tam ayarı alır;
yazanlar `ayir(d)` ile sırları Anahtar Zinciri'ne yazıp dosyaya sırsız sözlüğü kaydeder. Anahtar Zinciri erişilemezse (ör. kilitli)
eski davranışa düşer (dosyada kalır) ki hiçbir özellik bozulmasın.
"""
import subprocess

HIZMET = "Video Hub"
SIRLAR = ("asana_token", "youtube_api_anahtar", "pexels_anahtar", "takvim_ics", "erisim_pin", "sync_anahtar")
_onbellek = {}


def al(ad):
    if ad in _onbellek:
        return _onbellek[ad]
    try:
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", HIZMET, "-a", ad, "-w"], capture_output=True, text=True, timeout=10)
        deger = r.stdout.rstrip("\n") if r.returncode == 0 else ""
        if deger and len(deger) % 2 == 0 and all(c in "0123456789abcdef" for c in deger):
            # `security -w` satır sonu içeren değeri (ör. alt alta iki takvim adresi) onaltılık verir; 2026-10-19'dan beri takvim okunamıyordu
            try:
                cozulen = bytes.fromhex(deger).decode("utf-8")
                if cozulen.isprintable() or "\n" in cozulen:
                    deger = cozulen
            except ValueError:
                pass
    except Exception:  # noqa: BLE001
        deger = ""
    _onbellek[ad] = deger
    return deger


def koy(ad, deger):
    """True: Anahtar Zinciri'ne yazıldı (ya da silindi)."""
    _onbellek.pop(ad, None)
    try:
        if not deger:
            subprocess.run(["/usr/bin/security", "delete-generic-password", "-s", HIZMET, "-a", ad], capture_output=True, timeout=10)
            _onbellek[ad] = ""
            return True
        r = subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-s", HIZMET, "-a", ad, "-w", deger],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            _onbellek[ad] = deger
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def birlestir(d):
    """Ayar sözlüğüne Anahtar Zinciri'ndeki sırları ekler (dosyada hâlâ duran varsa o kullanılır)."""
    d = dict(d)
    for ad in SIRLAR:
        if not d.get(ad):
            deger = al(ad)
            if deger:
                d[ad] = deger
    return d


def ayir(d):
    """Sırları Anahtar Zinciri'ne yazar; dosyaya yazılacak sözlüğü döner (yazılabilen sırlar çıkarılmış). Tam ayar sözlüğü beklenir:
    sözlükte OLMAYAN sır bilerek kaldırılmıştır (ör. Asana bağlantısını kes: d.pop) ve Anahtar Zinciri'nden de silinir."""
    d = dict(d)
    for ad in SIRLAR:
        if koy(ad, d.get(ad) or ""):
            d.pop(ad, None)
    return d


def goc(d):
    """Dosyada duran sırları Anahtar Zinciri'ne taşır (YALNIZCA dosyada olanları; Anahtar Zinciri'ndeki diğer sırlara dokunmaz).
    Döner: (dosyaya yazılacak sözlük, değişti mi)."""
    d = dict(d)
    degisti = False
    for ad in SIRLAR:
        if d.get(ad) and koy(ad, d[ad]):
            d.pop(ad, None); degisti = True
    return d, degisti


if __name__ == "__main__":
    for ad in SIRLAR:
        print(f"{ad}: {'var' if al(ad) else 'yok'}")

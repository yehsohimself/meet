"""ortak.py - Modüllerde kopyalanan küçük yardımcıların tek sürümü (2026-10-25 backend gözden geçirmesi).

Kopyalar: 8 `_zaman` (bir saatin üstünde biçim tutarsızdı: "75:30" / "1:15:30"), 16 `_ayar` (yarısı Anahtar Zinciri'ndeki sırları görmüyordu),
ad temizleme regex'leri ve "temel doğrula" kalıpları. Yeni kod bunları kullanır; eski modüllerin `_ayar`/`_zaman` adları buraya yönlendirildi.
"""
import json
import re
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
_TEMEL = re.compile(r"^[\w\-]+$")
_AD_KOTU = re.compile(r'[\\/:*?"<>|]+')


def zaman(sn, saatli=False):
    """mm:ss; bir saatin üstünde (ya da saatli=True) h:mm:ss."""
    sn = int(sn or 0)
    if saatli or sn >= 3600:
        return f"{sn // 3600}:{sn % 3600 // 60:02d}:{sn % 60:02d}"
    return f"{sn // 60:02d}:{sn % 60:02d}"


def saniye(z):
    """'mm:ss' | 'h:mm:ss' | '75:30' → saniye; okunamazsa None."""
    m = re.match(r"^\s*(?:(\d+):)?(\d{1,3}):(\d{2})\s*$", str(z or ""))
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def ayar(klasor=None):
    """ayarlar.json + Anahtar Zinciri'ndeki sırlar (gizli.birlestir). Dosya yoksa/bozuksa {}."""
    try:
        d = json.loads(((Path(klasor) if klasor else KLASOR) / "ayarlar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        d = {}
    try:
        import gizli
        return gizli.birlestir(d)
    except Exception:  # noqa: BLE001
        return d


def kimlik(klasor=None):
    """Kurulumun sahibi (2026-10-25, depo dışarıya açılabilir olsun diye): kodda hiçbir kişi, şirket, hesap adı geçmez; hepsi buradan okunur.
    ayarlar.json: benim_adim, benim_epostalar · profil/x.json: kullanici (X hesabı), takim (tuttuğu takım), sehir, kimlik (tek paragraf).
    Boş kurulumda da çalışır: ilk_ad 'kullanıcı', takım/hesap boş."""
    k = Path(klasor) if klasor else KLASOR
    a = ayar(k)
    try:
        x = json.loads((k / "profil" / "x.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        x = {}
    ad = str(a.get("benim_adim") or "").strip()
    return {"ad": ad, "ilk_ad": (ad.split() or ["kullanıcı"])[0], "epostalar": [e.strip() for e in (a.get("benim_epostalar") or []) if str(e).strip()],
            "x_kullanici": str(x.get("kullanici") or "").strip().lstrip("@"), "takim": str(x.get("takim") or "").strip(),
            "sehir": str(x.get("sehir") or "").strip(), "kimlik": str(x.get("kimlik") or "").strip()}


def sirket_adlari(klasor=None):
    """ayarlar.json 'sirketler' + 'musteriler' + şirketlerin müşteri ve anahtar sözcükleri: tek liste (istemlerde 'ajans: X / Y' gibi yerlerde)."""
    a = ayar(klasor)
    adlar = []
    for s in a.get("sirketler") or []:
        if isinstance(s, dict):
            adlar += [s.get("ad") or ""] + list(s.get("musteriler") or []) + list(s.get("anahtar") or [])
    adlar += list(a.get("musteriler") or [])
    return [x for x in dict.fromkeys(str(x).strip() for x in adlar) if x]


def temel_gecerli(temel):
    """Kayıt adı yalnız harf/rakam/alt çizgi/tire (yol kaçışı yok)."""
    return bool(temel) and bool(_TEMEL.match(str(temel)))


def guvenli_ad(s, en_cok=100, varsayilan="Video"):
    """Dosya adı için: yol ve işletim sistemi karakterleri boşluk olur, kırpılır."""
    s = _AD_KOTU.sub(" ", str(s or "")).strip()
    s = re.sub(r"\s+", " ", s)[:en_cok].strip(" .")
    return s or varsayilan


def kendi_depolar(klasor=None):
    """Ghost'un 'kendi işiniz' gönderileri için okunan git depoları (2026-10-29, Ghost herkese açılırken). ayarlar.json `kendi_depolar`:
    yol listesi; anahtar hiç yoksa bu kurulumun kendi deposu (eski davranış), boş liste = kapalı. Yalnız var olan klasörler."""
    k = Path(klasor) if klasor else KLASOR
    L = ayar(k).get("kendi_depolar")
    yollar = [k] if L is None else [Path(str(x)).expanduser() for x in L if str(x).strip()]
    return [p for p in yollar if (p / ".git").exists()]


def git_kayitlari(sure, klasor=None, en_cok=80):
    """Kendi depolarından çalışma kayıtları: [(kısa kod, tarih, konu)], yeniden eskiye. sure: git --since değeri ('36 hours ago', 'midnight')."""
    import subprocess
    out = []
    for d in kendi_depolar(klasor):
        try:
            r = subprocess.run(["git", "-C", str(d), "log", f"--since={sure}", "--pretty=%h|%cs|%ct|%s"], capture_output=True, text=True, timeout=10)
        except Exception:  # noqa: BLE001
            continue
        for x in r.stdout.splitlines():
            p = x.strip().split("|", 3)
            if len(p) == 4:
                out.append((int(p[2]) if p[2].isdigit() else 0, p[0], p[1], p[3]))
    return [(h, t, s) for _, h, t, s in sorted(out, reverse=True)][:en_cok]

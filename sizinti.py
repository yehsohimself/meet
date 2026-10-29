"""sizinti.py - Depoya kişisel bilgi sızmasın (2026-10-25; kullanıcı: "her ürün ileride dışarıya açılabilir olmalı").

Ne arar: (1) ayarlar.json ve profil/x.json'daki kişisel adlar (adınız, e-postalar, şirketler, müşteriler, kişiler, X hesabı, marka sözcükleri;
hepsi git DIŞINDAKİ dosyalardan okunur, bu dosyada hiçbir ad yok), (2) genel desenler: e-posta adresi (örnek alanlar hariç), Anthropic/OpenAI/GitHub/
Slack anahtar önekleri, /Users/<ad>/ yolları, 25+ karakterlik Drive kimliği gibi görünen diziler 'drive|klasor|folder|id' yanında.
Nerede: sürüm takibindeki metin dosyaları (`git ls-files`) ya da yalnız commit'e hazırlananlar (`--staged`).
İzin: `.sizinti_izin.txt` (git dışı; satır başına bir düzenli ifade) ve koddaki İZİNLİ desenler (launchd etiketi gibi).

Kullanım: python sizinti.py            bütün depo
          python sizinti.py --staged   yalnız commit'e hazır dosyalar (.git/hooks/pre-commit bunu çağırır)
duman_testi.py `hizli` de çağırır: sızıntı varsa yeniden başlatma kapısı geçmez.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
UZANTILAR = {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".swift", ".plist", ".command", ".sh", ".webmanifest", ".ini", ".toml", ".yml", ".yaml"}
ATLA = ("tests/", "static/ikon/", "static/derlenmis/")           # testler sahte adlarla çalışır; ikon lisansı
IZINLI = [r"com\.\w+\.transkript(\.\w+)?", r"@(example|ornek|alan|domain)\.(com|org|net|io)", r"ornek@", r"noreply@anthropic\.com"]
DESENLER = [
    ("e-posta adresi", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")),
    ("API anahtarı", re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{12,})")),
    ("kullanıcı klasörü yolu", re.compile(r"/Users/[A-Za-z0-9_.-]+/")),
    ("Drive kimliği gibi dizi", re.compile(r"(?i)(drive|folder|_id\b|kimli)[^\n]{0,40}['\"](?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*\d)([A-Za-z0-9_-]{25,})['\"]")),
]


def kelimeler():
    """Kişisel adlar: ayarlar.json + profil/x.json (+ .sizinti_ek.txt). Küçük harfe indirilmiş, ≥4 karakter."""
    import ortak
    a = ortak.ayar()
    K = set()

    def ekle(x):
        for parca in re.split(r"[,;/]| ve ", str(x or "")):
            parca = parca.strip()
            if len(parca) >= 4 and not parca.isdigit():
                K.add(parca.casefold())
    ekle(a.get("benim_adim"))
    for p in str(a.get("benim_adim") or "").split():
        ekle(p)
    for e in a.get("benim_epostalar") or []:
        ekle(e)
        if e.split("@")[-1] not in {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "icloud.com", "yahoo.com", "proton.me"}:
            ekle(e.split("@")[-1])
    for s in a.get("sirketler") or []:
        if isinstance(s, dict):
            for k in ("ad", "kod"):
                ekle(s.get(k))
            for x in list(s.get("musteriler") or []) + list(s.get("alan") or []) + list(s.get("anahtar") or []):
                ekle(x)
            for x in s.get("kisiler") or []:                    # kişi adları: tek sözcüklü kısa adlar (Umut, Can) sözcüklerle çakışır; yalnız tam adlar ve uzun adlar
                if len(str(x).split()) > 1 or len(str(x)) >= 6:
                    ekle(x)
    for x in a.get("musteriler") or []:
        ekle(x)
    for k, v in (a.get("musteri_kisiler") or {}).items() if isinstance(a.get("musteri_kisiler"), dict) else []:
        ekle(k)
        for x in v if isinstance(v, list) else [v]:
            ekle(x)
    for k in (a.get("alt_isler") or {}):
        ekle(k)
    for anahtar in ("asana_ws", "secki_klasor_id", "secki_havuz_id"):
        if a.get(anahtar):
            K.add(str(a[anahtar]))
    for t in a.get("reklam_arsivi_tablolar") or []:
        if isinstance(t, list) and t:
            K.add(str(t[0]))
    try:
        x = json.loads((KLASOR / "profil" / "x.json").read_text(encoding="utf-8"))
        ekle(x.get("kullanici"))                            # takım kişisel veri değil; kod zaten profilden okur
    except Exception:  # noqa: BLE001
        pass
    ek = KLASOR / ".sizinti_ek.txt"
    if ek.exists():
        for satir in ek.read_text(encoding="utf-8").splitlines():
            ekle(satir)
    # çok genel sözcükler (kod ve arayüz metninde doğal olarak geçer) listeden düşer
    return {k for k in K if k not in {"genel", "diğer", "video", "film", "link", "studio", "meet", "ghost", "couple", "content", "test", "kişi", "marka",
                                      "şirket", "finansal", "internet", "dijital", "strateji", "kreatif", "mini", "spor", "kredi", "radyo", "sinema"}}


def _izinli():
    L = [re.compile(p) for p in IZINLI]
    yol = KLASOR / ".sizinti_izin.txt"
    if yol.exists():
        for satir in yol.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                try:
                    L.append(re.compile(satir.strip()))
                except re.error:
                    pass
    return L


def dosyalar(staged=False):
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["git", "ls-files"]
    r = subprocess.run(cmd, cwd=KLASOR, capture_output=True, text=True)
    out = []
    for ad in r.stdout.splitlines():
        p = KLASOR / ad
        if p.suffix.lower() in UZANTILAR and p.is_file() and not any(ad.startswith(x) for x in ATLA):
            out.append(p)
    return out


def denetle(staged=False, en_cok=60):
    """Döner: [{"dosya", "satir", "tur", "parca"}]"""
    K = kelimeler()
    kelime_re = re.compile(r"(?<![\w])(" + "|".join(re.escape(k) for k in sorted(K, key=len, reverse=True)) + r")(?![\w])", re.I) if K else None
    izinli = _izinli()
    bulgular = []
    for p in dosyalar(staged):
        try:
            metin = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for i, satir in enumerate(metin.splitlines(), 1):
            temiz = satir
            for r in izinli:                               # izinli parçalar silinir, kalan denetlenir
                temiz = r.sub("", temiz)
            hit = None
            if kelime_re:
                m = kelime_re.search(temiz)
                if m:
                    hit = ("kişisel ad", m.group(0))
            if not hit:
                for tur, r in DESENLER:
                    m = r.search(temiz)
                    if m:
                        hit = (tur, m.group(0)); break
            if hit:
                bulgular.append({"dosya": str(p.relative_to(KLASOR)), "satir": i, "tur": hit[0], "parca": hit[1][:60]})
                if len(bulgular) >= en_cok:
                    return bulgular
    return bulgular


if __name__ == "__main__":
    staged = "--staged" in sys.argv
    B = denetle(staged)
    if not B:
        print("Sızıntı yok" + (" (commit'e hazır dosyalarda)" if staged else "") + ".")
        raise SystemExit(0)
    for b in B:
        print(f"{b['dosya']}:{b['satir']}: {b['tur']}: {b['parca']}")
    print(f"\n{len(B)} bulgu. Kişisel bilgiyi ayarlar.json / profil / markalar gibi git dışı dosyalara taşıyın; bilerek kalacaksa deseni .sizinti_izin.txt'ye yazın.")
    raise SystemExit(1)

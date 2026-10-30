# sunucu/10_sayfalar.py — Content kaydı ve ürün sayfaları.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- ürünler isteğe bağlı (2026-10-25: her ürün ayrı depo/kurulum olabilir)
# Content (2026-10-23), Couple (2026-10-24) ve PT (2026-10-25) kendi modülleriyle kaydolur; modül yoksa o ürün bu kurulumda kapalıdır.
# Meet ve Ghost sunucu parçalarıyla gelir: parça dosyası yoksa kapalı. Kurulu ürünler sayfaya `data-urunler` ile verilir (menü ona göre).
URUNLER_KURULU = set()
if (KLASOR / "sunucu" / "21_studio.py").exists():        # 2026-10-29: Meet tek başına da kesilebilir (yehsohimself/meet); Studio'suz kurulumda 8765 Meet'tir
    URUNLER_KURULU.add("transcript")
for _mod, _kod in (("content_site", "content"), ("couple_site", "atolye"), ("pt_site", "pt")):   # Content 27 Ekim kapatılıp aynı gün geri açıldı
    try:
        globals()[_mod] = __import__(_mod)
        globals()[_mod].kaydet(app)
        URUNLER_KURULU.add(_kod)
    except ImportError:
        print(f"{_mod} yok: bu kurulumda {_kod} kapalı", flush=True)
for _parca, _kod in (("04_toplanti.py", "note"), ("07_ghost.py", "ghost")):
    if (KLASOR / "sunucu" / _parca).exists():
        URUNLER_KURULU.add(_kod)


# ----------------------------------------------------------------------------- sayfalar
URUN_PORTLARI = {p: k for p, k in {8765: "transcript", 8766: "note", 8767: "ghost", 8768: "atolye", 8769: "content", 8771: "pt"}.items()
                 if k in URUNLER_KURULU}   # aynı motor, ayrı adresler (2026-10-20; Content 2026-10-23; PT 2026-10-25)
if "transcript" not in URUNLER_KURULU and "note" in URUNLER_KURULU:
    URUN_PORTLARI[8765] = "note"            # uzantı ve kaydedici 8765 ile konuşur; Studio yoksa bu adres de Meet sayfasını açar
if 8765 not in URUN_PORTLARI and URUN_PORTLARI:
    URUN_PORTLARI[8765] = next(iter(URUN_PORTLARI.values()))   # 2026-10-29: tek ürünlü kurulum (ör. yalnız Ghost): ana adres de o ürünü açar
ANA_URUN = URUN_PORTLARI.get(PORT, "transcript")


_kabuk_onb = {}          # (sayfa, md5) → kabuk html


def _kabuk(html, sayfa):
    """index.html'in tek <style> ve tek satır içi <script> bloğunu içerik özetli dosyalara çıkarır (static/derlenmis/<sayfa>.<md5>.css|js, ?v= ile
    bir yıl önbellek). Kaynak dosya tek parça kalır (başka oturumlar onu düzenler); ikinci açılışta tarayıcı yalnız 45 KB'lık kabuğu indirir
    (2026-10-25). Beklenmedik yapıda (birden çok blok) dosya olduğu gibi döner."""
    import hashlib
    md5 = hashlib.md5(html.encode("utf-8")).hexdigest()[:12]
    k = (sayfa, md5)
    if k in _kabuk_onb:
        return _kabuk_onb[k]
    styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    if len(styles) != 1 or len(scripts) != 1:
        return html
    kl = Path(app.static_folder) / "derlenmis"
    kl.mkdir(exist_ok=True)
    ad = sayfa.rsplit(".", 1)[0]
    css, js = kl / f"{ad}.{md5}.css", kl / f"{ad}.{md5}.js"
    if not css.exists():
        css.write_text(styles[0], encoding="utf-8")
    if not js.exists():
        js.write_text(scripts[0], encoding="utf-8")
    for eski in sorted(kl.glob(f"{ad}.*.css"), key=lambda p: p.stat().st_mtime)[:-4]:   # son 4 sürüm kalır (açık sekmeler eskisini isteyebilir)
        eski.unlink(missing_ok=True); eski.with_suffix(".js").unlink(missing_ok=True)
    kabuk = re.sub(r"<style[^>]*>.*?</style>", f'<link rel="stylesheet" href="/static/derlenmis/{css.name}?v={md5}">', html, count=1, flags=re.S)
    kabuk = re.sub(r"<script(?![^>]*\bsrc=)[^>]*>.*?</script>", f'<script src="/static/derlenmis/{js.name}?v={md5}"></script>', kabuk, count=1, flags=re.S)
    if len(_kabuk_onb) > 20:
        _kabuk_onb.clear()
    _kabuk_onb[k] = kabuk
    return kabuk


_dil_onb = {}


def _dil_surumu():
    """static/dil/en.json'un değişiklik zamanı → ?v= (tarayıcı sözlüğü yenilesin)."""
    try:
        y = Path(app.static_folder) / "dil" / "en.json"; m = int(y.stat().st_mtime)
        return str(m)
    except OSError:
        return "0"


@app.get("/")
def ana():
    try:
        port = int(request.host.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        port = int(request.environ.get("SERVER_PORT") or PORT)      # adreste port yoksa (tünel, ters vekil): dinlenen port
    urun = URUN_PORTLARI.get(port, ANA_URUN)
    sayfa = {"content": "content.html", "atolye": "couple.html", "pt": "pt.html"}.get(urun, "index.html")      # Content, Couple ve PT kendi sayfaları
    html = (Path(app.static_folder) / sayfa).read_text(encoding="utf-8")
    if sayfa == "index.html" and "note" not in URUNLER_KURULU:        # Meet kurulu değilse (yalnız Studio) Meet'in eki istenmez (2026-10-25)
        html = re.sub(r'<script src="/static/meet_ek\.js[^"]*"></script>\n?', "", html)
    if sayfa == "index.html" and "atolye" not in URUNLER_KURULU:      # teslim kontrolü ve müşteri takibi Couple modülleriyle; yoksa ekler istenmez
        html = re.sub(r'<script src="/static/(teslim|takip)_ek\.js[^"]*"></script>\n?', "", html)
    if sayfa == "index.html":                                         # her ek yalnız kendi ürününde çalışır; ötekiler onu hiç indirmesin (2026-10-29)
        for ek, sahip in (("meet_ek", "note"), ("takip_ek", "note"), ("studio_ek", "transcript"), ("teslim_ek", "transcript")):
            if urun != sahip:
                html = re.sub(rf'<script src="/static/{ek}\.js[^"]*"></script>\n?', "", html)
    if sayfa == "index.html" and urun != "transcript" and (Path(app.static_folder) / f"{urun}.webmanifest").exists():
        # telefonda ana ekrana eklenince ürünün kendi adı ve simgesi (2026-10-25; Meet "Studio" adı ve simgesiyle ekleniyordu)
        ad = json.loads((Path(app.static_folder) / f"{urun}.webmanifest").read_text(encoding="utf-8")).get("short_name") or urun
        html = (html.replace('href="/static/manifest.webmanifest"', f'href="/static/{urun}.webmanifest"')
                .replace('href="/static/ikon-180.png"', f'href="/static/{urun}-ikon-180.png"')
                .replace('name="apple-mobile-web-app-title" content="Studio"', f'name="apple-mobile-web-app-title" content="{ad}"')
                .replace("<title>Studio</title>", f"<title>{ad}</title>", 1))
    html = _kabuk(html, sayfa)
    dil = str(ayarlar_oku().get("dil") or "")                         # arayüz dili (2026-10-25; boşsa tarayıcı dili, static/dil.js)
    html = html.replace("<html", f'<html data-urun="{urun}" data-urunler="{",".join(sorted(URUNLER_KURULU))}"' + (f' data-dil="{dil}"' if dil in ("tr", "en") else "") + f' data-dilv="{_dil_surumu()}"', 1)
    r = make_response(html)
    r.headers["Cache-Control"] = "no-cache"
    return r


@app.get("/favicon.ico")
def favicon():
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='14' fill='#0071e3'/>"
           "<path d='M20 24v16M32 16v32M44 24v16' stroke='#fff' stroke-width='6' stroke-linecap='round'/></svg>")
    return svg, 200, {"Content-Type": "image/svg+xml", "Cache-Control": "max-age=86400"}



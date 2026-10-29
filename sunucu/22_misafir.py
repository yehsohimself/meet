# sunucu/22_misafir.py — Studio davetlileri (2026-10-24; kullanıcı: "kapalı bir grup arkadaşım linkle deneyebilmeli; herkese açık değil, belirleyeceğimiz
# sayıda kişi; her link sahibi kendi deneyimini yaşamalı, benim kişisel bilgilerime erişememeli"). Cloudflare hesapsız tüneli (Mac yeniden başlayınca adres
# değişir; kullanıcı kabul etti) yalnız 127.0.0.1:8770'e gelir. Tünel trafiği bu Mac'ten geliyormuş gibi görünür (127.0.0.1), bu yüzden misafir IP'ye göre
# DEĞİL, bağlandığı porta göre (SERVER_PORT 8770) ayrılır. 8770'te her istek varsayılan olarak reddedilir; yalnız IZINLI Studio uçları, yalnız misafirin
# KENDİ kayıtları için geçer. Misafirin işi: sahibin işleri öne geçer, aynı anda tek misafir işi; Claude yalnız misafirin kendi anahtarıyla (claude_yaz.MISAFIR),
# yoksa bu Mac'teki model; sahibin sözlüğü, tanınan sesleri, müşteri adları, Ghost, tarayıcı oturumu (çerez) misafir işine girmez.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
import contextvars
import secrets

import claude_yaz

MISAFIR_PORT = 8770
URUN_PORTLARI[MISAFIR_PORT] = "transcript" if "transcript" in URUNLER_KURULU else "note"   # site.py bu portu da aynı uygulamayla açar (Studio yoksa Meet)
MISAFIR_KLASOR = KLASOR / "misafir"
DAVET_DOSYA = MISAFIR_KLASOR / "davetler.json"
TUNEL_LOG = KAYIT / "tunel.log"
TUNEL_ETIKET = "com.yehso.transkript.tunel"
MISAFIR_SINIR = {"kisi": 5, "gunluk": 3, "en_uzun_sn": 3600, "yukleme_gb": 2, "bos_disk_gb": 10}
_davet_kilit = threading.Lock()
YENI_VIDEO_ISLEMI = ("transkript", "ozet", "indir")    # günlük hakka sayılanlar (türemiş işler: altyazılı, klip, dublaj... sayılmaz)

# ---------------------------------------------------------------------------- bağlam: alt iş parçacıkları başlatanın bağlamını taşır
_t_start = threading.Thread.start


def _baglamli_start(self, *a, **k):
    ctx = contextvars.copy_context()
    hedef = self.run
    self.run = lambda: ctx.run(hedef)
    return _t_start(self, *a, **k)


threading.Thread.start = _baglamli_start


def _misafir_istek():
    try:
        return str(request.environ.get("SERVER_PORT")) == str(MISAFIR_PORT)
    except RuntimeError:
        return False


def _gid():
    m = claude_yaz.MISAFIR.get()
    return (m or {}).get("id") or ""


# ---------------------------------------------------------------------------- davetler
def _davetler():
    try:
        return json.loads(DAVET_DOSYA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"kisiler": []}


def _davet_yaz(d):
    MISAFIR_KLASOR.mkdir(exist_ok=True)
    tmp = DAVET_DOSYA.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DAVET_DOSYA)
    try:
        os.chmod(MISAFIR_KLASOR, 0o700); os.chmod(DAVET_DOSYA, 0o600)   # davet linkleri düz metin: yalnız bu kullanıcı okusun (2026-10-25)
    except OSError:
        pass


def _link_guvenli(url):
    """İnternetteki davetlinin verdiği link bu Mac'e ya da yerel ağa dönmesin (SSRF, 2026-10-25): yalnız http(s) ve herkese açık adresler."""
    import ipaddress
    import socket
    import urllib.parse
    try:
        u = urllib.parse.urlparse(str(url or ""))
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        if u.hostname.lower() in ("localhost",) or u.hostname.endswith((".local", ".internal", ".localhost")):
            return False
        for aile, _t, _p, _c, sa in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
    except Exception:  # noqa: BLE001
        return False
    return True


_oran = {}           # (kim, sinif) → [pencere_baslangici, sayac]
_oran_kilit = threading.Lock()
ORAN = {"davet": (20, 60), "api": (240, 60), "sayfa": (600, 60)}   # (istek, saniye)


def _oran_asildi(kim, sinif):
    en_cok, sure = ORAN[sinif]
    with _oran_kilit:
        simdi = time.time()
        k = (kim, sinif)
        p = _oran.get(k)
        if not p or simdi - p[0] > sure:
            _oran[k] = [simdi, 1]
            if len(_oran) > 5000:
                for eski in [x for x, v in _oran.items() if simdi - v[0] > sure]:
                    _oran.pop(eski, None)
            return False
        p[1] += 1
        return p[1] > en_cok


def _iz(token):
    return hashlib.sha256(("vh-misafir|" + token).encode()).hexdigest()


def _kisi_token(token):
    if not token or len(token) < 20:
        return None
    iz = _iz(token)
    return next((k for k in _davetler()["kisiler"] if k.get("iz") == iz and k.get("aktif")), None)


def _kisi(gid):
    return next((k for k in _davetler()["kisiler"] if k.get("id") == gid), None)


def _anahtar(gid):
    import gizli
    return gizli.al(f"misafir_{gid}") or ""


def _baglam(kisi):
    return {"id": kisi["id"], "ad": kisi.get("ad") or "", "anahtar": _anahtar(kisi["id"])}


def _bugun_sayisi(kisi):
    return int((kisi.get("gunluk") or {}).get(time.strftime("%Y-%m-%d"), 0))


def _say(gid):
    with _davet_kilit:
        d = _davetler()
        for k in d["kisiler"]:
            if k["id"] == gid:
                g = {kk: vv for kk, vv in (k.get("gunluk") or {}).items() if kk >= time.strftime("%Y-%m-%d", time.localtime(time.time() - 14 * 86400))}
                g[time.strftime("%Y-%m-%d")] = g.get(time.strftime("%Y-%m-%d"), 0) + 1
                k["gunluk"] = g
        _davet_yaz(d)


def _yukleme_kaydet(gid, yol):
    with _davet_kilit:
        d = _davetler()
        for k in d["kisiler"]:
            if k["id"] == gid:
                k["yuklemeler"] = (k.get("yuklemeler") or [])[-49:] + [yol]
        _davet_yaz(d)


def tunel_adresi():
    try:
        m = re.findall(r"https://[a-z0-9\-]+\.trycloudflare\.com", TUNEL_LOG.read_text(encoding="utf-8", errors="ignore")[-200000:])
        return m[-1] if m else ""
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------- sahiplik
_sahip_onb = {}


def _temel_sahibi(temel):
    if not temel or not re.match(r"^[\w\-]+$", str(temel)):
        return ""
    js = KLASOR / f"{temel}.json"
    try:
        mt = js.stat().st_mtime
    except OSError:
        return ""
    o = _sahip_onb.get(temel)
    if o and o[0] == mt:
        return o[1]
    try:
        m = json.loads(js.read_text(encoding="utf-8"))["veri"].get("misafir") or ""
    except Exception:  # noqa: BLE001
        m = ""
    _sahip_onb[temel] = (mt, m)
    return m


def _dosya_sahibi(ad):
    return (_dizin_oku().get(ad) or {}).get("misafir") or ""


def _temel_dosyadan(dosya):
    """'transkript_x.en.srt' → 'transkript_x' (en uzun var olan temel)."""
    parca = str(dosya).split(".")
    for i in range(len(parca) - 1, 0, -1):
        t = ".".join(parca[:i])
        if (KLASOR / f"{t}.json").exists():
            return t
    return ""


# ---------------------------------------------------------------------------- iş sırası: sahibin işleri önce, tek misafir işi
def _misafir_sirasi_uygun(kuyruk):
    for i in list(isler.values()):
        if i.get("durum") == "calisiyor" and not i.get("misafir"):
            return False                                   # sahibin işi sürüyor: misafir bekler
    for iid in list(_misafir_calisan):
        if (isler.get(iid) or {}).get("durum") in ("sirada", "calisiyor"):
            return False
        _misafir_calisan.discard(iid)
    return True


_misafir_calisan = set()


class _OncelikliKuyruk(queue.Queue):
    """queue.Queue'nun iç kancaları: sahip / misafir iki ayrı deque. Var olan kuyrukların sınıfı yerinde değiştirilir (bekleyen işçi uyanmadan)."""

    def _qsize(self):
        return len(self.sahip) + (len(self.misafir) if self.misafir and _misafir_sirasi_uygun(self) else 0)

    def _put(self, item):
        is_ = isler.get(item) if item else None
        gid = (_gid() or (is_ or {}).get("misafir") or _temel_sahibi((is_ or {}).get("temel"))) if is_ else ""
        if not gid:
            self.sahip.append(item); return
        is_["misafir"] = gid
        is_["cerez"] = ""                                   # sahibin tarayıcı oturumu misafir işinde kullanılmaz
        if float(is_.get("sure") or 0) > MISAFIR_SINIR["en_uzun_sn"]:
            is_["durum"] = "hata"; is_["hata"] = f"Davetli kullanımda en çok {MISAFIR_SINIR['en_uzun_sn'] // 60} dakikalık videolar işlenebilir."
            return
        self.misafir.append(item)

    def _get(self):
        if self.sahip:
            item = self.sahip.popleft()
        else:
            item = self.misafir.popleft()
            _misafir_calisan.add(item)
        is_ = isler.get(item) or {}
        kisi = _kisi(is_.get("misafir")) if is_.get("misafir") else None
        claude_yaz.MISAFIR.set(_baglam(kisi) if kisi else None)   # işçi iş parçacığının bağlamı bu işe göre
        return item


def _kuyruk_donustur(q):
    with q.mutex:
        if isinstance(q, _OncelikliKuyruk):
            return
        q.sahip = q.queue
        q.misafir = collections.deque()
        q.__class__ = _OncelikliKuyruk


for _q in (sira, sira_indir):
    _kuyruk_donustur(_q)


def _kuyruk_durtucu():
    """Misafir işi, sahibin işi bitince kendiliğinden başlasın (koşul değişince kuyruk kendisi uyanmıyor)."""
    while True:
        time.sleep(5)
        for q in (sira, sira_indir):
            try:
                with q.not_empty:
                    q.not_empty.notify_all()
            except Exception:  # noqa: BLE001
                pass


threading.Thread(target=_kuyruk_durtucu, daemon=True).start()

_env_onceki = _env


def _env():   # noqa: F811 — misafir işinin alt süreci kendi kimliği ve (varsa) kendi Claude anahtarıyla
    e = _env_onceki()
    m = claude_yaz.MISAFIR.get()
    e.pop("VH_MISAFIR", None); e.pop("VH_MISAFIR_ANAHTAR", None)
    if m:
        e["VH_MISAFIR"] = m["id"]; e["VH_MISAFIR_ANAHTAR"] = m.get("anahtar") or ""
    return e


_indirme_bitir_onceki = _indirme_bitir


def _indirme_bitir(is_):   # noqa: F811 — misafirin indirdiği/ürettiği video yalnız onun
    _indirme_bitir_onceki(is_)
    gid = _gid() or is_.get("misafir") or _temel_sahibi(is_.get("temel"))
    if gid and is_.get("dosya"):
        with kilit:
            d = _dizin_oku(); ad = Path(is_["dosya"]).name
            if ad in d:
                d[ad]["misafir"] = gid; _dizin_yaz(d)


# ---------------------------------------------------------------------------- kapı
OZEL = object()
# kural → None (sahiplik yok) | "temel" | "is" | "dosya_temel" | "indirilen" | "kapak_ad"
IZINLI = {
    ("GET", "/api/onizle"): OZEL, ("POST", "/api/baslat"): OZEL, ("POST", "/api/yukle"): OZEL,
    ("GET", "/api/isler"): None, ("GET", "/api/is/<is_id>"): "is", ("DELETE", "/api/is/<is_id>"): "is", ("POST", "/api/is/<is_id>/ekler"): "is",
    ("GET", "/api/gecmis"): None, ("GET", "/api/ara"): None, ("POST", "/api/sor"): OZEL, ("GET", "/api/sahne-ara"): None,
    ("GET", "/api/indirilenler"): None, ("GET", "/indirilen/<path:dosya>"): "indirilen", ("GET", "/indirilen-kapak/<path:dosya>"): "indirilen_kapak",
    ("DELETE", "/api/indirilen/<path:dosya>"): "indirilen", ("POST", "/api/indirilen-geri/<path:dosya>"): "indirilen",
    ("GET", "/api/metin/<temel>"): "temel", ("DELETE", "/api/sil/<temel>"): "temel", ("POST", "/api/geri-al/<temel>"): "temel",
    ("POST", "/api/isimlendir/<temel>"): "temel", ("POST", "/api/segment/<temel>"): "temel", ("POST", "/api/ozet/<temel>"): "temel", ("POST", "/api/ozet/<temel>/geri"): "temel",
    ("GET", "/api/ozet-durum/<temel>"): "temel", ("POST", "/api/ceviri/<temel>"): "temel", ("GET", "/api/ceviri-durum/<temel>"): "temel",
    ("POST", "/api/klipler/<temel>"): "temel", ("GET", "/api/dolgu/<temel>"): "temel", ("POST", "/api/dublaj/<temel>"): OZEL,
    ("GET", "/api/kaynak-video/<temel>"): "temel", ("GET", "/api/kurgu/<temel>"): "temel", ("POST", "/api/kurgu/<temel>"): OZEL,
    ("POST", "/api/metin-duzelt/<temel>"): "temel", ("GET", "/api/altyazi-onizle/<temel>"): "temel",
    ("POST", "/api/yayin/<temel>"): "temel", ("GET", "/api/yayin-durum/<temel>"): "temel", ("POST", "/api/yayin/<temel>/kapak"): "temel",
    ("POST", "/api/yayin/<temel>/shorts"): "temel", ("POST", "/api/sahne-dizin/<temel>"): "temel", ("GET", "/api/sahne-durum/<temel>"): "temel",
    ("GET", "/api/sohbet/<temel>"): "temel", ("POST", "/api/sohbet/<temel>"): "temel", ("DELETE", "/api/sohbet/<temel>"): "temel",
    ("GET", "/medya/<temel>"): "temel", ("GET", "/kare/<temel>/<dosya>"): "temel", ("GET", "/disa/<temel>.<uz>"): "temel",
    ("GET", "/zip/<temel>.zip"): "temel", ("GET", "/indir/<dosya>"): "dosya_temel", ("GET", "/kapak/<dosya>"): "dosya_temel",
    ("GET", "/yayin-kapak/<ad>"): "kapak_ad", ("GET", "/kapak-taslak/<ad>"): "kapak_ad",
    ("GET", "/altyazi-ornek/<stil>.mp4"): None, ("GET", "/ping"): None, ("GET", "/favicon.ico"): None,
    ("GET", "/api/misafir/ben"): None, ("POST", "/api/misafir/anahtar"): None, ("DELETE", "/api/misafir/anahtar"): None, ("POST", "/api/misafir/cikis"): None,
}


def _sayfa(baslik, metin, kod=200):
    import html as _h
    return (f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio</title><style>body{{font-family:-apple-system,Manrope,sans-serif;background:#08080a;color:#eee;display:grid;place-items:center;min-height:100vh;margin:0;padding:24px;
box-sizing:border-box}}div{{max-width:420px;text-align:center}}h1{{font-size:34px;margin:0 0 12px}}p{{color:#a1a1a6;line-height:1.5;margin:0}}</style></head>
<body><div><h1>{_h.escape(baslik)}</h1><p>{_h.escape(metin)}</p></div></body></html>""", kod, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})


def _misafir_ana(kisi):
    import html as _h
    html = (Path(app.static_folder) / "index.html").read_text(encoding="utf-8")
    html = html.replace("<html", '<html data-urun="transcript" data-misafir="1"', 1)
    ek = (f'<script>window.MISAFIR = {json.dumps({"ad": kisi.get("ad") or ""}, ensure_ascii=False)};</script>'
          '<script src="/static/misafir.js?v=1"></script>')
    html = html.replace("</body>", ek + "</body>", 1)
    r = make_response(html)
    r.headers["Cache-Control"] = "no-store"
    return r


def _red(kod=404, metin="Bulunamadı."):
    return jsonify({"hata": metin}), kod


@app.before_request
def _misafir_kapisi():
    if not _misafir_istek():
        return None
    claude_yaz.MISAFIR.set(None)
    yol = request.path
    kim = request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"     # tünel trafiği 127.0.0.1 görünür; Cloudflare gerçek IP'yi başlıkta verir
    if _oran_asildi(kim, "davet" if yol.startswith("/d/") else ("api" if yol.startswith("/api/") else "sayfa")):
        return jsonify({"hata": "Çok fazla istek; biraz sonra deneyin."}), 429
    if yol.startswith("/d/"):
        return None                                          # davet linki (kendi rotası)
    if yol.startswith("/static/"):
        if yol.lower().endswith((".html", ".htm")) or yol.startswith("/static/logolar"):
            return _red(403, "Bu sayfa davetli kullanımda kapalı.")   # ham sayfalar yalnız temizlenmiş hâliyle "/"dan (2026-10-25: 23'ten buraya; Studio tek başına da korusun)
        return None
    kisi = _kisi_token(request.cookies.get("vh_misafir", ""))
    if not kisi:
        if yol in ("/", "/index.html"):
            return _sayfa("Studio", "Bu sayfa yalnızca davetle açılır. Size gönderilen davet linkini kullanın.", 403)
        return _red(401, "Davet gerekli.")
    ctx = _baglam(kisi)
    claude_yaz.MISAFIR.set(ctx)
    if yol == "/":
        return _misafir_ana(kisi)
    kural = request.url_rule.rule if request.url_rule else ""
    if request.method == "GET" and kural == "/api/ayarlar":
        return jsonify({"ozet": True, "ozet_dili": "tr", "benim_adim": kisi.get("ad") or "", "claude": bool(ctx["anahtar"]), "misafir": True})
    if request.method == "GET" and kural == "/api/claude":
        return jsonify({"giris": bool(ctx["anahtar"]), "kullanim": bool(ctx["anahtar"]), "misafir": True})
    tur = IZINLI.get(("GET" if request.method == "HEAD" else request.method, kural), "YOK")
    if tur == "YOK":
        return _red(403, "Bu özellik davetli kullanımda kapalı.")
    va = request.view_args or {}
    gid = kisi["id"]
    if tur == "temel" and _temel_sahibi(va.get("temel")) != gid:
        return _red()
    if tur == "is" and (isler.get(va.get("is_id")) or {}).get("misafir") != gid:
        return _red()
    if tur in ("indirilen", "indirilen_kapak"):
        ad = str(va.get("dosya") or "")
        if tur == "indirilen_kapak":
            ad = next((k for k in _dizin_oku() if Path(k).stem == Path(ad).stem), "")
        if not ad or _dosya_sahibi(ad) != gid:
            return _red()
    if tur in ("dosya_temel", "kapak_ad"):
        ad = str(va.get("dosya") or va.get("ad") or "")
        if _temel_sahibi(_temel_dosyadan(ad)) != gid:
            return _red()
    if tur is OZEL:
        return _ozel_denetim(kural, kisi, ctx, va)
    return None


def _yerel_izinli(link, kisi):
    return link in (kisi.get("yuklemeler") or []) and Path(link).is_file()


def _disk_yeter():
    try:
        return shutil.disk_usage(str(KLASOR)).free / 1e9 >= MISAFIR_SINIR["bos_disk_gb"]
    except Exception:  # noqa: BLE001
        return True


def _ozel_denetim(kural, kisi, ctx, va):
    gid = kisi["id"]
    v = request.get_json(silent=True) or {}
    if kural == "/api/yukle":
        if (request.content_length or 0) > MISAFIR_SINIR["yukleme_gb"] * 1e9:
            return _red(413, f"Dosya en çok {MISAFIR_SINIR['yukleme_gb']} GB olabilir.")
        if not _disk_yeter():
            return _red(507, "Şu an yer yok; daha sonra deneyin.")
        return None
    if kural == "/api/sor":
        return None                                          # sor.dizin misafirin yalnız kendi kayıtlarını görür
    if kural == "/api/onizle":
        if not _link_guvenli(request.args.get("link") or ""):
            return _red(400, "Bu adres kullanılamıyor.")
        return None
    if kural in ("/api/dublaj/<temel>", "/api/kurgu/<temel>"):
        if _temel_sahibi(va.get("temel")) != gid:
            return _red()
        if (kural == "/api/dublaj/<temel>" or v.get("olustur")) and not _disk_yeter():
            return _red(507, "Şu an yer yok; daha sonra deneyin.")
        return None
    if kural == "/api/baslat":
        islem = v.get("islem") or "transkript"
        if islem in ("dudak",):
            return _red(403, "Bu özellik davetli kullanımda kapalı.")
        if v.get("temel") and _temel_sahibi(v.get("temel")) != gid:
            return _red()
        link = str(v.get("link") or "").strip()
        if link and not re.match(r"^https?://", link) and not _yerel_izinli(link, kisi):
            return _red(403, "Yalnızca internet linki ya da kendi yüklediğiniz dosya kullanılabilir.")
        if link and re.match(r"^https?://", link) and not _link_guvenli(link):
            return _red(400, "Bu adres kullanılamıyor.")
        if not v.get("temel"):
            if _bugun_sayisi(kisi) >= MISAFIR_SINIR["gunluk"]:
                return _red(429, f"Bugünlük {MISAFIR_SINIR['gunluk']} video hakkınız doldu; yarın yeniden deneyebilirsiniz.")
            if not _disk_yeter():
                return _red(507, "Şu an yer yok; daha sonra deneyin.")
        return None
    return None


@app.after_request
def _misafir_sonra(yanit):
    """Liste uçları: sahip misafirlerin kayıtlarını, misafir yalnız kendininkini görür. Misafir isteğinde başarılı iş/yükleme kayda geçer."""
    try:
        kural = request.url_rule.rule if request.url_rule else ""
        misafir = _misafir_istek()
        gid = _gid() if misafir else ""
        if misafir:
            yanit.headers.pop("Access-Control-Allow-Origin", None)
        if misafir and not gid:
            return yanit
        if kural in ("/api/gecmis", "/api/isler", "/api/indirilenler") and yanit.status_code == 200:
            L = yanit.get_json(silent=True)
            if isinstance(L, list):
                L = [x for x in L if (x.get("misafir") or "") == gid]
                yanit.set_data(json.dumps(L, ensure_ascii=False)); yanit.headers["Content-Length"] = str(len(yanit.get_data()))
        elif kural == "/api/onizle" and misafir and yanit.status_code == 200:
            d = yanit.get_json(silent=True) or {}
            if (d.get("mevcut") or {}).get("temel") and _temel_sahibi(d["mevcut"]["temel"]) != gid:
                d.pop("mevcut", None)
            m2 = d.get("mevcut_indirme")
            if isinstance(m2, list):
                d["mevcut_indirme"] = [x for x in m2 if isinstance(x, dict) and _dosya_sahibi(x.get("ad") or "") == gid]
            elif m2 and _dosya_sahibi((m2 or {}).get("ad") or "") != gid:
                d.pop("mevcut_indirme", None)
            yanit.set_data(json.dumps(d, ensure_ascii=False)); yanit.headers["Content-Length"] = str(len(yanit.get_data()))
        elif misafir and kural == "/api/yukle" and yanit.status_code == 200:
            y = (yanit.get_json(silent=True) or {}).get("yol")
            if y:
                _yukleme_kaydet(gid, y)
        elif misafir and kural == "/api/baslat" and yanit.status_code == 200:
            v = request.get_json(silent=True) or {}
            if not v.get("temel") and (v.get("islem") or "transkript") in YENI_VIDEO_ISLEMI:
                _say(gid)
    except Exception as e:  # noqa: BLE001
        print(f"Misafir süzgeci: {e}", flush=True)
    return yanit


# ---------------------------------------------------------------------------- misafirin kendi uçları
@app.get("/d/<token>")
def misafir_davet(token):
    if not _misafir_istek():
        abort(404)
    kisi = _kisi_token(token)
    if not kisi:
        return _sayfa("Studio", "Bu davet linki geçersiz ya da kaldırılmış. Sizi davet eden kişiden yeni bir link isteyin.", 403)
    with _davet_kilit:
        d = _davetler()
        for k in d["kisiler"]:
            if k["id"] == kisi["id"]:
                k["son_giris"] = time.time()
        _davet_yaz(d)
    r = make_response(redirect("/"))
    https = request.headers.get("X-Forwarded-Proto") == "https" or request.host.endswith(".trycloudflare.com")
    r.set_cookie("vh_misafir", token, max_age=180 * 86400, httponly=True, samesite="Lax", secure=https)
    return r


@app.get("/api/misafir/ben")
def misafir_ben():
    if not _misafir_istek():
        abort(404)
    k = _kisi(_gid()) or {}
    return jsonify({"ad": k.get("ad") or "", "gunluk": MISAFIR_SINIR["gunluk"], "bugun": _bugun_sayisi(k),
                    "en_uzun_dk": MISAFIR_SINIR["en_uzun_sn"] // 60, "anahtar": bool(_anahtar(k.get("id") or ""))})


@app.post("/api/misafir/anahtar")
def misafir_anahtar_koy():
    if not _misafir_istek():
        abort(404)
    a = str((request.get_json(silent=True) or {}).get("anahtar") or "").strip()
    if not re.match(r"^sk-ant-(api|oat)\d\d-[A-Za-z0-9_\-]{20,}$", a):
        return _red(400, "Bu bir Claude anahtarına benzemiyor (sk-ant- ile başlamalı).")
    import gizli
    if not gizli.koy(f"misafir_{_gid()}", a):
        return _red(500, "Anahtar kaydedilemedi.")
    return jsonify({"tamam": True})


@app.delete("/api/misafir/anahtar")
def misafir_anahtar_sil():
    if not _misafir_istek():
        abort(404)
    import gizli
    gizli.koy(f"misafir_{_gid()}", "")
    return jsonify({"tamam": True})


@app.post("/api/misafir/cikis")
def misafir_cikis():
    if not _misafir_istek():
        abort(404)
    r = jsonify({"tamam": True})
    r.delete_cookie("vh_misafir")
    return r


# ---------------------------------------------------------------------------- sahibin uçları (8770'te IZINLI'de olmadığı için misafire kapalı)
def _davet_ozet(k, adres):
    return {"id": k["id"], "ad": k.get("ad") or "", "aktif": bool(k.get("aktif")), "olusturma": k.get("olusturma"), "son_giris": k.get("son_giris"),
            "bugun": _bugun_sayisi(k), "toplam": sum((k.get("gunluk") or {}).values()), "anahtar": bool(_anahtar(k["id"])),
            "link": f"{adres}/d/{k['token']}" if adres and k.get("token") and k.get("aktif") else ""}


def _tunel_calisiyor():
    try:
        r = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{TUNEL_ETIKET}"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and "state = running" in r.stdout
    except Exception:  # noqa: BLE001
        return False


@app.get("/api/davetler")
def davetler_get():
    adres = tunel_adresi() if _tunel_calisiyor() else ""
    return jsonify({"kisiler": [_davet_ozet(k, adres) for k in _davetler()["kisiler"]], "sinir": MISAFIR_SINIR, "adres": adres,
                    "tunel": _tunel_calisiyor(), "cloudflared": Path("/opt/homebrew/bin/cloudflared").exists()})


@app.post("/api/davetler")
def davetler_post():
    v = request.get_json(silent=True) or {}
    ad = re.sub(r"\s+", " ", str(v.get("ad") or "")).strip()[:40]
    if not ad:
        return _red(400, "Bir ad yazın.")
    with _davet_kilit:
        d = _davetler()
        if sum(1 for k in d["kisiler"] if k.get("aktif")) >= MISAFIR_SINIR["kisi"]:
            return _red(400, f"En çok {MISAFIR_SINIR['kisi']} kişi davet edilebilir; önce birini kaldırın.")
        token = secrets.token_urlsafe(24)
        k = {"id": secrets.token_hex(4), "ad": ad, "token": token, "iz": _iz(token), "aktif": True, "olusturma": time.time(), "gunluk": {}}
        d["kisiler"].append(k)
        _davet_yaz(d)
    return jsonify({"tamam": True, "kisi": _davet_ozet(k, tunel_adresi() if _tunel_calisiyor() else "")})


@app.post("/api/davetler/<gid>")
def davetler_degistir(gid):
    v = request.get_json(silent=True) or {}
    with _davet_kilit:
        d = _davetler()
        k = next((x for x in d["kisiler"] if x["id"] == gid), None)
        if not k:
            return _red()
        if "aktif" in v:
            if v["aktif"] and not k.get("aktif") and sum(1 for x in d["kisiler"] if x.get("aktif")) >= MISAFIR_SINIR["kisi"]:
                return _red(400, f"En çok {MISAFIR_SINIR['kisi']} kişi.")
            k["aktif"] = bool(v["aktif"])
        if v.get("yenile"):                                  # eski link geçersiz olur
            k["token"] = secrets.token_urlsafe(24); k["iz"] = _iz(k["token"])
        _davet_yaz(d)
    return jsonify({"tamam": True})


@app.delete("/api/davetler/<gid>")
def davetler_sil(gid):
    with _davet_kilit:
        d = _davetler()
        d["kisiler"] = [x for x in d["kisiler"] if x["id"] != gid]
        _davet_yaz(d)
    import gizli
    gizli.koy(f"misafir_{gid}", "")
    return jsonify({"tamam": True})


def _tunel_plist():
    return Path.home() / "Library" / "LaunchAgents" / f"{TUNEL_ETIKET}.plist"


@app.post("/api/davetler/tunel")
def davetler_tunel():
    """Davet linklerini aç/kapat: Cloudflare hesapsız tüneli (cloudflared) kullanıcı giriş ajanı olarak; yalnız 127.0.0.1:8770'e açılır."""
    ac = bool((request.get_json(silent=True) or {}).get("ac"))
    uid = os.getuid()
    if ac:
        cf = Path("/opt/homebrew/bin/cloudflared")
        if not cf.exists():
            return _red(400, "cloudflared kurulu değil.")
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{TUNEL_ETIKET}</string>
<key>ProgramArguments</key><array><string>{cf}</string><string>tunnel</string><string>--no-autoupdate</string><string>--url</string><string>http://127.0.0.1:{MISAFIR_PORT}</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{TUNEL_LOG}</string><key>StandardErrorPath</key><string>{TUNEL_LOG}</string>
</dict></plist>"""
        _tunel_plist().write_text(plist, encoding="utf-8")
        TUNEL_LOG.write_text("", encoding="utf-8")
        subprocess.run(["/bin/launchctl", "bootout", f"gui/{uid}/{TUNEL_ETIKET}"], capture_output=True, timeout=20)
        r = subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{uid}", str(_tunel_plist())], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return _red(500, "Tünel başlatılamadı: " + (r.stderr or r.stdout).strip()[:160])
        for _ in range(40):
            if tunel_adresi():
                break
            time.sleep(0.5)
        return jsonify({"tamam": True, "adres": tunel_adresi()})
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{uid}/{TUNEL_ETIKET}"], capture_output=True, timeout=20)
    _tunel_plist().unlink(missing_ok=True)
    return jsonify({"tamam": True, "adres": ""})


_ses_ogren_onceki = _ses_ogren


def _ses_ogren(veri):   # noqa: F811 — davetlinin verdiği adlar sahibin tanınan seslerine öğretilmez
    if veri.get("misafir") or _gid():
        return []
    return _ses_ogren_onceki(veri)


def _adres_izle():
    """Mac yeniden başlayınca hesapsız tünelin adresi değişir: değiştiğinde bildirim (linkler Ayarlar → Davetler'den yeniden gönderilir)."""
    iz = MISAFIR_KLASOR / ".son_adres"
    time.sleep(60)
    while True:
        try:
            a = tunel_adresi() if _tunel_calisiyor() else ""
            eski = iz.read_text(encoding="utf-8").strip() if iz.exists() else ""
            if a and a != eski:
                MISAFIR_KLASOR.mkdir(exist_ok=True); iz.write_text(a, encoding="utf-8")
                if eski and any(k.get("aktif") for k in _davetler()["kisiler"]):
                    _bildir("Davet adresi değişti", "Yeni linkleri Studio → Ayarlar → Davetler'den kopyalayıp gönderin.")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(120)


threading.Thread(target=_adres_izle, daemon=True).start()

OZELLIK_ADLARI.update({"/api/davetler": "Davet oluşturma"})

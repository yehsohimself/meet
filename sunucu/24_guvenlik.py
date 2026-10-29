# sunucu/24_guvenlik.py — backend gözden geçirmesinin (2026-10-25) ortak güvenlik ve dayanıklılık katmanı.
# Bulgular: (1) POST /api/ayarlar yanıtı bütün ayarları SIRLARLA birlikte döndürüyordu (GET maskeliyordu, POST maskelemiyordu; ağ paylaşımı açık ve PIN
# yokken aynı ağdaki herkes boş bir POST ile Asana belirtecini okuyabilirdi); (2) sır alanlarına sayı gönderilince "123" olarak kaydediliyordu (test
# sırasında gerçek Asana belirteci bu yüzden silindi); (3) /api/segment ve /api/kurgu bozuk sayı alınca HTML 500 dönüyordu.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
import gzip
import hashlib
import traceback

import gizli

SIR_ANAHTARLARI = set(gizli.SIRLAR) | {"fal_anahtar"}
LISTE_ALANLARI = ("musteriler", "sozluk", "benim_epostalar", "abonelikler", "bulten_gonderenler", "bulten_kutulari")


def _sir_mi(k):
    return k in SIR_ANAHTARLARI or k.endswith(("_token", "_anahtar", "_ics", "_pin"))


YEREL_YAZMA = ("/api/uzanti/", "/api/x/", "/api/ig/", "/api/kayit/dosya")   # uzantı/kaydedici uçları: POST yalnız bu Mac'ten (LAN'dan profil zehirlenmesin)


@app.before_request
def _yerel_yazma():
    ra = request.remote_addr or ""
    if request.method in ("POST", "DELETE", "PUT") and request.path.startswith(YEREL_YAZMA) \
            and not (ra in ("127.0.0.1", "::1") or ra.startswith("::ffff:127.")):
        return jsonify({"hata": "Bu uç yalnızca bu bilgisayardan kullanılır."}), 403
    return None


@app.before_request
def _ayar_dogrula():
    if request.method != "POST" or (request.url_rule.rule if request.url_rule else "") != "/api/ayarlar":
        return None
    v = request.get_json(silent=True)
    if not isinstance(v, dict):
        return jsonify({"hata": "Ayarlar JSON nesnesi olmalı."}), 400
    for k, deger in v.items():
        if _sir_mi(k) and not isinstance(deger, str):
            return jsonify({"hata": f"{k} metin olmalı."}), 400
        if k in LISTE_ALANLARI and not (isinstance(deger, list) and all(isinstance(x, str) for x in deger)):
            return jsonify({"hata": f"{k} metin listesi olmalı."}), 400
    yol = v.get("drive_yol")
    if yol is not None and (not isinstance(yol, str) or not Path(yol).expanduser().is_dir() or not str(Path(yol).expanduser().resolve()).startswith(str(Path.home()))):
        return jsonify({"hata": "Drive klasörü ev klasörünüzün içinde var olan bir klasör olmalı."}), 400
    return None


@app.after_request
def _sir_maskele(yanit):
    """/api/ayarlar yanıtlarında (GET ve POST) sır alanları hiç dönmez; yalnız *_bagli bayrakları."""
    try:
        if (request.url_rule.rule if request.url_rule else "") == "/api/ayarlar" and yanit.status_code == 200:
            d = yanit.get_json(silent=True)
            if isinstance(d, dict) and any(_sir_mi(k) for k in d):
                for k in [k for k in d if _sir_mi(k)]:
                    if k not in ("takvim_ics",):
                        d[k.replace("_token", "").replace("_anahtar", "").replace("_pin", "") + ("_var" if k.endswith("_pin") else "_bagli")] = bool(d[k])
                    d.pop(k, None)
                yanit.set_data(json.dumps(d, ensure_ascii=False)); yanit.headers["Content-Length"] = str(len(yanit.get_data()))
    except Exception as e:  # noqa: BLE001
        print(f"Sır maskeleme: {e}", flush=True)
    return yanit


@app.errorhandler(Exception)
def _api_hatasi(e):
    """/api/* altında beklenmeyen hata: HTML 500 yerine JSON; ayrıntı site.log'a. HTTP hataları (404, 405...) olduğu gibi."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    _hata_kaydet(f"{request.method} {request.path}", e, traceback.format_exc())
    if request.path.startswith("/api/"):
        if isinstance(e, (ValueError, TypeError, KeyError)):
            return jsonify({"hata": "Gönderilen bilgi beklenen biçimde değil."}), 400
        return jsonify({"hata": "İşlem yapılamadı; ayrıntı kayıt dosyasında."}), 500
    return "Bir hata oldu.", 500


# ---- Sıkıştırma ve önbellek başlıkları (2026-10-25 gözden geçirme: index.html 777 KB sıkıştırmasız + no-cache, /api/gecmis 105 KB, /api/paylasimlar 186 KB)
SIKISTIR = ("text/html", "application/json", "text/css", "application/javascript", "text/javascript", "text/plain", "image/svg+xml", "text/markdown")
_gz_onbellek = {}            # (yol, md5) → gzip gövde (büyük sabit yanıtlar: index.html, static)


@app.after_request
def _sikistir(yanit):
    try:
        if request.path.startswith("/static/") and request.args.get("v"):
            yanit.headers["Cache-Control"] = "public, max-age=31536000, immutable"       # ?v= sürümlü dosyalar
        statik = request.path.startswith(("/static/derlenmis/", "/static/studio_ek", "/static/meet_ek", "/static/misafir"))
        if yanit.status_code == 200 and statik:
            yanit.direct_passthrough = False                   # sürümlü büyük betik/stil dosyaları da sıkıştırılır (md5 ile bir kez)
        if yanit.status_code != 200 or yanit.direct_passthrough or (yanit.is_streamed and not statik) or "Content-Encoding" in yanit.headers:
            return yanit
        if "gzip" not in (request.headers.get("Accept-Encoding") or "") or not yanit.mimetype or not yanit.mimetype.startswith(SIKISTIR):
            return yanit
        govde = yanit.get_data()
        if len(govde) < 1024:
            return yanit
        if len(govde) > 100_000:                                   # büyük ve sık istenen gövdeler (ana sayfa) bir kez sıkıştırılır
            k = (request.path, hashlib.md5(govde).hexdigest())
            gz = _gz_onbellek.get(k)
            if gz is None:
                gz = gzip.compress(govde, 6)
                if len(_gz_onbellek) > 40:
                    _gz_onbellek.clear()
                _gz_onbellek[k] = gz
        else:
            gz = gzip.compress(govde, 5)
        yanit.set_data(gz)
        yanit.headers["Content-Encoding"] = "gzip"; yanit.headers["Content-Length"] = str(len(gz))
        yanit.headers.add("Vary", "Accept-Encoding")
    except Exception as e:  # noqa: BLE001
        print(f"Sıkıştırma: {e}", flush=True)
    return yanit


# Sıkıştırma EN SON çalışmalı (2026-10-29 bulundu): Flask after_request işlevlerini kayıt sırasının tersiyle çalıştırır; bu parça 22/23'ten sonra
# yüklendiği için sıkıştırma onlardan ÖNCE çalışıyordu. Tarayıcı gzip istediğinde yanıtı okuyup yeniden yazan süzgeçler (davetliye yalnız kendi
# kayıtları, sır maskeleme, davet listesine Meet bağlantıları) sıkıştırılmış gövdeyi okuyamıyor, ya hiç süzmüyor ya da gövdeyi bozuyordu. Testler gzip
# istemediği için görünmüyordu. Listenin başına alınınca hangi parça sonradan kaydolursa olsun en son çalışır.
_sonra = app.after_request_funcs.setdefault(None, [])
if _sikistir in _sonra:
    _sonra.remove(_sikistir)
_sonra.insert(0, _sikistir)


# ---- Arka plan hataları görünür olsun (2026-10-25: 110 traceback günlerce fark edilmedi). threading.excepthook + sayaç + /api/hatalar.
import threading as _threading

_hatalar = {"sayi": 0, "son": []}


def _hata_kaydet(kaynak, e, tb=""):
    _hatalar["sayi"] += 1
    _hatalar["son"] = (_hatalar["son"] + [{"t": time.time(), "kaynak": str(kaynak)[:80], "hata": str(e)[:200]}])[-30:]
    print(f"HATA [{kaynak}]: {e}\n{tb}", flush=True)


def _thread_hatasi(args):
    import traceback as _tb
    _hata_kaydet(getattr(args.thread, "name", "?"), args.exc_value, "".join(_tb.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


_threading.excepthook = _thread_hatasi


@app.get("/api/hatalar")
def hatalar_get():
    return jsonify({"sayi": _hatalar["sayi"], "son": _hatalar["son"][::-1], "baslangic": BASLANGIC})


BASLANGIC = time.time()

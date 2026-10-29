# sunucu/30_kayit_disi.py — Meet: kaydedilmeyen toplantılar (2026-10-29; kullanıcı: "Kurs meetlerini kaydetmeye gerek yok. Her hafta tekrar
# ediyor, anlarsın zaten."). Liste ayarlar.json `kayit_disi` (kayit_disi.py). Kaydedici listeyi okuyup bu görüşmelerde kayda başlamaz; burada:
# uzantı nabzı (07) bu görüşmede `.uzanti_arama` yerine `.kayit_disi_arama` yazar, gelen kayıt (04 /api/kayit/dosya) yazıya dökülmeden çöpe gider,
# canlı yazıya dökme ve "kaydediliyor" bildirimi (27) atlanır. Liste kendiliğinden büyür: onay kartında Kaldır (04 toplanti_onay) ya da toplantı
# kapısının aynı adlı kaydı iki ayrı günde "toplantı değil" bulması (04 _toplanti_bitir_ic).
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
import kayit_disi as kayit_disi_modulu

KAYIT_DISI_GECMIS = KAYIT / ".kayit_disi_gecmis.json"
KAYIT_DISI_KILIT = threading.Lock()          # genel `kilit` tutulurken de çağrılabilsin diye ayrı


def _kayit_disi_ayar():
    """Yalnız ayar dosyası (sır değil; Anahtar Zinciri'ne gidilmez: kayıt sürerken 5 sn'de bir okunuyor)."""
    try:
        return json.loads(AYARLAR_DOSYASI.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _kayit_disi_eslesen(*basliklar):
    """Başlıklardan biri kaydedilmeyen bir toplantıya uyuyorsa o kayıt (dict), yoksa None."""
    try:
        return kayit_disi_modulu.eslesen([str(b) for b in basliklar if b], _kayit_disi_ayar())
    except Exception as e:  # noqa: BLE001
        print(f"Kaydedilmeyen toplantı denetimi: {e}", flush=True)
        return None


def _kayit_disi_ekle(ad, neden, otomatik=False, desenler=None):
    """Listeye ekler; eklendiyse True. Kilit altında oku-yaz (aynı anda gelen ayar yazımı ezmesin)."""
    with KAYIT_DISI_KILIT:
        ay = ayarlar_oku()
        yeni, eklendi = kayit_disi_modulu.ekle(ay, ad, desenler, neden, otomatik)
        if eklendi:
            ay["kayit_disi"] = yeni; ayarlar_yaz(ay)
    if eklendi:
        print(f"Kaydedilmeyen toplantılara eklendi: {ad} ({neden})", flush=True)
    return eklendi


def _kayit_disi_at(yol, mik=""):
    """Kaydedilmeyen görüşmenin ses dosyalarını yazıya dökmeden çöpe (.cop, bir gün sonra temizlenir) taşır."""
    COP.mkdir(exist_ok=True)
    for f in (Path(str(yol or "")), Path(str(mik or ""))):
        try:
            if f.name and f.is_file() and str(f).startswith(str(KAYIT) + "/"):
                shutil.move(str(f), str(COP / f"kayit_disi__{f.name}"))
        except OSError as e:
            print(f"Kaydedilmeyen kayıt taşınamadı: {e}", flush=True)


def _kayit_disi_ogren_kapi(baslik, gun=None):
    """Toplantı kapısı bir kaydı 'toplantı değil' buldu: aynı ad ikinci ayrı günde de böyleyse listeye girer ve bir kez bildirilir."""
    ad = kayit_disi_modulu.imza(baslik)
    if not ad:
        return False
    n = kayit_disi_modulu.aday_kaydet(KAYIT_DISI_GECMIS, ad, "kapi", gun)
    if n >= 2 and _kayit_disi_ekle(ad, f"{n} ayrı günde toplantı olmayan kayıt", otomatik=True):
        _bildir(f"“{ad}” artık kaydedilmeyecek", "Tekrar eden ve toplantıya benzemeyen bir görüşme. Ayarlar → Kayıt'tan geri açabilirsiniz.",
                url="http://127.0.0.1:8766/")
        return True
    return False


@app.get("/api/kayit-disi")
def kayit_disi_get():
    return jsonify({"liste": kayit_disi_modulu.liste(ayarlar_oku())})


@app.post("/api/kayit-disi")
def kayit_disi_post():
    """{ekle: ad} listeye ekler; {sil: sıra} ya da {sil_ad: ad} çıkarır (onay kartındaki Geri al da bunu kullanır)."""
    v = request.get_json(silent=True) or {}
    if v.get("ekle"):
        ad = re.sub(r"\s+", " ", str(v["ekle"])).strip()[:60]
        if len(ad) < 3:
            return jsonify({"hata": "En az üç harf yazın."}), 400
        _kayit_disi_ekle(ad, "Elle eklendi")
    elif "sil" in v or v.get("sil_ad"):
        with KAYIT_DISI_KILIT:
            ay = ayarlar_oku(); L = list(ay.get("kayit_disi") or [])
            if "sil" in v:
                i = int(v["sil"])
                if 0 <= i < len(L):
                    L.pop(i)
            else:
                L = [x for x in L if (x.get("ad") if isinstance(x, dict) else x) != v["sil_ad"]]
            ay["kayit_disi"] = L; ayarlar_yaz(ay)
    return jsonify({"liste": kayit_disi_modulu.liste(ayarlar_oku())})

# sunucu/11_ozellik_sayaci.py — özellik kullanım sayacı.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- özellik kullanım sayacı (2026-10-19)
OZELLIK_SAYAC = KAYIT / ".ozellik_kullanim.json"
_ozellik_bellek = {"son_yazma": 0.0, "veri": None}
OZELLIK_ADLARI = {
    "/api/ghost/yaz": "Ghost girdisi (link/yazı/fikir)", "/api/secki/yaz": "Ghost: seçkiden yaz", "/api/ghost/sesli-not": "Ghost: sesli not", "/api/ghost/soru/cevap": "Ghost: günün sorusu cevabı", "/api/ghost/mac": "Ghost: maç defteri", "/api/ghost/birlestir": "Ghost: iki notu birleştir", "/api/ghost/not": "Ghost: defterdeki notu yaz/sil", "/api/ghost/gorus-aday": "Ghost: görüş adayı kararı", "/api/paylasim/<temel>/<int:i>/alinti": "Ghost: alıntıyla yaz", "/api/paylasim/<temel>/<int:i>/dayanak": "Ghost: kendi karşılığıyla yaz", "/api/kesif/yaz": "Ghost: keşiften yaz", "/api/kesif/story": "Ghost: story paylaşıldı", "/api/kesif/yenile": "Ghost: keşfi yenile", "/api/paylasim/<temel>/elenen/<int:j>": "Ghost: elenen fikri yaz", "/api/drive-oku/baglan": "Drive okuma bağlantısı", "/api/amac": "Amaç kapısı", "/api/tahmin/<tid>": "Tahmin sonucu", "/api/kapsam/eposta": "Ek iş e-postası",
    "/api/kayit/yukle": "Telefondan/dosyadan toplantı kaydı",
    "/api/sirket/<kod>/yorum": "Şirket genel yorumu",
    "/api/danisman/<temel>": "Kariyer danışmanı notu",
    "/api/kisaca/<temel>/is": "Toplantı işi işaretleme",
    "/api/sohbet/<temel>": "Toplantıyla sohbet", "/api/tarif/<temel>": "Tarif", "/api/canli/not": "Toplantıda not/işaret",
    "/api/baslat": "Yazıya dökme", "/api/ceviri/<temel>": "Çeviri", "/api/sor": "Soru-cevap",
    "/api/ozet/<temel>": "Özet (yeniden)", "/api/klipler/<temel>": "Öne çıkan anlar", "/api/marka-etiket/<temel>": "Marka serisine ekleme",
    "/api/isimlendir/<temel>": "Konuşmacı adı verme", "/api/segment/<temel>": "Paragraf konuşmacısı değiştirme", "/api/takip": "Kanal takibi",
    "/api/marka/<temel>": "Marka paketi", "/api/marka-shorts/<temel>": "Marka Shorts", "/api/marka-kapak/<temel>": "Kapak taslakları",
    "/api/paylasim/<temel>": "Paylaşım fikirleri (elle)", "/api/paylasim/<temel>/<int:i>": "Paylaşım kararı", "/api/paylasim/<temel>/<int:i>/yeniden": "Paylaşım yeniden yaz", "/api/paylasim/<temel>/<int:i>/yorum": "Ghost: taslağa yorum",
    "/api/notlar/<temel>": "Toplantı notları", "/api/brief/<temel>": "Brief çıkarma", "/api/takip-eposta/<temel>": "Takip e-postası",
    "/api/asana/gorev/<temel>": "Asana'ya görev", "/api/drive/yukle/<temel>": "Drive'a yükleme", "/api/haftalik/<tur>": "Haftalık özet (elle)",
    "/api/atolye/calistir": "Atölye çalışması", "/api/atolye/<cid>/akis": "Atölye akış işlemleri", "/api/atolye/kadro/<kkod>": "Atölye kadro düzenleme",
    "/api/atolye/marka/<mkod>": "Marka profili düzenleme", "/api/atolye/ornek": "Atölye örnek havuzu", "/api/atolye/bilgi/<kkod>/yenile": "Bilgi kartı tazeleme",
    "/api/kayit/baslat": "Elle toplantı kaydı", "/api/on-brifing/hazirla": "Toplantı öncesi not", "/api/yukle": "Dosya yükleme",
}


BASLAT_ADLARI = {"transkript": "Yazıya dökme", "ozet": "Özetle", "indir": "Video indirme", "altyazili": "Altyazılı video", "klip": "Klip",
                 "kesim": "Metinden kesme", "sessizlik": "Sessizlikleri kesme / kurgu aktarımı", "dublaj": "Seslendirme (dublaj)"}


@app.after_request
def _ozellik_say(yanit):
    """Kullanıcı eylemlerini (POST) özellik adıyla günlük sayar: hangi özellikler gerçekten kullanılıyor (sadeleştirme kararları için)."""
    try:
        kural = request.url_rule.rule if request.url_rule else ""
        if request.method == "POST" and kural.startswith("/api/") and kural in OZELLIK_ADLARI and yanit.status_code < 400:
            ad_ = OZELLIK_ADLARI[kural]
            if kural == "/api/baslat":                     # tek uç birçok işi başlatır: işleme göre ad
                ad_ = BASLAT_ADLARI.get(str((request.get_json(silent=True) or {}).get("islem") or "transkript"), ad_)
            if _ozellik_bellek["veri"] is None:
                _ozellik_bellek["veri"] = json.loads(OZELLIK_SAYAC.read_text(encoding="utf-8")) if OZELLIK_SAYAC.exists() else {}
            gun = time.strftime("%Y-%m-%d")
            g = _ozellik_bellek["veri"].setdefault(gun, {})
            g[ad_] = g.get(ad_, 0) + 1
            if time.time() - _ozellik_bellek["son_yazma"] > 120:
                eski = time.strftime("%Y-%m-%d", time.localtime(time.time() - 120 * 86400))
                _ozellik_bellek["veri"] = {k: x for k, x in _ozellik_bellek["veri"].items() if k >= eski}
                OZELLIK_SAYAC.write_text(json.dumps(_ozellik_bellek["veri"], ensure_ascii=False), encoding="utf-8")
                _ozellik_bellek["son_yazma"] = time.time()
    except Exception:  # noqa: BLE001
        pass
    return yanit


def ozellik_kullanimi(gun=30):
    veri = _ozellik_bellek["veri"] if _ozellik_bellek["veri"] is not None else (
        json.loads(OZELLIK_SAYAC.read_text(encoding="utf-8")) if OZELLIK_SAYAC.exists() else {})
    sinir = time.strftime("%Y-%m-%d", time.localtime(time.time() - gun * 86400))
    top = {}
    for g, d in veri.items():
        if g >= sinir:
            for ad, n in d.items():
                top[ad] = top.get(ad, 0) + n
    return {"kullanilan": sorted(top.items(), key=lambda x: -x[1]),
            "kullanilmayan": sorted((set(OZELLIK_ADLARI.values()) | set(BASLAT_ADLARI.values())) - set(top)),
            "baslangic": min(veri) if veri else None}



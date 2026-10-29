# sunucu/01_yardimcilar.py — yardımcılar.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- yardımcılar
def _zaman(sn, saatli=False):
    import ortak
    return ortak.zaman(sn, saatli)


def _env():
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    return env


def _bildir(baslik, metin, url=""):
    """macOS bildirimi (sessizce başarısız olabilir). url verilirse ve kaydedici bildirim gösterebiliyorsa (kayitlar/.bildirim/.destek), bildirime
    tıklayınca o sayfa açılır (2026-10-24; osascript bildirimi tıklanınca Komut Dosyası Düzenleyicisi'ni açıyordu). 20 sn içinde gösterilmezse eski yol."""
    kl = KAYIT / ".bildirim"
    try:
        if url and (kl / ".destek").exists() and time.time() - (kl / ".destek").stat().st_mtime < 120:
            f = kl / f"{time.time():.3f}.json"
            f.write_text(json.dumps({"baslik": baslik, "metin": metin, "url": url}, ensure_ascii=False), encoding="utf-8")

            def _yedek():
                time.sleep(20)
                if f.exists():
                    f.unlink(missing_ok=True); _bildir(baslik, metin)
            threading.Thread(target=_yedek, daemon=True).start()
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        subprocess.Popen(["/usr/bin/osascript", "-e",
                          f'display notification "{metin.replace(chr(92), " ").replace(chr(34), " ")}" with title "{baslik.replace(chr(92), " ").replace(chr(34), " ")}"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        pass


def _dayanikli(fn, ad=""):
    """İşçi döngüsünü sarar: beklenmeyen bir hata (ör. eksik alanlı iş kaydı) iş parçacığını öldürüp kuyruğu sonsuza dek kilitlemesin
    (2026-10-25 gözden geçirme). Hata loglanır, 2 sn sonra döngü yeniden başlar."""
    import traceback

    def _calis():
        while True:
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                print(f"İşçi {ad or fn.__name__} hata verdi, yeniden başlıyor: {e}\n{traceback.format_exc()}", flush=True)
                time.sleep(2)
    return _calis


def _json_yaz_atomik(yol, veri, yedek=False):
    """JSON'u önce geçici dosyaya yazıp yerine koyar (yarıda kesilen yazım dosyayı bozmasın); yedek=True ise eskisi .bak olarak kalır."""
    yol = Path(yol)
    tmp = yol.with_name(yol.name + ".tmp")
    tmp.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    if yedek and yol.exists():
        try:
            shutil.copy2(str(yol), str(yol.with_name(yol.name + ".bak")))
        except OSError:
            pass
    tmp.replace(yol)


def _kaydet():
    """İş listesini diske yaz (kayıt satırlarının sadece sonu)."""
    try:
        with kilit:
            veri = {}
            for k, v in isler.items():
                d = {kk: vv for kk, vv in v.items() if kk not in ("p", "log")}
                d["log"] = v.get("log", [])[-60:]
                veri[k] = d
            tmp = ISLER_DOSYASI.with_name(ISLER_DOSYASI.name + ".tmp")
            tmp.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8"); tmp.replace(ISLER_DOSYASI)   # atomik (2026-10-25)
    except Exception as e:  # noqa: BLE001
        print(f"İş listesi yazılamadı: {e}", flush=True)


def _yukle():
    if not ISLER_DOSYASI.exists():
        return
    try:
        veri = json.loads(ISLER_DOSYASI.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    simdi = time.time()
    devam = []
    for k, v in veri.items():
        if simdi - v.get("olusturma", 0) > 86400:
            continue
        if v.get("durum") in ("sirada", "calisiyor"):
            n = int(v.get("yeniden_sayisi") or 0)
            if n < 2 and _devam_edebilir(v):             # site yeniden başladı: iş kaybolmasın, baştan sıraya girsin
                v.update({"durum": "sirada", "yeniden_sayisi": n + 1, "ilerleme": 0, "adim": 0,
                          "adim_metni": "Site yeniden başladı; iş yeniden sıraya alındı"})
                v.pop("hata", None); v.pop("dosya", None)
                devam.append(k)
            else:
                v["durum"] = "kesildi"
                v["hata"] = "Site kapanınca bu iş yarım kaldı."
        isler[k] = v
    for k in sorted(devam, key=lambda x: isler[x].get("olusturma", 0)):
        (sira_indir if isler[k].get("tur") else sira).put(k)
    if devam:
        print(f"Yarım kalan {len(devam)} iş yeniden sıraya alındı", flush=True)


def _devam_edebilir(v):
    """Yarım iş yeniden çalıştırılabilir mi: link geçerli ya da yerel dosya / transkript hâlâ yerinde."""
    if v.get("tur") in ("altyazili", "klip", "kesim", "dublaj", "sessizlik"):
        return bool(v.get("temel")) and (KLASOR / f"{v['temel']}.json").exists()
    link = str(v.get("link") or "")
    return bool(re.match(r"^https?://", link)) or (bool(link) and Path(link).is_file())


def _ozet_dili(ay=None):
    """Özet dili: ayar `ozet_dili` (tr | auto); arayüz dili İngilizceyse ve özet dili varsayılan Türkçe kaldıysa İngilizce (2026-10-25)."""
    ay = ay if ay is not None else ayarlar_oku()
    od = ay.get("ozet_dili", "tr")
    return "en" if ay.get("dil") == "en" and od == "tr" else od


def mesgul_nedenler():
    """Yeniden başlatmayı bekletmesi gereken süren işler (boş liste = güvenli)."""
    n = []
    # arka plan öğrenmesinin (atölye bilgi kartı) işleri sayılmaz: açılışta yeniden sıraya girer; saysaydık site hiç boş kalmıyordu
    calisan = [i for i in list(isler.values()) if i.get("durum") in ("calisiyor", "sirada") and "/.atolye/" not in str(i.get("link") or "")
               or i.get("durum") in ("calisiyor", "sirada") and any(x.get("calisiyor") for x in list(globals().get("atolye_durum", {}).values()))]
    # 2026-10-25: ürünler ayrı kurulabilir (yalnız Studio gibi); başka ürünün durum sözlüğü yoksa boş sayılır (globals().get)
    if calisan:
        n.append(f"{len(calisan)} iş sürüyor ya da sırada")
    for ad, d in (("içerik paketi", globals().get("marka_durum", {})), ("çeviri", ceviri_durum), ("X paylaşımları", globals().get("paylasim_durum", {})), ("brief", globals().get("brief_durum", {}))):
        if any((x or {}).get("calisiyor") for x in list(d.values())):
            n.append(f"{ad} hazırlanıyor")
    if globals().get("haftalik_durum", {}).get("calisiyor"):
        n.append("haftalık özet hazırlanıyor")
    if globals().get("toplanti_bitiren"):
        n.append("toplantı sonrası adımlar sürüyor")
    if globals().get("ghost_defter_durum", {}).get("calisiyor"):
        n.append("Ghost defteri hazırlanıyor")
    if globals().get("kesif_durum", {}).get("calisiyor"):
        n.append("Ghost keşfi sürüyor")
    if globals().get("blog_durum", {}).get("calisiyor"):
        n.append("Ghost blog konuları hazırlanıyor")
    if any(x.get("calisiyor") for x in list(globals().get("atolye_durum", {}).values())):
        n.append("atölye çalışması sürüyor")
    if ozet_calisan or klip_calisan:
        n.append("özet ya da öne çıkan anlar hazırlanıyor")
    for _m in ("content_site", "couple_site", "pt_site"):
        if _m in globals():
            n += globals()[_m].mesgul()
    n += [f"Ghost: {ad}" for ad, d in globals().get("ghost_gelisim_durum", {}).items() if d.get("calisiyor")]
    if globals().get("meet_gelisim_durum", {}).get("calisiyor"):
        n.append("Meet: " + globals()["meet_gelisim_durum"]["calisiyor"])
    try:
        if any(time.time() - f.stat().st_mtime < 30 for f in KAYIT.glob("Toplantı *.m4a")):
            n.append("toplantı kaydı sürüyor")
    except Exception:  # noqa: BLE001
        pass
    return n


def guvenli_yeniden_baslat(en_cok_dk=60):
    """Site kendini yeniden başlatacaksa (ör. ağ paylaşımı) süren işlerin bitmesini bekler."""
    def _bekle():
        bitis = time.time() + en_cok_dk * 60
        time.sleep(0.8)
        while mesgul_nedenler() and time.time() < bitis:
            time.sleep(10)
        subprocess.Popen(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.yehso.transkript"])
    threading.Thread(target=_bekle, daemon=True).start()


def _model_var(model):
    return any((HF / ad / "snapshots").exists() for ad in MODEL_KLASORLERI[model])


def _mevcut_kayit(video_id, link):
    for js in KLASOR.glob("transkript_*.json"):
        try:
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        if (video_id and v.get("video_id") == video_id) or (link and v.get("link") == link):
            return {"temel": js.stem, "baslik": v.get("baslik") or js.stem,
                    "tarih": v.get("olusturma") or js.stat().st_mtime}
    return None


def _kapak_indir(temel, url):
    if not url:
        return
    hedef = KLASOR / f"{temel}.jpg"
    if not re.match(r"^https?://", str(url)):              # 2026-10-25 güvenlik: file:// ile yerel dosya okunmasın
        return
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r, open(hedef, "wb") as f:
            f.write(r.read(8 * 1024 * 1024))
    except Exception:  # noqa: BLE001
        if hedef.exists():
            hedef.unlink()


def _kapak_yolu(temel, uzak):
    if (KLASOR / f"{temel}.jpg").exists():
        return f"/kapak/{temel}.jpg"
    return uzak or ""


def _hata_metni(kayit):
    """Scriptin terminal dilindeki hatasını sade web diline çevir."""
    k = kayit.lower()
    if "drm" in k or "kopya korumalı" in k:
        return "Bu video kopya korumalı; sesi alınamıyor. Bu tür videolar yazıya dökülemez."
    if "giriş istiyor" in k or "login required" in k or "sign in" in k or "cookies" in k or "rate-limit" in k:
        return "Bu site giriş istiyor. Tarayıcınızdaki oturumla tekrar deneyin."
    if "not a bot" in k or "please update" in k or "yt-dlp -u" in k or "update to the latest" in k:
        return "Video sitesi yöntem değiştirmiş; indirme aracının güncellenmesi gerekiyor."
    if "bulunamadı ya da gizli" in k or "private video" in k or "404" in k or "not available" in k:
        return "Video bulunamadı ya da gizli. Link doğru mu?"
    if "desteklenmiyor" in k or "unsupported url" in k:
        return "Bu link bir video sayfası değil ya da site desteklenmiyor."
    if "konuşma tespit" in k:
        return "Videoda konuşma bulunamadı."
    for satir in reversed(kayit.splitlines()):
        if satir.startswith("HATA"):
            return satir.replace("HATA:", "").replace("--cerez chrome (veya safari) ile", "tarayıcı oturumunuzla").strip()
    return "Bir şeyler ters gitti. Ayrıntılı kayıtta sebebi görebilirsiniz."



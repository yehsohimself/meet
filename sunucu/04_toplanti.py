# sunucu/04_toplanti.py — toplantı kaydı, toplantı sonrası adımlar, Google Drive.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- toplantı kaydı + Google Drive
def _drive_bagli():
    if not RCLONE.exists():
        return False
    try:
        p = subprocess.run([str(RCLONE), "listremotes"], capture_output=True, text=True, timeout=10)
        return f"{DRIVE_REMOTE}:" in p.stdout.split()
    except Exception:  # noqa: BLE001
        return False


drive_durum = {"calisiyor": False, "hata": ""}


def _rclone_yetki(uzak, kapsam, durum):
    """rclone authorize: tarayıcıda Google izin sayfası açılır; kullanıcı onaylayınca `uzak` oluşturulur. rclone 1.7x ayarları
    base64 (URL güvenli, dolgusuz) JSON ister ve yanıtı da öyle verir; eski sürüm düz '{token}' yazıyordu, ikisi de okunur."""
    import base64
    durum.update({"calisiyor": True, "hata": ""})
    try:
        ayar = base64.urlsafe_b64encode(json.dumps({"scope": kapsam}).encode()).decode().rstrip("=")
        p = subprocess.run([str(RCLONE), "authorize", "drive", ayar], capture_output=True, text=True, timeout=600, env=_env())
        cikti = p.stdout + p.stderr
        m = re.search(r"--->\s*(\S.*?)\s*<---", cikti, re.S)
        if not m:
            durum["hata"] = "Yetki alınamadı; tarayıcıdaki izin sayfası tamamlanmadı."
            return
        ham = m.group(1).strip()
        if ham.startswith("{"):
            token = ham.replace("\n", "")
        else:
            token = json.loads(base64.urlsafe_b64decode(ham + "=" * (-len(ham) % 4)))["token"]
        q = subprocess.run([str(RCLONE), "config", "create", uzak, "drive", f"token={token}", f"scope={kapsam}", "--non-interactive"],
                           capture_output=True, text=True, timeout=60, env=_env())
        if q.returncode != 0:
            durum["hata"] = (q.stderr or q.stdout).strip()[-200:] or "Bağlantı kaydedilemedi."
    except subprocess.TimeoutExpired:
        durum["hata"] = "Zaman aşımı; tekrar deneyin."
    except Exception as e:  # noqa: BLE001
        durum["hata"] = str(e)[:200]
    finally:
        durum["calisiyor"] = False


def _drive_baglan():
    _rclone_yetki(DRIVE_REMOTE, "drive.file", drive_durum)


def _drive_yukle(dosyalar, klasor):
    """[(yerel_yol, drive_adı)] → Drive'da klasor altına kopyalar. Döner: hata metni ya da ''."""
    for yol, ad in dosyalar:
        if not Path(yol).exists():
            continue
        p = subprocess.run([str(RCLONE), "copyto", str(yol), f"{DRIVE_REMOTE}:{klasor}/{ad}", "--retries", "3"],
                           capture_output=True, text=True, timeout=1800, env=_env())
        if p.returncode != 0:
            return (p.stderr or p.stdout).strip().splitlines()[-1:][0] if (p.stderr or p.stdout).strip() else "yüklenemedi"
    return ""


def _toplanti_adi_temizle(s):
    """Sekme/pencere başlığından toplantı adını ayıklar; genel adlar ('Meet', 'Microsoft Teams', 'Zoom Meeting') boş döner."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if re.fullmatch(r"display \d+ backstop|backstop.*|.*\bbackstop", s, re.I):   # 23 Ekim: macOS'un tam ekran arka plan penceresi ("Display 3 Backstop") ad sanıldı
        return ""
    s = re.sub(r"^\s*Meet\s*[-–|]\s*", "", s)
    s = re.sub(r"\s*[-–|]\s*(Google Meet|Microsoft Teams|Teams|Zoom|Zoom Meeting|Zoom Workplace)\s*$", "", s, flags=re.I)
    s = re.sub(r"^\(\d+\)\s*", "", s).strip(" -–|")
    # toplantı olmayan sekme/pencere (21 Ekim: kayıt biterken öndeki sekme 'Notifications / X 🔊' toplantı adı sanıldı) ve çıplak Meet kodu
    if re.search(r"(\s/\s?X$|^X$|notifications|bildirimler|youtube|gmail|inbox|gelen kutusu|whatsapp|instagram|facebook|linkedin|netflix|spotify|twitch|"
                 r"google'da ara|google search|new tab|yeni sekme|🔊|backstop)", s, re.I) or re.fullmatch(r"[a-z]{3}-[a-z]{4}-[a-z]{3}", s.strip().lower()):
        return ""
    if s.lower() in ("", "meet", "google meet", "microsoft teams", "teams", "zoom", "zoom meeting", "zoom workplace", "meeting", "toplantı", "calls", "aramalar"):
        return ""
    if re.fullmatch(r"[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+", s):          # 27 Ekim: uygulamaların iç pencere adları (Zoom 'StatusIndicator') toplantı adı sanıldı
        return ""
    return s[:90]


def _pencere_toplanti_adi(pencere, uygulama):
    """Kaydedicinin bildirdiği pencere başlığından toplantı adı; yalnız gerçekten toplantı penceresiyse (2026-10-27).
    Kaydedici uygulamanın en uzun pencere başlığını gönderiyordu: Chrome'da başka bir pencerenin sekmesi ('underbelly'), Zoom'da iç pencere adı
    ('StatusIndicator') toplantı adı oldu. Tarayıcıda yalnız Google Meet / Teams / Zoom sayfası başlığı; Zoom masaüstü pencere adları toplantıyı
    anlatmaz (hep 'Zoom Meeting' ya da iç adlar), kullanılmaz; Teams masaüstünde yalnız '… | Microsoft Teams'."""
    p = re.sub(r"\s+", " ", str(pencere or "")).strip(); u = str(uygulama or "").lower()
    if not p:
        return ""
    if any(x in u for x in ("chrome", "safari", "firefox", "edge", "brave", "browser", "arc", "opera")):
        if not re.search(r"^\s*Meet\s*[-–]|[-–|]\s*(Google Meet|Microsoft Teams)\s*$|Zoom Meeting|zoom\.us", p, re.I):
            return ""
    elif "zoom" in u:
        return ""
    elif "teams" in u and "microsoft teams" not in p.lower():
        return ""
    return _toplanti_adi_temizle(p)


def _toplanti_baslik(veri):
    """Özetten 4-8 kelimelik konu başlığı; model yoksa boş."""
    o = veri.get("ozet") or {}
    metin = (o.get("ozet") or "") + " " + " ".join(o.get("maddeler") or [])
    if not metin.strip() or not ozet_modulu.hazir():
        return ""
    try:
        c = ozet_modulu._json_coz(ozet_modulu._sor(
            "Aşağıdaki toplantı özeti için dosya adı olarak kullanılacak 3-7 kelimelik, somut ve nesnel bir Türkçe başlık yaz. "
            "Konuyu anlatan tek bir ifade olsun (ör. 'Sosyal medya raporlarının yapay zekâyla hazırlanması'); virgülle ayrılmış "
            "kelime listesi, kişi adı, müşteri ya da şirket adı (ayrıca gösteriliyor), tırnak, nokta ve 'Toplantı' kelimesi olmasın." + _meet_ad_blogu()
            + " Yalnızca JSON: {\"baslik\": \"...\"}\n\n" + metin[:3000], json_bekle=True, num_ctx=4096, zaman_asimi=120))
        b = re.sub(r'[\\/:*?"<>|]+', " ", str(c.get("baslik") or "")).strip(" .")
        return b[:70]
    except Exception:  # noqa: BLE001
        return ""


def _meet_ad_blogu():
    """Kullanıcının toplantı adı düzeltmelerinden ve haftalık derslerden öğrenilenler (meet_gelisim.py)."""
    try:
        import meet_gelisim
        return meet_gelisim.ad_blogu()
    except Exception:  # noqa: BLE001
        return ""


def _meet_musteri_blogu():
    """Kullanıcının müşteri düzeltmelerinden ve haftalık derslerden öğrenilen kurallar (meet_gelisim.py)."""
    try:
        import meet_gelisim
        return meet_gelisim.musteri_blogu()
    except Exception:  # noqa: BLE001
        return ""


def _beni_bul(segmentler, etiket, mix_yolu, mik_yolu):
    """Mikrofon kanalının (kullanıcı) hangi konuşmacı kümesinde baskın olduğunu bulur. Döner: küme anahtarı ya da None."""
    import numpy as np
    from faster_whisper.audio import decode_audio
    mik = decode_audio(str(mik_yolu), sampling_rate=16000).astype(np.float32)
    mix = decode_audio(str(mix_yolu), sampling_rate=16000).astype(np.float32)
    n = min(len(mik), len(mix))
    if n < 16000 * 30:
        return None
    pay, sure = {}, {}
    for s in segmentler:
        a, b = int(s["bas"] * 16000), int(s["bit"] * 16000)
        if b > n or b - a < 16000 * 0.5:
            continue
        rm = float(np.sqrt(np.mean(mik[a:b] ** 2)) + 1e-6); rx = float(np.sqrt(np.mean(mix[a:b] ** 2)) + 1e-6)
        k = str(s["k"]); d = (b - a) / 16000
        pay[k] = pay.get(k, 0.0) + min(1.5, rm / rx) * d; sure[k] = sure.get(k, 0.0) + d
    oran = {k: pay[k] / sure[k] for k in pay if sure[k] >= 10}
    if not oran:
        return None
    sirali = sorted(oran.items(), key=lambda x: -x[1])
    en, deger = sirali[0]
    ikinci = sirali[1][1] if len(sirali) > 1 else 0.0
    # 23 Ekim: aynı odada mikrofona yakın ikinci biri olunca (21 Ekim: kullanıcı 1,12, yanındaki 0,89) 1,4 kat şartı kaçırıyordu; güçlü baskınlıkta 1,2 kat yeter
    return en if (deger >= 0.6 and deger >= 1.4 * max(ikinci, 0.05)) or (deger >= 0.9 and deger >= 1.2 * ikinci) else None


def _musteri_listesi(ay=None):
    """Müşteri adları: şirketlerin müşteri listeleri + eski düz liste; şirket adları müşteri sayılmaz (2026-10-27 ürün incelemesi: eski düz listede
    yalnız 5 ad ve şirketlerin kendisi vardı, gerçek 31 müşteri şirketlerin altındaydı; 12 toplantının 6'sı "Diğer"e ya da şirkete düşüyordu)."""
    ay = ay or ayarlar_oku()
    try:
        import sirketler
        S = sirketler.liste()
    except Exception:  # noqa: BLE001
        S = []
    sirket_adlari = {str(x.get("ad") or "").casefold() for x in S} | {str(x.get("kod") or "").casefold() for x in S}
    out = []
    for m in [m for x in S for m in (x.get("musteriler") or [])] + list(ay.get("musteriler") or []):
        if m and m.casefold() not in sirket_adlari and m.casefold() not in {o.casefold() for o in out}:
            out.append(m)
    return out


def _musteri_sec(veri, baslik_ipucu=""):
    """Müşteri/marka seçimi: önce katılımcı/konuşmacı adları (Ayarlar'daki 'Müşteri: kişi, kişi' eşlemesi),
    sonra adı metinde geçiyor mu, sonra model; emin değilse 'Diğer'."""
    ay = ayarlar_oku()
    liste = _musteri_listesi(ay)
    if not liste:
        return ""
    kisiler = ay.get("musteri_kisiler") or {}
    benim = (ay.get("benim_adim") or "").strip().lower()
    adlar = {str(a).strip().lower() for a in (veri.get("etiket") or {}).values() if not str(a).startswith("Konuşmacı ")}
    adlar |= {str(a).split(" (")[0].strip().lower() for a in (veri.get("katilimcilar") or [])}
    adlar.discard(benim)
    epostalar = {str(k.get("eposta") or "").lower() for k in (veri.get("takvim") or {}).get("katilimcilar", []) if isinstance(k, dict)}
    epostalar -= {e.lower() for e in (ay.get("benim_epostalar") or [])}
    alanlar = {e.split("@")[1] for e in epostalar if "@" in e} - {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com"}
    if alanlar and kisiler:
        for m, ks in kisiler.items():
            if any(k.lower().lstrip("@") in alanlar for k in ks if k.startswith("@")):
                return m
    if adlar and kisiler:
        esles = {m: len([k for k in ks if k.lower() in adlar or any(k.lower() in a for a in adlar)]) for m, ks in kisiler.items()}
        en = sorted(esles.items(), key=lambda x: -x[1])
        if en and en[0][1] > 0 and (len(en) == 1 or en[0][1] > en[1][1]):
            return en[0][0]
    metin = (baslik_ipucu + " " + (veri.get("baslik") or "") + " " + " ".join(veri.get("ozet", {}).get("maddeler", []) if veri.get("ozet") else [])).lower()
    try:
        js = KLASOR / f"{veri.get('_temel', '')}.json"
        if js.exists():
            d = json.loads(js.read_text(encoding="utf-8"))
            metin += " " + " ".join(sg["metin"] for sg in d["segmentler"]).lower()
    except Exception:  # noqa: BLE001
        pass
    sayac = {m: len(re.findall(r"(?<!\w)" + re.escape(m.lower()), metin)) for m in liste}   # "ING" "meeting"in içinde sayılıyordu
    en = sorted(sayac.items(), key=lambda x: -x[1])
    if not en or en[0][1] == 0:
        return "Diğer"                                   # adı hiç geçmeyen müşteriye model tahminle atamasın
    if len(en) == 1 or en[0][1] >= 2 * max(1, en[1][1]):
        return en[0][0]
    if not ozet_modulu.hazir() or not veri.get("ozet"):
        return en[0][0]
    try:
        o = veri["ozet"]
        c = ozet_modulu._json_coz(ozet_modulu._sor(
            "Aşağıdaki toplantı özeti şu müşteri/markalardan hangisine ait? Seçenekler: " + ", ".join(m for m, n in en if n > 0) +
            ". Hiçbiri belirgin değilse \"Diğer\" yaz. Yalnızca JSON: {\"musteri\": \"...\"}\n\n" +
            (o.get("ozet") or "") + "\n" + "\n".join(o.get("maddeler") or []), json_bekle=True, num_ctx=4096, zaman_asimi=120))
        m = str(c.get("musteri") or "").strip()
        return m if m in liste else "Diğer"
    except Exception:  # noqa: BLE001
        return "Diğer"


def _drive_klasor_yolu():
    """Drive senkron klasörü (Masaüstü/Drive gibi); yoksa None."""
    ay = ayarlar_oku()
    yol = Path(ay.get("drive_yol") or "").expanduser()
    return yol if yol.is_dir() else None


def _musteri_oner(veri, segmentler):
    """Müşteri bulunamayan toplantı için Claude'dan, toplantıda açıkça geçen ve üzerinde iş yapılan marka/şirket adı.
    Döner: {"ad", "guven", "kanit"} | None. (Toplantı bağlamında çağrılmalı: Claude toplantı iznine tabi.)"""
    import claude_yaz
    if not claude_yaz.hazir():
        return None
    o = veri.get("ozet") or {}
    metin = " ".join(s.get("metin", "") for s in segmentler)
    liste = ", ".join(_musteri_listesi()) or "(boş)"
    istem = (f"Bu, kullanıcının ({ayarlar_oku().get('benim_adim') or 'kullanıcı'}) katıldığı bir iş toplantısı. Mevcut müşteri listesi: {liste}.\n"
             "Toplantı hangi müşteri ya da marka için yapılmış? Yalnızca toplantıda adı AÇIKÇA geçen ve üzerinde iş yapılan şirket/marka adını ver. "
             "Kullanıcının kendi ajansı/şirketi, rakip markalar, örnek olarak anılan şirketler ve araçlar (Asana, Drive, Meet gibi) müşteri DEĞİLDİR. "
             "Mevcut listedekilerden biriyse aynen onu yaz. Emin değilsen 'musteri' boş kalsın. Adı doğru yazımıyla ver (listedeki gibi).\n"
             + _meet_musteri_blogu() +
             'Yalnızca JSON: {"musteri": "", "guven": 0.0, "kanit": "en çok 15 kelime: adın geçtiği yer"}\n\n'
             f"BAŞLIK: {veri.get('baslik') or ''}\nKATILIMCILAR: {', '.join(veri.get('katilimcilar') or [])}\nÖZET: {o.get('ozet', '')}\n"
             f"TRANSKRİPT:\n{metin[:40000]}")
    try:
        c = claude_yaz.sor_json(istem, zaman_asimi=300)
    except Exception:  # noqa: BLE001
        return None
    ad = re.sub(r'[\\/:*?"<>|]+', " ", str(c.get("musteri") or "")).strip()[:40]
    try:
        guven = float(c.get("guven") or 0)
    except (TypeError, ValueError):
        guven = 0.0
    if not ad or guven < 0.6 or ad.casefold() in ("diğer", "yok", "belirsiz"):
        return None
    return {"ad": ad, "guven": round(guven, 2), "kanit": str(c.get("kanit") or "").strip()[:240]}


def _musteri_tasi(temel, yeni):
    """Toplantıyı başka müşteriye taşır: veri, başlık, belgeler ve Drive klasörü."""
    js = KLASOR / f"{temel}.json"
    d = json.loads(js.read_text(encoding="utf-8")); veri = d["veri"]
    eski = veri.get("musteri") or "Diğer"
    veri["musteri"] = yeni; veri.pop("musteri_oneri", None)
    b = veri.get("baslik") or ""
    if eski != "Diğer" and b.endswith(f" · {eski}"):
        b = b[: -len(f" · {eski}")]
    if not b.endswith(f" · {yeni}"):
        b = f"{b} · {yeni}"
    veri["baslik"] = b
    with kilit:
        ciktilari_yaz(KLASOR / temel, veri, d["segmentler"])
        js.write_text(json.dumps({"veri": veri, "segmentler": d["segmentler"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        kok = _drive_klasor_yolu()
        if not kok:
            return
        ay = ayarlar_oku()
        musteri_kok = kok / _drive_ust({**veri, "musteri": yeni})
        eski_yol = Path(veri.get("drive") or "")
        if veri.get("drive") and eski_yol.is_dir() and eski_yol.parent != musteri_kok:
            hedef = musteri_kok / _guvenli_ad(eski_yol.name)
            musteri_kok.mkdir(parents=True, exist_ok=True)
            if not hedef.exists():
                shutil.move(str(eski_yol), str(hedef))
                try:
                    eski_yol.parent.rmdir()                   # boş kaldıysa eski müşteri klasörünü kaldır
                except OSError:
                    pass
            veri["drive"] = str(hedef)
        elif not (veri.get("drive") and eski_yol.is_dir()):  # Drive'a hiç düzgün yüklenmemişse şimdi yükle
            m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}\.\d{2}) · (.+?)(?: · [^·]+)?$", veri.get("baslik") or "")
            zaman, konu = (m.group(1), m.group(2)) if m else (time.strftime("%Y-%m-%d %H.%M", time.localtime(veri.get("olusturma") or time.time())), temel)
            alt, dosyalar = _drive_dosyalari(temel, veri, zaman, konu, yeni)
            hedef, hata = _drive_kopyala(dosyalar, alt)
            if not hata:
                veri["drive"] = str(hedef)
        if veri.get("drive") and Path(veri["drive"]).is_dir():      # belgeler yeni başlıkla
            for uz in ("docx", "txt"):
                if (KLASOR / f"{temel}.{uz}").exists():
                    _drive_kopya(KLASOR / f"{temel}.{uz}", Path(veri["drive"]) / f"{Path(veri['drive']).name}.{uz}")
    except Exception as e:  # noqa: BLE001
        print(f"Drive klasörü taşınamadı: {e}", flush=True)
    with kilit:
        d2 = json.loads(js.read_text(encoding="utf-8")); d2["veri"]["drive"] = veri.get("drive", "")
        js.write_text(json.dumps(d2, ensure_ascii=False, indent=1), encoding="utf-8")


@app.get("/api/musteri-onerileri")
def musteri_onerileri():
    """'Diğer'de kalan toplantılar için öneriler, ada göre gruplanmış (listede olan ve reddedilenler hariç)."""
    ay = ayarlar_oku()
    mevcut = {m.casefold().replace(" ", "") for m in _musteri_listesi(ay)}
    red = {m.casefold().replace(" ", "") for m in (ay.get("musteri_red") or [])}
    gruplar = {}
    for js in KLASOR.glob("transkript_*.json"):
        try:
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        o = v.get("musteri_oneri")
        if not v.get("toplanti") or (v.get("musteri") or "Diğer") != "Diğer" or not o:
            continue
        k = o["ad"].casefold().replace(" ", "")
        if k in mevcut or k in red:
            continue
        g = gruplar.setdefault(k, {"ad": o["ad"], "toplantilar": [], "kanit": o.get("kanit", "")})
        g["toplantilar"].append({"temel": js.stem, "baslik": v.get("baslik") or js.stem})
    return jsonify(sorted(gruplar.values(), key=lambda g: -len(g["toplantilar"])))


@app.post("/api/musteri-onerileri/tara")
def musteri_onerileri_tara():
    """'Diğer'de kalan ve taranmamış toplantıları Claude ile tarar (toplantı izni gerekir). Listede olan bir müşteri
    bulunursa toplantı doğrudan oraya taşınır; listede olmayan ad öneri olarak kalır (kullanıcı Ekle/Hayır der)."""
    import claude_yaz
    taranan, oneri, tasinan = 0, 0, []
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            return jsonify({"hata": "Claude bağlı değil ya da toplantılarda kapalı"}), 503
        for js in sorted(KLASOR.glob("transkript_*.json")):
            try:
                d = json.loads(js.read_text(encoding="utf-8")); v = d["veri"]
            except Exception:  # noqa: BLE001
                continue
            if not v.get("toplanti") or (v.get("musteri") or "Diğer") != "Diğer" or v.get("musteri_oneri") or v.get("musteri_tarandi"):
                continue
            taranan += 1
            o = _musteri_oner(v, d["segmentler"])
            mevcut = {m.casefold().replace(" ", ""): m for m in _musteri_listesi()}
            with kilit:
                d = json.loads(js.read_text(encoding="utf-8")); v = d["veri"]
                v["musteri_tarandi"] = time.time()
                if o and o["ad"].casefold().replace(" ", "") in mevcut and o["guven"] >= 0.7:
                    tasinan.append((js.stem, mevcut[o["ad"].casefold().replace(" ", "")]))
                elif o:
                    v["musteri_oneri"] = o; oneri += 1
                js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    for temel, ad in tasinan:
        _musteri_tasi(temel, ad)
    return jsonify({"taranan": taranan, "oneri": oneri, "tasinan": len(tasinan)})


@app.post("/api/musteri-oneri")
def musteri_oneri_karar():
    v = request.get_json(force=True) or {}
    ad = re.sub(r'[\\/:*?"<>|]+', " ", str(v.get("ad") or "")).strip()[:40]
    if not ad:
        return jsonify({"hata": "Ad yok"}), 400
    ay = ayarlar_oku(); k = ad.casefold().replace(" ", "")
    if not v.get("kabul"):
        ay["musteri_red"] = sorted(set((ay.get("musteri_red") or []) + [ad])); ayarlar_yaz(ay)
        return jsonify({"tamam": True})
    if k not in {m.casefold().replace(" ", "") for m in (ay.get("musteriler") or [])}:
        ay["musteriler"] = (ay.get("musteriler") or []) + [ad]; ayarlar_yaz(ay)
    tasinan = 0
    for js in KLASOR.glob("transkript_*.json"):
        try:
            veri = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        o = veri.get("musteri_oneri") or {}
        if veri.get("toplanti") and (veri.get("musteri") or "Diğer") == "Diğer" and o.get("ad", "").casefold().replace(" ", "") == k:
            _musteri_tasi(js.stem, ad); tasinan += 1
    return jsonify({"tamam": True, "tasinan": tasinan})


def _guvenli_ad(ad):
    """Klasör/dosya adı: '/' ve ':' klasörü bölüyordu ("Kurgu w/Mami" → iç içe iki klasör)."""
    return re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>]+', "-", str(ad))).strip(" .-")[:120]


def _drive_ust(veri, musteri=None):
    """Toplantının Drive'daki üst klasörü (2026-10-21, kullanıcı: şirketlere göre): <Toplantılar>/<Şirket>/<Müşteri> — müşteri yoksa ya da şirketin
    kendisiyse yalnız <Şirket>; şirket belirsizse eski düzen <Toplantılar>/<Müşteri|Diğer>."""
    ay = ayarlar_oku(); kok = ay.get("drive_klasor") or "Toplantılar"
    musteri = musteri if musteri is not None else (veri.get("musteri") or "")
    kod = veri.get("sirket") or ""
    if not kod:
        return f"{kok}/{_guvenli_ad(musteri or 'Diğer')}"
    try:
        import sirketler
        sad = next((x["ad"] for x in sirketler.liste() if x["kod"] == kod), "Genel")
    except Exception:  # noqa: BLE001
        sad = "Genel" if kod == "genel" else kod
    if not musteri or musteri == "Diğer" or musteri.casefold() == sad.casefold():
        return f"{kok}/{_guvenli_ad(sad)}"
    return f"{kok}/{_guvenli_ad(sad)}/{_guvenli_ad(musteri)}"


def _drive_yerlestir(temel):
    """Toplantının Drive klasörü olması gereken yerde değilse taşır (şirket/müşteri değişince ya da düzen değişince). Döner: yeni yol ya da None."""
    tj = KLASOR / f"{temel}.json"
    try:
        d = json.loads(tj.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    veri = d["veri"]; eski = Path(veri.get("drive") or "")
    kok = _drive_klasor_yolu()
    if not veri.get("drive") or not eski.is_dir() or not kok:
        return None
    hedef = kok / _drive_ust(veri) / eski.name
    if hedef == eski:
        return None
    if hedef.exists():
        return None
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(eski), str(hedef))
    ust = eski.parent                                      # boş kalan eski müşteri/şirket klasörlerini kaldır (Toplantılar köküne kadar)
    kok_t = kok / (ayarlar_oku().get("drive_klasor") or "Toplantılar")
    while ust != kok_t and ust.is_dir() and not any(p for p in ust.iterdir() if not p.name.startswith(".")):
        try:
            for p in ust.iterdir():
                p.unlink()
            ust.rmdir()
        except OSError:
            break
        ust = ust.parent
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); d["veri"]["drive"] = str(hedef)
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Drive: {eski.name} → {hedef.parent.relative_to(kok)}", flush=True)
    return str(hedef)


def _drive_dosyalari(temel, veri, zaman, konu, musteri, kayit_dosya=None):
    """Toplantının Drive alt klasörü ve kopyalanacak dosyalar [(yerel, ad)]."""
    ad = _guvenli_ad(f"{zaman} {konu}")
    alt = f"{_drive_ust(veri, musteri)}/{ad}"
    dosyalar = [(KLASOR / f"{temel}.docx", f"{ad}.docx"), (KLASOR / f"{temel}.txt", f"{ad}.txt")]
    if (KLASOR / f"{temel}.notlar.txt").exists():
        dosyalar.append((KLASOR / f"{temel}.notlar.txt", f"{ad} (notlar).txt"))
    kayit = kayit_dosya or veri.get("kayit")
    if kayit and Path(kayit).exists():
        dosyalar.append((Path(kayit), f"{ad} (kayıt).m4a"))
    return alt, dosyalar


def _drive_kopya(kaynak, hedef, deneme=6):
    """Drive klasörüne kopyalama; Drive uygulaması dosyayı eşitlerken kilitleyebiliyor ("Resource deadlock avoided"):
    birkaç kez bekleyip dener, olmazsa geçici adla yazıp yerine koyar. Döner: hata metni ya da ''."""
    son = ""
    for i in range(deneme):
        try:
            shutil.copy2(str(kaynak), str(hedef)); return ""
        except OSError as e:
            son = str(e)
            try:
                gecici = Path(str(hedef) + ".yeni")
                shutil.copy2(str(kaynak), str(gecici)); os.replace(gecici, hedef); return ""
            except OSError as e2:
                son = str(e2)
            time.sleep(2 + i * 2)
    return son


def _drive_kopyala(dosyalar, alt_klasor):
    """[(yerel, ad)] → Drive senkron klasörü altına kopyalar (Google Drive uygulaması buluta yükler). Döner: (hedef, hata)."""
    kok = _drive_klasor_yolu()
    if not kok:
        return None, "Drive klasörü bulunamadı"
    hedef = kok / alt_klasor
    try:
        hedef.mkdir(parents=True, exist_ok=True)
        hatalar = [h for yol, ad in dosyalar if Path(yol).exists() for h in [_drive_kopya(yol, hedef / ad)] if h]
        if hatalar:
            print(f"Drive kopyalama uyarısı: {hatalar[0]}", flush=True)
        return str(hedef), ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


_MEET_YOK = object()
MEET_KULLANICI_ALANI = ("etiket", "baslik", "musteri", "sirket")      # akış sürerken kullanıcı da değiştirdiyse onunki kalır


def _meet_kaydet(temel, veri, ilk, cikti=True):
    """Toplantı sonrası akışın dakikalarca tuttuğu `veri`yi yazar ama o arada başkalarının yazdıklarını EZMEZ (2026-10-25; eskiden bütün dosya bellekteki
    eski kopyayla yazılıyordu: ad değişikliği, paragraf konuşmacısı, metin düzeltmesi, çeviri kaybolabiliyordu). Kilit altında dosya yeniden okunur
    (kayit_json), yalnız bu akışın değiştirdiği alanlar yazılır; segmentler her zaman dosyadakidir. `veri` ve `ilk` yerinde güncellenir. Döner: segmentler."""
    import copy
    import kayit_json
    js = KLASOR / f"{temel}.json"

    def birlestir(d):
        f = d["veri"]
        for k in set(veri) | set(ilk):
            if veri.get(k, _MEET_YOK) == ilk.get(k, _MEET_YOK):
                continue                                               # bu akış değiştirmedi: dosyadaki kalır
            if k in MEET_KULLANICI_ALANI and f.get(k, _MEET_YOK) != ilk.get(k, _MEET_YOK):
                continue                                               # kullanıcı da değiştirdi: onunki
            if k in veri:
                f[k] = veri[k]
            else:
                f.pop(k, None)
    with kilit:
        d = kayit_json.guncelle(js, birlestir)
        veri.clear(); veri.update(d["veri"])
        ilk.clear(); ilk.update(copy.deepcopy(d["veri"]))
        if cikti:
            ciktilari_yaz(KLASOR / temel, veri, d["segmentler"])
    return d["segmentler"]


toplanti_bitiren = set()     # toplantı sonrası adımları süren işler (yeniden başlatma bunları beklemeli; 21 Ekim'de yarıda kesildi)


def _toplanti_bitir(is_):
    """Toplantı transkripti bitince: başlık ve müşteri belirle, belgeleri yenile, Drive klasörüne kopyala.
    Toplantı içeriği: Claude yalnızca Ayarlar'da 'Toplantılarda da Claude' açıksa kullanılır."""
    import claude_yaz
    toplanti_bitiren.add(is_.get("temel"))
    try:
        with claude_yaz.toplanti():
            sonuc = _toplanti_bitir_ic(is_)
        return sonuc
    finally:
        toplanti_bitiren.discard(is_.get("temel"))


def _yarim_toplantilari_bitir():
    """Açılışta: yazıya dökülmüş ama toplantı sonrası adımları (başlık, şirket, kısaca, danışman, sinyaller, Drive) yapılmamış toplantıları tamamlar."""
    time.sleep(20)
    for is_ in list(isler.values()):
        try:
            if not is_.get("toplanti") or is_.get("durum") != "bitti" or not is_.get("temel") or time.time() - (is_.get("olusturma") or 0) > 3 * 86400:
                continue
            js = KLASOR / f"{is_['temel']}.json"
            if not js.exists() or json.loads(js.read_text(encoding="utf-8"))["veri"].get("toplanti"):
                continue
            print(f"Yarım kalan toplantı sonrası adımlar tamamlanıyor: {is_['temel']}", flush=True)
            _toplanti_bitir(is_)
        except Exception as e:  # noqa: BLE001
            print(f"Yarım toplantı tamamlanamadı: {e}", flush=True)


def _toplanti_bitir_ic(is_):
    temel = is_["temel"]; js = KLASOR / f"{temel}.json"
    try:                                                               # 2026-10-25: toplantı altyazısı (uzantı) konuşmacıları ve metni düzeltir
        meet_altyazi_uygula(is_)
    except Exception as e:  # noqa: BLE001
        is_.setdefault("log", []).append(f"      Altyazı kullanılamadı: {str(e)[:120]}")
    d = json.loads(js.read_text(encoding="utf-8")); veri = d["veri"]
    import copy
    ilk = copy.deepcopy(veri)                                          # _meet_kaydet: yalnız bu akışın değiştirdikleri yazılır
    if is_.get("konusmaci_olaylari"):
        eslenen = _adlari_esle(d["segmentler"], veri["etiket"], is_["konusmaci_olaylari"], lambda m: is_["log"].append(m))
        for k, ad in eslenen.items():
            if str(veri["etiket"].get(k, "")).startswith("Konuşmacı "):
                veri["etiket"][k] = ad
        if eslenen:
            veri["adlar_kaynak"] = "toplantı"
            try:
                import sesler as sesler_modulu
                sesler_modulu.ogren(veri)
            except Exception:  # noqa: BLE001
                pass
    if is_.get("katilimcilar"):
        try:
            import kisiler as kisiler_modulu
            veri["katilimcilar"] = [a for a in is_["katilimcilar"] if kisiler_modulu.ad_mi(a)]   # Meet arayüz yazıları kişi değil
        except Exception:  # noqa: BLE001
            veri["katilimcilar"] = is_["katilimcilar"]
    # Kullanıcının kendi sesi: mikrofon kanalında baskın olan küme (ayarlar: "Adınız"). 2026-10-24: Kısaca'dan ÖNCE (eskiden sonra çalışıyordu;
    # "Kim ne yapacak" kullanıcıyı "Konuşmacı N" diye yazıyor, Sizden beklenenler ve Asana boş kalıyordu)
    benim_adim = (ayarlar_oku().get("benim_adim") or "").strip()
    try:                                                   # ilk ad yerine en çok doğrulanmış tam ad; iki profil oluşmasın
        import meet_gelisim
        benim_adim = meet_gelisim.ben_tam_ad() or benim_adim
    except Exception:  # noqa: BLE001
        pass
    ilk_ben = benim_adim.split(" ")[0].casefold()
    if benim_adim and is_.get("mik_dosya") and Path(is_["mik_dosya"]).exists() and not any(str(a).split(" ")[0].casefold() == ilk_ben for a in veri["etiket"].values()):
        try:
            k = _beni_bul(d["segmentler"], veri["etiket"], is_.get("kayit_dosya"), is_["mik_dosya"])
            if k is not None and str(veri["etiket"].get(k, "")).startswith("Konuşmacı "):
                veri["etiket"][k] = benim_adim; is_["log"].append(f"      Mikrofondan tanındı: {benim_adim}")
                try:
                    import sesler as sesler_modulu
                    sesler_modulu.ogren(veri)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            is_["log"].append(f"      Mikrofon eşlemesi yapılamadı ({e})")
    # Meet gelişimi (20_meet_gelisim.py): katılımcı listesiyle eleyerek ad, ekranda paylaşılanlar
    try:
        _meet_on_adim(is_, d, veri, temel)
    except Exception as e:  # noqa: BLE001
        is_["log"].append(f"      Meet ön adımı çalışmadı ({e})")
    # Kullanıcının toplantı sırasında aldığı notlar ve işaretlediği anlar (notlarim.py): kayıt aralığına düşenler, bağlamla zenginleştirilir
    try:
        import notlarim
        kb = float(is_.get("kayit_baslangic") or 0)
        if kb:
            nl = notlarim.aralik(kb, kb + float(veri.get("sure") or (d["segmentler"][-1]["bit"] if d["segmentler"] else 0)))
            if nl:
                veri["notlarim"] = notlarim.zenginlestir(veri, d["segmentler"], nl, log=lambda m: is_["log"].append(m))
    except Exception as e:  # noqa: BLE001
        is_["log"].append(f"      Notlarınız eklenemedi ({e})")
    # Toplantı kapısı (toplanti_kapisi.py): toplantıya benzemeyen kayıt listeye girmez, kullanıcıya sorulur; onaylarsa akış o zaman sürer
    if not veri.get("toplanti_onay") and ayarlar_oku().get("toplanti_kapisi", True):
        try:
            import toplanti_kapisi
            kp = toplanti_kapisi.degerlendir(veri, d["segmentler"], log=lambda m: is_["log"].append(m))
            veri["kapi"] = kp
            if toplanti_kapisi.sorulmali(kp):
                zaman0 = time.strftime("%Y-%m-%d %H.%M", time.localtime(is_.get("kayit_baslangic") or is_.get("olusturma") or time.time()))
                konu0 = _toplanti_adi_temizle(is_.get("toplanti_baslik") or "") or _toplanti_baslik(veri) or "Kayıt"
                veri.update({"baslik": f"{zaman0} · {konu0}", "toplanti": True, "kayit": is_.get("kayit_dosya") or "", "uygulama": is_.get("uygulama") or "",
                             "onay_bekliyor": {**kp, "zaman": time.time()},
                             "bekleyen_is": {k: is_.get(k) for k in ("kayit_dosya", "mik_dosya", "kayit_baslangic", "uygulama", "toplanti_baslik", "katilimcilar",
                                                                  "takvim", "musteri", "olusturma") if is_.get(k) is not None}})
                d["segmentler"] = _meet_kaydet(temel, veri, ilk)
                is_["baslik"] = veri["baslik"]; is_["drive"] = "onay bekliyor"; _kaydet()
                try:
                    _kayit_disi_ogren_kapi(is_.get("toplanti_baslik") or "", time.strftime("%Y-%m-%d", time.localtime(is_.get("kayit_baslangic") or time.time())))
                except Exception as e:  # noqa: BLE001
                    print(f"Kaydedilmeyen toplantı öğrenmesi: {e}", flush=True)
                _bildir("Bu bir toplantı mı?", (kp.get("neden") or "Toplantıya benzemiyor") + " · Meet'te onaylarsanız listeye eklenir", url=_meet_url(temel))
                return
        except Exception as e:  # noqa: BLE001
            is_["log"].append(f"      Toplantı kapısı çalışmadı ({e})")
    # Sayfanın en üstündeki kart: 1-2 paragraf özet + kişi kişi yapılacaklar (kisaca.py)
    try:
        import kisaca
        k = kisaca.uret(veri, d["segmentler"], log=lambda m: is_["log"].append(m))
        if k:
            veri["kisaca"] = k
    except Exception as e:  # noqa: BLE001
        is_["log"].append(f"      Kısa özet hazırlanamadı ({e})")
    if (veri.get("kisaca") or {}).get("kararlar"):          # kararlar önceki toplantılarınkine bağlanır (karar_zinciri.py)
        try:
            import karar_zinciri
            karar_zinciri.zincirle(veri, Path(js).stem, kilit=kilit, log=lambda m: is_["log"].append(m))
        except Exception as e:  # noqa: BLE001
            is_["log"].append(f"      Karar zinciri kurulamadı ({e})")
    # Toplantı sırasında verilen canlı kartlar (hatırlatma, öneri, mentör; canli_asistan.py) kayda geçer: danışman notu bunlara bakar (2026-10-23).
    try:
        kayit_yol = is_.get("kayit_dosya") or veri.get("kayit") or ""
        af = KAYIT / ".canli" / (Path(kayit_yol).stem + ".asistan.json") if kayit_yol else None
        if af and af.exists():
            veri["canli_kartlar"] = json.loads(af.read_text(encoding="utf-8")).get("kartlar", [])
    except Exception:  # noqa: BLE001
        pass
    # Kişisel kariyer danışmanı notu (danisman.py; opus). Word belgesinin ayrı sayfasına girer, belge Drive'a gider.
    if ayarlar_oku().get("danisman", True):
        try:
            import danisman
            is_["log"].append("      Kariyer danışmanı notu hazırlanıyor...")
            dn = danisman.uret(veri, d["segmentler"], log=lambda m: is_["log"].append(m))
            if dn:
                veri["danisman"] = dn
        except Exception as e:  # noqa: BLE001
            is_["log"].append(f"      Danışman notu hazırlanamadı ({e})")
    # Sinyaller: amaç tuttu mu, kapsam dışı istekler, önceki toplantılarla çelişkiler, kırılmalar, tahminler (sinyaller.py)
    try:
        import sinyaller
        sy = sinyaller.uret(veri, d["segmentler"], temel, log=lambda m: is_["log"].append(m))
        if sy:
            veri["sinyaller"] = sy
            if sy.get("amac"):
                veri["amac"] = sy["amac"]
    except Exception as e:  # noqa: BLE001
        is_["log"].append(f"      Sinyaller çıkarılamadı ({e})")
    if is_.get("takvim"):
        veri["takvim"] = is_["takvim"]
    zaman = time.strftime("%Y-%m-%d %H.%M", time.localtime(is_.get("kayit_baslangic") or is_.get("olusturma") or time.time()))
    # Toplantı adı: 1) toplantı sırasında ekranda yazan ad (takvim / uzantı sekme başlığı / pencere başlığı), 2) özetten konu,
    # 3) en son çare katılımcı adları. Kullanıcı: "toplantı adını varsayma, oradan al"; 22 Ekim: ad "Şirket · Müşteri · Konu" biçiminde
    # görünür, katılımcılar ayrı satırda; bu yüzden ad kişi listesi olmamalı.
    konu = _toplanti_adi_temizle(is_.get("toplanti_baslik") or "")
    if not konu:
        konu = _toplanti_baslik(veri); veri["baslik_kaynak"] = "tahmin"
        if not konu:
            kisiler = [a for a in (veri.get("katilimcilar") or []) if a and a.strip().lower() != (ayarlar_oku().get("benim_adim") or "").strip().lower()]
            if not kisiler:
                kisiler = [a for a in veri.get("etiket", {}).values() if not str(a).startswith("Konuşmacı ")]
            konu = ("Görüşme · " + ", ".join(kisiler[:3])) if kisiler else "Toplantı"
            veri["baslik_kaynak"] = "katılımcılar" if kisiler else "tahmin"
    else:
        veri["baslik_kaynak"] = "toplantı"
    veri["_temel"] = temel
    musteri = (is_.get("musteri") or "").strip() or _musteri_sec(veri, konu)
    try:
        import sirketler
        musteri = sirketler.ana_marka(musteri)                 # seri adı ayrı müşteri değil, ana marka (ayarlar alt_isler)
    except Exception:  # noqa: BLE001
        pass
    veri.pop("_temel", None)
    baslik = f"{zaman} · {konu}" + (f" · {musteri}" if musteri and musteri != "Diğer" else "")
    veri["baslik"] = baslik; veri["toplanti"] = True; veri["kayit"] = is_.get("kayit_dosya") or ""; veri["musteri"] = musteri
    veri["uygulama"] = is_.get("uygulama") or ""
    if musteri == "Diğer" and not (is_.get("musteri") or "").strip():
        try:
            oneri = _musteri_oner(veri, d["segmentler"])
            if oneri:
                mevcut = {m.casefold().replace(" ", ""): m for m in _musteri_listesi()}
                anahtar = oneri["ad"].casefold().replace(" ", "")
                if anahtar in mevcut and oneri["guven"] >= 0.7:          # listedeki bir müşteri: doğrudan oraya
                    musteri = mevcut[anahtar]; veri["musteri"] = musteri
                    baslik = f"{zaman} · {konu} · {musteri}"; veri["baslik"] = baslik
                    is_["log"].append(f"      Müşteri (Claude): {musteri}")
                elif anahtar not in mevcut:
                    veri["musteri_oneri"] = oneri
                    is_["log"].append(f"      Müşteri önerisi: {oneri['ad']} ({oneri['kanit'][:80]})")
        except Exception as e:  # noqa: BLE001
            is_["log"].append(f"      Müşteri önerisi alınamadı ({e})")
    # Şirket (ayarlardaki şirketler / Genel): kurallar, olmazsa Claude; güvenliyse kişiler öğrenilir (sirketler.py)
    try:
        import sirketler
        sr = sirketler.sec(veri, d["segmentler"], log=lambda m: is_["log"].append(m))
        veri["sirket"] = sr["kod"]; veri["sirket_neden"] = sr.get("neden", "")
        if musteri == "Diğer" and sr.get("musteri"):
            veri["musteri_tahmin"] = sr["musteri"]
            altlar = {m.casefold(): m for x in sirketler.liste() if x.get("kod") == sr["kod"] for m in x.get("musteriler") or []}
            if sr["musteri"].casefold() in altlar:          # şirketin tanımlı alt markası: müşteri o marka
                musteri = altlar[sr["musteri"].casefold()]; veri["musteri"] = musteri
                baslik = f"{zaman} · {konu} · {musteri}"; veri["baslik"] = baslik
                is_["log"].append(f"      Müşteri (şirketin markası): {musteri}")
        sirketler.ogren(sr["kod"], veri)
        is_["log"].append(f"      Şirket: {sr['kod']} ({sr.get('neden', '')[:80]})")
    except Exception as e:  # noqa: BLE001
        is_["log"].append(f"      Şirket belirlenemedi ({e})")
    d["segmentler"] = _meet_kaydet(temel, veri, ilk)
    baslik = veri.get("baslik") or baslik; musteri = veri.get("musteri") or musteri    # kullanıcı bu arada değiştirdiyse onunki
    is_["baslik"] = baslik; is_["musteri"] = musteri
    ay = ayarlar_oku()
    # Bağlamı yüksek toplantı notları + e-posta (kullanıcının toplantıya girdiği adrese)
    try:
        import notlar as notlar_modulu
        is_["log"].append("      Toplantı notları hazırlanıyor...")
        n = notlar_modulu.uret(veri, d["segmentler"], temel, log=lambda m: is_["log"].append(m))
        if n:
            veri["notlar"] = n
            (KLASOR / f"{temel}.notlar.txt").write_text(notlar_modulu.metin(veri, n), encoding="utf-8")
            if ay.get("notlar_gonder", True) and not is_.get("notlar_gonderildi"):   # birleşik toplantıda ilk parçadan gitmişse yeniden gönderilmez
                alici = notlar_modulu.alici_sec(veri, ay)
                hata = notlar_modulu.gonder(f"Toplantı notları · {baslik}", notlar_modulu.metin(veri, n), alici, alici) if alici else "alıcı adresi yok"
                veri["notlar_gonderim"] = {"alici": alici, "zaman": time.time(), "hata": hata}
                is_["log"].append(f"      Notlar e-postayla gönderildi: {alici}" if not hata else f"      Notlar gönderilemedi: {hata}")
        else:
            is_["log"].append("      Toplantı notları üretilemedi.")
    except Exception as e:  # noqa: BLE001
        is_["log"].append(f"      Toplantı notları hatası: {e}")
    _gorev_ve_sesli(temel, veri, log=lambda m: is_["log"].append(m))
    d["segmentler"] = _meet_kaydet(temel, veri, ilk, cikti=False)
    if not ay.get("drive", True):
        is_["drive"] = "kapalı"
        _bildir("Toplantı notları hazır", f"{musteri} · {konu}" if musteri and musteri != "Diğer" else konu, url=_meet_url(temel))
        return
    is_["drive"] = "yükleniyor"; _kaydet()
    alt, dosyalar = _drive_dosyalari(temel, veri, zaman, konu, musteri, is_.get("kayit_dosya"))
    hedef, hata = _drive_kopyala(dosyalar, alt)
    if hata and _drive_bagli():                        # klasör yoksa rclone yedeği
        hata = _drive_yukle(dosyalar, alt); hedef = alt
    is_["drive"] = f"hata: {hata}" if hata else "yüklendi"
    veri["drive"] = "" if hata else str(hedef)
    _meet_kaydet(temel, veri, ilk, cikti=False)
    _kaydet()
    _bildir("Toplantı notları hazır" if not hata else "Drive'a eklenemedi", (f"{musteri} · {konu}" if musteri and musteri != "Diğer" else konu) + (" · Drive'a da eklendi" if not hata else ""), url=_meet_url(temel))


def _drive_cope(klasor):
    """Drive klasörünü eşitlenen alandan çıkarır (Google Drive kendi çöpüne alır, 30 gün geri alınabilir). Önce Mac Çöp'ü;
    launchd altında ~/.Trash'e yazma izni olmayabiliyor (21 Ekim IK 18 klasörü yerinde kalmıştı) → .cop/drive__<ad>."""
    # 2026-10-24: .cop'a taşınan klasörü Google Drive geri getiriyordu (launchd altındaki site Drive'dan silemiyor); Finder ile Çöp'e atmak kalıcı
    try:
        yedek = COP / f"drive__{klasor.name} {time.strftime('%H%M%S')}"
        shutil.copytree(str(klasor), str(yedek))
        q = str(klasor).replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["/usr/bin/osascript", "-e", f'tell application "Finder" to delete (POSIX file "{q}" as alias)'], capture_output=True, timeout=30)
        if not klasor.exists():
            return True
        shutil.rmtree(yedek, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    son_hata = ""
    for hedef in (Path.home() / ".Trash" / f"{klasor.name} {time.strftime('%H%M%S')}", COP / f"drive__{klasor.name} {time.strftime('%H%M%S')}"):
        try:
            hedef.parent.mkdir(exist_ok=True)
            shutil.move(str(klasor), str(hedef))
            return True
        except Exception as e:  # noqa: BLE001
            son_hata = str(e)[:160]
            continue
    print(f"Drive klasörü kaldırılamadı: {klasor} ({son_hata})", flush=True)      # 2026-10-27: sessizce yerinde kalıyordu
    try:                                                     # Meet durumunda görünsün; kullanıcı Finder'dan Çöp'e atabilir
        import meet_gelisim
        meet_gelisim.olay("uyari", f"Eski Drive klasörü kaldırılamadı: {klasor.name}", "")
    except Exception:  # noqa: BLE001
        pass
    return False


ASANA_CL_WS = ""      # ajansın Asana çalışma alanı: ayarlar.json `asana_ws` (kodda kimlik yok, 2026-10-25)


def _asana_projeler():
    """Çalışma alanındaki projeler {ad: gid} (gün boyu önbellek)."""
    if asana_onbellek.get("proje_zaman", 0) > time.time() - 86400:
        return asana_onbellek.get("projeler") or {}
    ben = _asana_ben()
    L = _asana(f"/workspaces/{ben['alan']['gid']}/projects?archived=false&limit=100&opt_fields=name") or []
    asana_onbellek.update({"proje_zaman": time.time(), "projeler": {p["name"]: p["gid"] for p in L}})
    return asana_onbellek["projeler"]


def _asana_proje_bul(veri):
    """Toplantının müşterisine (yoksa şirketine) karşılık gelen Asana projesi: ad karşılaştırması harf/boşluk/büyük-küçük farkını yok sayar."""
    norm = lambda x: re.sub(r"[^a-z0-9]", "", str(x).casefold().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c"))   # noqa: E731
    adaylar = [veri.get("musteri"), veri.get("musteri_tahmin")]
    P = {norm(ad): gid for ad, gid in _asana_projeler().items()}
    for a in adaylar:
        if a and a != "Diğer" and norm(a) in P:
            return P[norm(a)]
    return None


def _marka_adlari():
    """Bütün şirket, müşteri (marka) ve anahtar adları: ajans dışı işlerden ayıklanır."""
    ay = ayarlar_oku(); out = set()
    for sk in ay.get("sirketler") or []:
        if isinstance(sk, dict):
            out |= {sk.get("ad") or ""} | set(sk.get("musteriler") or []) | set(sk.get("anahtar") or [])
    out |= set(ay.get("musteriler") or [])
    try:                                                   # ürün ve alt marka adları da markayı ele verir (Stelatopia, VBC, Phytocyane...)
        mk = json.loads((KLASOR / "atolye" / "markalar.json").read_text(encoding="utf-8")).get("markalar") or {}
        for v in mk.values():
            out.add(v.get("ad") or "")
            for u in v.get("urunler") or []:
                ad = str(u.get("ad") if isinstance(u, dict) else u or "")
                out |= {ad} | {p.strip() for p in re.split(r"[/(),]| ve ", ad) if len(p.strip()) >= 3}
    except Exception:  # noqa: BLE001
        pass
    return sorted({x.strip() for x in out if x and len(x.strip()) >= 3}, key=len, reverse=True)


def _markasiz(isler):
    """Ajans dışı toplantının işlerinde ajans ve marka adlarını çıkarır (kullanıcı, 23 Ekim: "ajansın Asana'sı o; diğer işleri eklerken ajans
    veya marka ismi verme"). Cümle bozulmasın diye Claude yeniden yazar (toplantı izniyle); olmazsa adlar ve ekleri kodla silinir. Döner: [yeni ad]."""
    adlar = _marka_adlari()
    desen = re.compile(r"\b(" + "|".join(re.escape(a) for a in adlar) + r")(?:[’'][a-zçğıöşü]+)?\b", re.I) if adlar else None
    if not desen or not any(desen.search(x) for x in isler):
        return list(isler)
    try:
        import claude_yaz
        with claude_yaz.toplanti():
            if claude_yaz.hazir():
                c = claude_yaz.sor_json("Aşağıdaki iş maddelerini, içlerindeki şirket, ajans, marka, alt marka ve ürün adlarını ÇIKARARAK yeniden yaz. Anlam ve iş aynı kalsın, cümle "
                                        "doğal Türkçe olsun; ad yerine genel ifade kullan ('sunuma', 'müşteriye', 'kampanya için'). Kişi adları kalabilir.\n"
                                        f"ÇIKARILACAK ADLAR: {', '.join(adlar)}\n"
                                        'JSON: {"isler": ["...", "..."]} (aynı sırayla, aynı sayıda)\n\n' + "\n".join(f"{n + 1}. {x}" for n, x in enumerate(isler)),
                                        model_adi="sonnet", zaman_asimi=120)
                L = [str(x).strip() for x in c.get("isler") or []]
                if len(L) == len(isler) and all(L) and not any(desen.search(x) for x in L):
                    return L
    except Exception:  # noqa: BLE001
        pass
    return [re.sub(r"\s{2,}", " ", desen.sub("", x)).strip(" ,.-") for x in isler]


def _asana_acik_gorevler(alan_gid):
    """Kullanıcının bu çalışma alanındaki açık görev adları (mükerrer görev açılmasın): {normalize ad: (gid, url)}."""
    try:
        r = _asana(f"/tasks?assignee=me&workspace={alan_gid}&completed_since=now&opt_fields=name,permalink_url&limit=100")
    except Exception:  # noqa: BLE001
        return {}
    L = r if isinstance(r, list) else (r.get("data") if isinstance(r, dict) else []) or []
    return {re.sub(r"\W+", " ", str(t.get("name") or "").casefold()).strip(): (t.get("gid"), t.get("permalink_url") or "") for t in L if t.get("name")}


def _asana_ekle(maddeler, veri, konu="", temel=""):
    """gorevler.ata için: işleri ajansın Asana'sında kullanıcıya atanmış görev olarak açar. Ajans toplantısı: müşteri projesi ve toplantı adı.
    Başka şirket/kişisel toplantı (23 Ekim): ajans ve marka adı yok (`_markasiz`), notta yalnız tarih, proje yok. Aynı adlı açık görev varsa yenisi açılmaz.
    Döner: {iş: {gid, url, proje}}."""
    import difflib
    ben = _asana_ben()
    if not ben.get("alan"):
        raise RuntimeError("Asana çalışma alanı bulunamadı")
    cl = (veri.get("sirket") or "") in {s.get("kod") for s in (ayarlar_oku().get("sirketler") or []) if isinstance(s, dict) and s.get("asana")}   # Asana'nın sahibi ajans (ayar `asana: true`)
    proje = _asana_proje_bul(veri) if cl else None
    adlar = [m["is"] for m in maddeler] if cl else _markasiz([m["is"] for m in maddeler])
    acik = _asana_acik_gorevler(ben["alan"]["gid"])
    tarih = (str(veri.get("baslik") or "")[:10]) or time.strftime("%Y-%m-%d")
    out = {}
    for m, ad in zip(maddeler, adlar):
        anahtar = re.sub(r"\W+", " ", ad.casefold()).strip()
        es = next((v for k, v in acik.items() if difflib.SequenceMatcher(None, k, anahtar).ratio() >= 0.88), None)
        if es:                                             # aynı iş zaten açık: yeni görev yok
            out[m["is"]] = {"gid": es[0], "url": es[1], "proje": False, "zaten_vardi": True}
            continue
        is_proje = (_asana_proje_bul({"musteri": m["musteri"]}) or proje) if cl and m.get("musteri") else proje   # çok müşterili toplantı: işin kendi müşterisi
        notlar = (f"Toplantı: {konu or veri.get('baslik') or ''}" if cl else f"Toplantı notu, {tarih}") \
            + (f"\nMüşteri: {m['musteri']}" if cl and m.get("musteri") else "") \
            + (f"\nNe zaman: {m['ne_zaman']}" if m.get("ne_zaman") and cl else "") + (f"\nMeet: http://127.0.0.1:8766/#t={temel}" if temel else "")
        govde = {"name": ad[:250], "assignee": "me", "workspace": ben["alan"]["gid"], "notes": notlar}
        if m.get("son"):
            govde["due_on"] = m["son"]
        if is_proje:
            govde["projects"] = [is_proje]
        g = _asana("/tasks", "POST", govde)
        out[m["is"]] = {"gid": g.get("gid"), "url": g.get("permalink_url") or "", "proje": bool(is_proje), "ad": ad, **({"musteri": m["musteri"]} if m.get("musteri") else {})}
        acik[anahtar] = (g.get("gid"), g.get("permalink_url") or "")
    return out


def _asana_bekleyenleri_gonder():
    """Asana bağlanınca: son 30 günün bekleyen işlerini (gorev_atama._bekliyor) ekler."""
    import gorevler
    for js in sorted(KLASOR.glob("transkript_*.json"), key=lambda p: p.stat().st_mtime):
        try:
            d = json.loads(js.read_text(encoding="utf-8")); veri = d["veri"]
        except Exception:  # noqa: BLE001
            continue
        if not (veri.get("gorev_atama") or {}).get("_bekliyor") or time.time() - js.stat().st_mtime > 30 * 86400:
            continue
        try:
            gorevler.ata(veri, js.stem, asana_ekle=lambda m, k, t, v=veri: _asana_ekle(m, v, k, t), log=lambda x: print(x, flush=True))
        except Exception as e:  # noqa: BLE001
            print(f"Bekleyen işler Asana'ya eklenemedi: {e}", flush=True); return
        with kilit:
            d2 = json.loads(js.read_text(encoding="utf-8")); d2["veri"]["gorev_atama"] = veri.get("gorev_atama"); js.write_text(json.dumps(d2, ensure_ascii=False, indent=1), encoding="utf-8")


def _gorev_ve_sesli(temel, veri, log=print, gorev=True, sesli=True):
    """Toplantı sonrası: kullanıcının işleri görev olarak (Asana bağlıysa orada, değilse Anımsatıcılar) + sesli özet (macOS Yelda)."""
    if gorev:
        try:
            import gorevler
            asana = (lambda m, k, t: _asana_ekle(m, veri, k, t)) if ayarlar_oku().get("asana_token") else None
            gorevler.ata(veri, temel, asana_ekle=asana, log=log)
        except Exception as e:  # noqa: BLE001
            log(f"      Görevler atanamadı ({e})")
    if not sesli:
        return
    try:
        import sesli_ozet
        yol, sn = sesli_ozet.uret(temel, veri)
        if yol:
            veri["sesli_ozet"] = {"dosya": yol.name, "sn": sn, "zaman": time.time()}
            log(f"      Sesli özet hazır ({sn} sn)")
    except Exception as e:  # noqa: BLE001
        log(f"      Sesli özet hazırlanamadı ({e})")


@app.get("/api/onay-bekleyen")
def onay_bekleyen():
    """Toplantıya benzemediği için listeye alınmayan, kullanıcının onayını bekleyen kayıtlar."""
    out = []
    for js in sorted(KLASOR.glob("transkript_*.json"), key=lambda p: -p.stat().st_mtime)[:200]:
        v = _oku_veri(js)
        if v.get("onay_bekliyor"):
            out.append({"temel": js.stem, "baslik": v.get("baslik") or js.stem, "neden": v["onay_bekliyor"].get("neden") or "", "tur": v["onay_bekliyor"].get("tur") or "",
                        "sure": v.get("sure") or 0, "kisa": ((v.get("ozet") or {}).get("ozet") if isinstance(v.get("ozet"), dict) else "") or "", "drive": bool(v.get("drive"))})
    return jsonify(out)


@app.post("/api/toplanti/<temel>/onay")
def toplanti_onay(temel):
    """{kabul: true} → toplantı akışı şimdi çalışır (şirket, Kısaca, danışman, notlar, görevler, Drive). {kabul: false} → kayıt kaldırılır
    (Geri al ile 1 gün içinde dönebilir); daha önce Drive'a gittiyse oradaki klasör Çöp'e."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    kabul = bool((request.get_json(silent=True) or {}).get("kabul"))
    with kilit:
        d = json.loads(tj.read_text(encoding="utf-8")); veri = d["veri"]
        bekleyen = veri.get("bekleyen_is") or {}
        if kabul:
            veri.pop("bekleyen_is", None); veri.pop("onay_bekliyor", None); veri["toplanti_onay"] = True
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if not kabul:
        eski = Path(veri.get("drive") or "")
        if veri.get("drive") and eski.is_dir():
            _drive_cope(eski)
        sil(temel)
        # Toplantı değil dediği kaydın adı (ör. her hafta tekrar eden kurs) bir daha kaydedilmez (30); Geri al bunu da geri alır
        import kayit_disi as _kd
        ad = _kd.imza(bekleyen.get("toplanti_baslik") or "") or _kd.imza(veri.get("baslik") or "")
        if ad and ad.lower() != "kayıt" and _kayit_disi_ekle(ad, "Toplantı değil dediğiniz kayıt"):
            return jsonify({"tamam": True, "kaldirildi": True, "kayit_disi": ad})
        return jsonify({"tamam": True, "kaldirildi": True})
    if veri.get("kisaca") and veri.get("sirket"):          # geriye dönük taramada işaretlenmişti; akış zaten çalışmış
        return jsonify({"tamam": True})
    is_ = {**bekleyen, "temel": temel, "log": [], "id": "onay_" + temel}

    def _calis():
        try:
            _toplanti_bitir(is_)
        except Exception as e:  # noqa: BLE001
            print(f"onaylı toplantı akışı hatası: {e}", flush=True)
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True, "isleniyor": True})


@app.post("/api/toplanti-kapisi/tara")
def toplanti_kapisi_tara():
    """Son 14 günün toplantılarını kapıdan geçirir (geriye dönük); toplantıya benzemeyenler onay bekleyen olur. Drive'a dokunmaz."""
    import toplanti_kapisi

    def _calis():
        for js in sorted(KLASOR.glob("transkript_*.json"), key=lambda p: -p.stat().st_mtime):
            try:
                d = json.loads(js.read_text(encoding="utf-8")); v = d["veri"]
            except Exception:  # noqa: BLE001
                continue
            if not v.get("toplanti") or v.get("kapi") or v.get("toplanti_onay") or time.time() - (v.get("olusturma") or 0) > 14 * 86400:
                continue
            kp = toplanti_kapisi.degerlendir(v, d["segmentler"])
            with kilit:
                d = json.loads(js.read_text(encoding="utf-8")); d["veri"]["kapi"] = kp
                if toplanti_kapisi.sorulmali(kp):
                    d["veri"]["onay_bekliyor"] = {**kp, "zaman": time.time()}
                js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    threading.Thread(target=_calis, daemon=True).start()
    return jsonify({"tamam": True})


@app.post("/api/gorevler/<temel>")
@app.post("/api/sesli-ozet/<temel>")
def gorevler_ata(temel):
    """/api/gorevler: kullanıcının işlerini görev olarak ekler; /api/sesli-ozet: yalnızca sesli özeti hazırlar (eski toplantılar için)."""
    tj = _temel_dogrula(temel).with_suffix(".json")
    d = json.loads(tj.read_text(encoding="utf-8")); veri = d["veri"]; log = []
    sesli = request.path.startswith("/api/sesli-ozet")
    _gorev_ve_sesli(temel, veri, log=log.append, gorev=not sesli, sesli=sesli)
    with kilit:
        d2 = json.loads(tj.read_text(encoding="utf-8"))
        for k in ("gorev_atama", "sesli_ozet"):
            if k in veri:
                d2["veri"][k] = veri[k]
        tj.write_text(json.dumps(d2, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify({"gorev_atama": veri.get("gorev_atama") or {}, "sesli_ozet": veri.get("sesli_ozet"), "log": log})


@app.get("/sesli-ozet/<temel>.m4a")
def sesli_ozet_dosya(temel):
    f = _temel_dogrula(temel).with_suffix(".ozet.m4a")
    if not f.exists():
        abort(404)
    from flask import send_file
    return send_file(f, mimetype="audio/mp4", conditional=True)


@app.post("/api/kayit/dosya")
def kayit_dosya():
    """Arka plandaki kaydedici bitmiş bir toplantı kaydını bildirir; transkript işi başlar."""
    v = request.get_json(force=True) or {}
    yol = Path(str(v.get("dosya") or ""))
    if not yol.is_file() or not str(yol).startswith(str(KAYIT) + "/"):
        return jsonify({"hata": "Dosya bulunamadı."}), 400
    bas = float(v.get("baslangic") or time.time()); bit = time.time()
    sure = _kayit_suresi(yol)
    if 0 < sure < bit - bas + 600:
        bit = bas + sure                                      # gerçek bitiş (bildirim, parçalar birleşince ~1 dk sonra gelir)
    taze = time.time() - uzanti_durum.get("zaman", 0) < 15 * 60
    takvim_e = None
    try:
        import takvim as takvim_modulu
        takvim_e = takvim_modulu.etkinlik_bul(bas, bit)
    except Exception as e:  # noqa: BLE001
        print(f"takvim hatası: {e}", flush=True)
    baslik_u = _toplanti_adi_temizle((takvim_e or {}).get("ad") or "") or (_toplanti_adi_temizle(uzanti_durum.get("baslik", "")) if taze else "")
    if not baslik_u:
        baslik_u = _pencere_toplanti_adi(v.get("pencere"), v.get("uygulama"))   # masaüstü Teams: pencere başlığı (yalnız toplantı penceresi)
    kd = _kayit_disi_eslesen(v.get("pencere"), uzanti_durum.get("baslik", "") if taze else "", (takvim_e or {}).get("ad"), baslik_u)
    if kd:                                                    # kaydedilmeyen toplantı (30): her hafta tekrar eden kurs vb.; yazıya dökülmez
        _kayit_disi_at(yol, v.get("mik_dosya"))
        print(f"Kaydedilmeyen toplantı, kayıt atıldı: {kd.get('ad')}", flush=True)
        return jsonify({"kayit_disi": kd.get("ad")})
    katilim = (uzanti_durum.get("katilimcilar", []) if taze else []) or [k["ad"] for k in (takvim_e or {}).get("katilimcilar", []) if k.get("ad")]
    if meet_devam_mi(yol, bas, bit, str(v.get("mik_dosya") or ""), baslik_u, str(v.get("uygulama") or ""), katilim, takvim_e):   # bağlantı kopup gelmiş (28)
        return jsonify({"birlesti": True})
    r = _baslat({"link": str(yol), "ozet": True, "konusmaci": True, "altyazi": False, "toplanti": True,
                 "toplanti_baslik": baslik_u,
                 "kayit_dosya": str(yol), "mik_dosya": str(v.get("mik_dosya") or ""), "uygulama": str(v.get("uygulama") or ""), "kayit_baslangic": bas,
                 "katilimcilar": (uzanti_durum.get("katilimcilar", []) if taze else []) or [k["ad"] for k in (takvim_e or {}).get("katilimcilar", []) if k.get("ad")],
                 "takvim": takvim_e or None, "konusmaci_olaylari": _uzanti_olaylari(bas, bit), "altyazi_dosya": meet_altyazi_dosyasi(yol, bas, bit)})
    j = r.get_json() if hasattr(r, "get_json") else {}
    if (j or {}).get("id") in isler:
        isler[j["id"]]["kayit_bitis"] = bit                   # devam kaydı gelirse aradaki süre buna göre ölçülür
    _bildir("Toplantı kaydedildi", "Yazıya dökülüyor; bitince Drive'a eklenecek")
    return jsonify({"id": (j or {}).get("id")})


@app.post("/api/kayit/yukle")
def kayit_yukle():
    """Telefondan ya da dosyadan toplantı kaydı (2026-10-21): iPhone Sesli Notlar / herhangi bir ses dosyası → toplantı akışı (konuşmacılar,
    Kısaca, danışman, Drive). Çok parçalı form (`dosya`, isteğe bağlı `baslik`, `zaman` = kaydın başladığı an, saniye) ya da ham gövde
    (iPhone Kısayolu "Dosya" gövdesi; ad `?ad=`). Kaydın saati: `zaman` > dosyanın içindeki oluşturma zamanı > şimdi − süre."""
    f = request.files.get("dosya")
    ad = (f.filename if f and f.filename else request.args.get("ad") or "Sesli not.m4a")
    ad = re.sub(r"[^\w.\- ]+", "_", Path(ad).name)[:100]
    if not re.search(r"\.(m4a|mp3|wav|aac|caf|amr|3gp|ogg|opus|webm|flac|aiff?|mp4|mov|qta)$", ad, re.I):
        ad += ".m4a"
    KAYIT.mkdir(exist_ok=True)
    gecici = KAYIT / f".yukleme_{uuid.uuid4().hex[:6]}_{ad}"
    if f:
        f.save(str(gecici))
    else:
        veri = request.get_data()
        if not veri:
            return jsonify({"hata": "Dosya gelmedi."}), 400
        gecici.write_bytes(veri)
    try:
        bilgi = json.loads(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=creation_time",
                                           "-of", "json", str(gecici)], capture_output=True, text=True, timeout=60).stdout or "{}")
        sure = float((bilgi.get("format") or {}).get("duration") or 0)
        ct = ((bilgi.get("format") or {}).get("tags") or {}).get("creation_time")
    except Exception:  # noqa: BLE001
        sure, ct = 0.0, None
    if sure < 20:
        gecici.unlink(missing_ok=True)
        return jsonify({"hata": "Kayıt çok kısa ya da okunamadı."}), 400
    bas = None
    try:
        bas = float(request.values.get("zaman")) if request.values.get("zaman") else None
    except ValueError:
        bas = None
    if bas is None and ct:
        try:
            bas = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00")).timestamp()
        except ValueError:
            bas = None
    if bas is None and request.values.get("zaman_ipucu"):            # tarayıcıdan: dosyanın son değiştirilme anı ≈ kaydın bitişi
        try:
            bas = float(request.values.get("zaman_ipucu")) - sure
        except ValueError:
            bas = None
    if bas is None or bas > time.time() + 60:
        bas = time.time() - sure
    baslik = re.sub(r"[/\\:]+", " ", str(request.values.get("baslik") or "")).strip()[:80]
    zaman = time.strftime("%Y-%m-%d %H.%M", time.localtime(bas))
    hedef = KAYIT / (f"Toplantı {zaman}" + (f" · {baslik}" if baslik else "") + ".m4a")
    n = 2
    while hedef.exists():
        hedef = KAYIT / (f"Toplantı {zaman} ({n})" + (f" · {baslik}" if baslik else "") + ".m4a"); n += 1
    p = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-i", str(gecici), "-vn", "-c:a", "aac", "-b:a", "128k", str(hedef)],
                       capture_output=True, text=True, timeout=1800)
    gecici.unlink(missing_ok=True)
    if p.returncode != 0 or not hedef.exists():
        return jsonify({"hata": "Ses dosyası dönüştürülemedi."}), 500
    takvim_e = None
    try:
        import takvim as takvim_modulu
        takvim_e = takvim_modulu.etkinlik_bul(bas, bas + sure)
    except Exception as e:  # noqa: BLE001
        print(f"takvim hatası: {e}", flush=True)
    r = _baslat({"link": str(hedef), "ozet": True, "konusmaci": True, "altyazi": False, "toplanti": True,
                 "toplanti_baslik": baslik or _toplanti_adi_temizle((takvim_e or {}).get("ad") or ""),
                 "kayit_dosya": str(hedef), "uygulama": "Telefon", "kayit_baslangic": bas,
                 "katilimcilar": [k["ad"] for k in (takvim_e or {}).get("katilimcilar", []) if k.get("ad")], "takvim": takvim_e or None})
    j = r.get_json() if hasattr(r, "get_json") else {}
    _bildir("Kayıt alındı", "Yazıya dökülüyor; bitince toplantılarda görünecek")
    return jsonify({"id": (j or {}).get("id"), "dosya": str(hedef), "sure": round(sure)})



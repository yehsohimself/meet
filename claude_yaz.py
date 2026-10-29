"""claude_yaz.py - Metin yazımı için Claude'u (kullanıcının Claude aboneliğiyle) arka planda çağırır.

Claude masaüstü uygulamasıyla gelen Claude Code komut satırı programı `-p` (yazdır ve çık) kipinde çalıştırılır:
araç YOK (`--tools ""`), MCP yok, ayar dosyası yok, oturum kaydı yok; yalnızca istem verilir, metin alınır.
Ek ücret yok (abonelik kullanım hakkından düşer). Bir kez giriş gerekir: "Claude'a Giriş.command" (ya da Ayarlar →
"Claude'a bağlan"). Giriş yoksa ya da hata olursa çağıran yer bilgisayardaki modele (Ollama) döner.

hazir() -> bool (10 dk önbellekli), sor(istem, sistem) -> str, sor_json(istem, sistem) -> dict
Elle: python claude_yaz.py            (durum)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import contextvars
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
DURUM = KLASOR / "kayitlar" / ".claude_durum.json"
DURUM_SN = 600


def _ayar():
    try:
        return json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def program():
    """Claude Code programının yolu: PATH'teki `claude`, ~/.local/bin, ya da masaüstü uygulamasının en yeni sürümü."""
    yol = shutil.which("claude")
    if yol:
        return yol
    for aday in (Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude")):
        if aday.exists():
            return str(aday)
    def surum(p):
        m = re.search(r"claude-code/(\d+)\.(\d+)\.(\d+)/", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    adaylar = glob.glob(str(Path.home() / "Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"))
    return max(adaylar, key=surum) if adaylar else None


def model():
    return os.environ.get("CLAUDE_MODEL") or _ayar().get("claude_model") or "sonnet"


# Misafir (Studio davetlileri, 2026-10-24): misafirin işi yalnızca KENDİ Claude anahtarıyla yapılır; anahtarı yoksa Claude hiç kullanılmaz
# (çağıran yer bilgisayardaki modele döner). Sitede bağlam değişkeni, alt süreçlerde VH_MISAFIR / VH_MISAFIR_ANAHTAR ortam değişkenleri.
MISAFIR = contextvars.ContextVar("vh_misafir", default=None)      # {"id": ..., "anahtar": ...}


def misafir():
    m = MISAFIR.get()
    if m:
        return m
    if os.environ.get("VH_MISAFIR"):
        return {"id": os.environ["VH_MISAFIR"], "anahtar": os.environ.get("VH_MISAFIR_ANAHTAR", "")}
    return None


def _ortam():
    e = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "USER": os.environ.get("USER", ""),
         "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
    m = misafir()
    if m:
        a = (m.get("anahtar") or "").strip()
        if not a:
            raise ClaudeHata("Misafirin Claude anahtarı yok")
        e["CLAUDE_CODE_OAUTH_TOKEN" if a.startswith("sk-ant-oat") else "ANTHROPIC_API_KEY"] = a
    return e


def durum(zorla=False):
    """{"program": bool, "giris": bool, "kullanim": bool}. Ayarlarda kapatılmışsa kullanim False."""
    acik = _ayar().get("claude", True)
    if not zorla and DURUM.exists() and time.time() - DURUM.stat().st_mtime < DURUM_SN:
        try:
            d = json.loads(DURUM.read_text(encoding="utf-8"))
            d["kullanim"] = bool(acik and d.get("giris"))
            return d
        except Exception:  # noqa: BLE001
            pass
    p = program()
    d = {"program": bool(p), "giris": False}
    if p:
        try:
            r = subprocess.run([p, "auth", "status"], capture_output=True, text=True, timeout=30, env=_ortam(), cwd=tempfile.gettempdir())
            d["giris"] = bool(json.loads(r.stdout or "{}").get("loggedIn"))
        except Exception:  # noqa: BLE001
            d["giris"] = False
    try:
        DURUM.parent.mkdir(parents=True, exist_ok=True)
        DURUM.write_text(json.dumps(d), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    d["kullanim"] = bool(acik and d["giris"])
    return d


_yerel = threading.local()


@contextmanager
def toplanti():
    """Bu blok içindeki çağrılar toplantı içeriğidir; Ayarlar'da 'Toplantılarda da Claude' kapalıysa Claude kullanılmaz."""
    eski = getattr(_yerel, "toplanti", False)
    _yerel.toplanti = True
    try:
        yield
    finally:
        _yerel.toplanti = eski


def toplanti_mi():
    return bool(getattr(_yerel, "toplanti", False) or os.environ.get("VH_TOPLANTI") == "1")


def hazir(toplanti_icerik=None):
    """Claude kullanılabilir mi? Toplantı içeriğinde ayrıca `claude_toplanti` ayarına bakılır; abonelik sınırındaysa hayır.
    `VH_CLAUDE_YOK` (transkript.py --claude-yok; Meet örnek toplantı testi) varsa hiç kullanılmaz."""
    if os.environ.get("VH_CLAUDE_YOK"):
        return False
    m = misafir()
    if m:                                     # misafir: yalnız kendi anahtarı varsa (sahibin oturumu ve sınırı hiç devreye girmez)
        return bool((m.get("anahtar") or "").strip()) and program() is not None
    if not durum()["kullanim"] or sinir_durumu():
        return False
    t = toplanti_mi() if toplanti_icerik is None else toplanti_icerik
    return not (t and _ayar().get("claude_toplanti", True) is False)


def etiket():
    return f"claude:{model()}"


class ClaudeHata(RuntimeError):
    def __init__(self, mesaj=""):
        m = str(mesaj)
        if misafir():                          # davetliye teknik İngilizce yerine ne yapacağını söyleyen mesaj (2026-10-25)
            if re.search(r"invalid api key|authenticat|oauth|\b401\b|credit balance|billing", m, re.I):
                m = "Claude anahtarınız çalışmıyor (geçersiz, süresi dolmuş ya da bakiyesi yok). Sağ üstteki hesap düğmesinden yenileyin."
            elif re.search(r"usage limit|rate limit|limit reached|too many requests", m, re.I):
                m = "Claude hesabınızın kullanım sınırı doldu; biraz sonra yeniden deneyin."
        super().__init__(m)


KULLANIM = KLASOR / "kayitlar" / ".claude_kullanim.jsonl"
SINIR = KLASOR / "kayitlar" / ".claude_sinir.json"
_kayit_kilidi = threading.Lock()
IS_ADLARI = {
    "terimler.claude_temizle": "Transkript temizliği", "ozet.ozet_uret": "Özet", "ceviri": "Çeviri", "sor": "Soru-cevap",
    "marka": "Marka içerik paketi", "paylasim": "X taslakları", "notlar": "Toplantı notları", "adlar": "Ad önerisi",
    "klipler": "Öne çıkan anlar", "broll": "B-roll", "canli": "Canlı özet", "goruntu": "Görüntü betimleme",
    "altyazi": "Altyazı kırılımı", "onbrifing": "Toplantı öncesi hatırlatma", "haftalik.brief": "Brief",
    "haftalik.takip_epostasi": "Takip e-postası", "haftalik": "Haftalık özet", "site": "Toplantı adı ve müşteri",
    "transkript": "Transkript temizliği",
}


def _is_adi():
    """Çağrıyı yapan işin adı (yığından): claude_yaz ve ozet._sor atlanır."""
    import inspect
    for f in inspect.stack()[2:12]:
        mod = Path(f.filename).stem
        if mod in ("claude_yaz", "threading", "concurrent", "thread") or (mod == "ozet" and f.function == "_sor"):
            continue
        for anahtar in (f"{mod}.{f.function}", mod):
            if anahtar in IS_ADLARI:
                return IS_ADLARI[anahtar]
        if mod not in ("_base", "contextlib"):
            return mod
    return "Diğer"


def _kullanim_yaz(is_adi, model_adi, sn, d=None, hata=""):
    u = (d or {}).get("usage") or {}
    satir = {"t": round(time.time()), "is": is_adi, "model": model_adi, "sn": round(sn, 1), "ok": not hata,
             "giris": int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0),
             "cikis": int(u.get("output_tokens") or 0), **({"hata": hata[:160]} if hata else {})}
    if misafir():                              # davetlinin kendi hesabıyla yaptığı çağrı: sahibin bütçesine ve özetine sayılmaz
        satir["misafir"] = misafir().get("id")
    try:
        with _kayit_kilidi:
            KULLANIM.parent.mkdir(parents=True, exist_ok=True)
            with open(KULLANIM, "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _sinir_kontrol(mesaj):
    """Abonelik kullanım sınırı mesajı: sınır bitene dek (bilinmiyorsa 1 saat) Claude kullanılmaz, yerel model devreye girer.
    Davetlinin kendi hesabının sınırı sahibinkini kapatmaz (2026-10-24)."""
    if misafir():
        return
    if not re.search(r"usage limit|rate limit|limit reached|too many requests|overloaded", mesaj, re.I):
        return
    m = re.search(r"\|(\d{10})", mesaj)
    bitis = int(m.group(1)) if m else time.time() + 3600
    try:
        SINIR.write_text(json.dumps({"bitis": bitis, "mesaj": mesaj[:200], "zaman": time.time()}), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


ARKA_PLAN_ESIK = 200        # 5 saatte bu kadar çağrıdan sonra arka plan işleri bekler (kullanıcının doğrudan işleri etkilenmez)


def son_cagri_sayisi(saat=5):
    try:
        sinir_ = time.time() - saat * 3600
        with open(KULLANIM, "rb") as f:                      # yalnız son ~400 KB (2026-10-25: dosya büyüdükçe tam okuma pahalılaşıyordu)
            f.seek(max(0, os.path.getsize(KULLANIM) - 400_000)); kuyruk = f.read().decode("utf-8", "ignore").splitlines()[1:]
        return sum(1 for satir in kuyruk if satir.strip() and (x := json.loads(satir)).get("t", 0) > sinir_ and not x.get("misafir"))
    except Exception:  # noqa: BLE001
        return 0


def arka_plan_uygun():
    """Claude bütçesi (2026-10-19): kategori öğrenmesi ve otomatik paylaşım önerileri gibi kendiliğinden çalışan işler, son 5 saatte
    ARKA_PLAN_ESIK (ya da ayarlar `claude_arka_plan_esik`) çağrıyı aştıysa ya da abonelik sınırı bildirilmişse beklesin."""
    if misafir():
        return hazir()
    if sinir_durumu():
        return False
    try:
        esik = int(json.loads((KLASOR / "ayarlar.json").read_text(encoding="utf-8")).get("claude_arka_plan_esik") or ARKA_PLAN_ESIK)
    except Exception:  # noqa: BLE001
        esik = ARKA_PLAN_ESIK
    return son_cagri_sayisi(5) < esik


def sinir_durumu():
    try:
        d = json.loads(SINIR.read_text(encoding="utf-8"))
        return d if d.get("bitis", 0) > time.time() else None
    except Exception:  # noqa: BLE001
        return None


# Kullanım özetinde (Ayarlar) iş adları: kayıtta modül adı kalmış olanlar okunur ada çevrilir (kayıttaki ham ad değişmez;
# BEKLER_ONEK onunla eşleşir).
GORUNUR_AD = {
    "04_toplanti": "Toplantı adı ve müşteri", "kisaca": "Toplantı özeti (Kısaca)", "danisman": "Koçluk notu", "sinyaller": "Toplantı sinyalleri",
    "toplanti_kapisi": "Toplantı mı kontrolü", "canli_asistan": "Canlı öneriler", "meet_altyazi": "Altyazıyla düzeltme",
    "meet_gelisim": "Meet bakımı", "karar_zinciri": "Karar zinciri", "tarifler": "Tarifler", "sohbet": "Toplantıyla sohbet",
    "sirketler": "Şirket seçimi", "kisiler": "Kişi profilleri", "notlarim": "Toplantı notlarınız", "duzenle": "Düzenleme",
    "atolye": "Atölye", "atolye_analiz": "Atölye", "atolye_bilgi": "Atölye", "kesif": "Ghost keşif", "yayin": "Yayın paketi",
    "dublaj": "Dublaj", "dil_cevir": "Arayüz çevirisi", "studio_gelisim": "Studio bakımı", "sahne_dizin": "Görüntü araması",
    "<string>": "Diğer", "<stdin>": "Diğer",
}


def gorunur_ad(ad):
    ad = ad or "Diğer"
    if ad in GORUNUR_AD:
        return GORUNUR_AD[ad]
    if ad.startswith("<"):                     # "<string>", "<module>": sunucu parçalarından (exec) gelen çağrı (2026-10-29: Ayarlar'da ham ad görünüyordu)
        return "Diğer"
    m = re.match(r"^\d\d_(\w+)$", ad)          # sunucu/04_toplanti.py gibi parça dosyası adı
    if m:
        return {"toplanti": "Toplantı notları", "ghost": "Ghost", "marka": "İçerik paketi", "meet_gelisim": "Meet gelişimi",
                "studio": "Studio", "video_isleri": "Video işleri", "api": "Studio"}.get(m.group(1), "Diğer")
    for on, gorunur in (("content", "Content"), ("couple", "Couple"), ("pt", "PT")):
        if ad == on or ad.startswith(on + "_"):
            return gorunur
    return ad


def kullanim_ozeti(gun=7):
    """Son N günün Claude kullanımı: toplam ve iş başına (istek, giriş/çıkış token, süre)."""
    sinir = time.time() - gun * 86400
    isler, top = {}, {"istek": 0, "giris": 0, "cikis": 0, "sn": 0.0, "hata": 0, "bugun": 0}
    bugun = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    try:
        satirlar = KULLANIM.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        satirlar = []
    for l in satirlar:
        try:
            x = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        if x.get("t", 0) < sinir or x.get("misafir"):
            continue
        i = isler.setdefault(gorunur_ad(x.get("is")), {"istek": 0, "giris": 0, "cikis": 0, "sn": 0.0})
        for d in (i, top):
            d["istek"] += 1; d["giris"] += x.get("giris", 0); d["cikis"] += x.get("cikis", 0); d["sn"] += x.get("sn", 0)
        top["hata"] += 0 if x.get("ok", True) else 1
        top["bugun"] += 1 if x.get("t", 0) >= bugun else 0
    return {"gun": gun, "toplam": top, "isler": dict(sorted(isler.items(), key=lambda kv: -kv[1]["istek"])), "sinir": sinir_durumu()}


# Toplantılara öncelik (2026-10-28; ölçüm: 7 günde 2.518 çağrının 1.688'i Ghost'un X taslakları). Abonelik sınırına takılınca toplantı notları
# yerel modele düşüyor ve Kısaca hiç yazılamıyordu. Kural: (1) toplantı kaydedilirken ya da notları hazırlanırken (son 10 dk'da toplantı içerikli
# bir çağrı olduysa) kendiliğinden çalışan arka plan işleri bekler; (2) son 5 saatin çağrısı arka plan eşiğini (ARKA_PLAN_ESIK) aştıysa aynı işler
# eşiğin altına inene dek bekler. Kullanıcının elle başlattığı işler (site isteğinden gelen) ve toplantı içeriği hiç beklemez.
TOPLANTI_ISARETI = KLASOR / "kayitlar" / ".toplanti_claude"
BEKLER_ONEK = ("X taslakları", "karisim", "kesif", "tetik", "fikir_kartlari", "konu_toplantisi", "yerimleri", "performans", "bultenler",
               "seckiler", "ghost", "hesaplar", "studio_gelisim", "sahne_dizin", "atolye", "couple", "content", "pt_kanit", "dil_cevir")


def toplanti_suruyor():
    """Toplantı kaydediliyor mu ya da notları hazırlanıyor mu (son 10 dk'da toplantı içerikli Claude çağrısı)."""
    try:
        k = json.loads((KLASOR / "kayitlar" / ".kayit_canli.json").read_text(encoding="utf-8"))
        if k.get("kayit") and time.time() - float(k.get("guncelleme", 0)) < 60:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        return time.time() - TOPLANTI_ISARETI.stat().st_mtime < 600
    except OSError:
        return False


def _istekten_mi():
    try:
        from flask import has_request_context
        return has_request_context()
    except Exception:  # noqa: BLE001
        return False


def _oncelik(is_adi):
    """Toplantı işi işaret bırakır; kendiliğinden çalışan arka plan işi gerekirse bekler (en çok 2 saat)."""
    if misafir():
        return
    if toplanti_mi():
        try:
            TOPLANTI_ISARETI.parent.mkdir(parents=True, exist_ok=True); TOPLANTI_ISARETI.touch()
        except OSError:
            pass
        return
    if not str(is_adi).startswith(BEKLER_ONEK) or _istekten_mi():
        return
    son, yazdi = time.time() + 7200, False
    while time.time() < son:
        neden = "toplantı sürüyor" if toplanti_suruyor() else ("Claude bütçesi toplantılara ayrıldı" if not arka_plan_uygun() and not sinir_durumu() else "")
        if not neden:
            return
        if not yazdi:
            print(f"Claude: {is_adi} bekliyor ({neden})", flush=True); yazdi = True
        time.sleep(20)
    raise ClaudeHata("Arka plan işi Claude'u bekledi; toplantı işleri önce geldi")


def sor(istem, sistem="", zaman_asimi=600, model_adi=None, araclar=""):
    """İstemi Claude'a verir, yanıt metnini döndürür. Varsayılan araç yok; yalnızca metin. `araclar` yalnız web için verilir
    ("WebSearch,WebFetch"; 2026-10-29 Content'in akım araması: anahtarsız arama motorları otomatik sorguyu engelliyor)."""
    p = program()
    if not p:
        raise ClaudeHata("Claude programı bulunamadı")
    if araclar and set(araclar.split(",")) - {"WebSearch", "WebFetch"}:
        raise ClaudeHata("yalnız web araçlarına izin var")
    _oncelik(_is_adi())
    komut = [p, "-p", "--tools", araclar, "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
             "--output-format", "json", "--model", model_adi or model()]
    if araclar:
        komut += ["--allowedTools", araclar]
    if sistem:
        komut += ["--system-prompt", sistem]
    is_adi, t0, m_adi = _is_adi(), time.time(), model_adi or model()
    with tempfile.TemporaryDirectory() as bos:                       # boş çalışma klasörü: proje dosyalarına bakmasın
        try:
            r = subprocess.run(komut, input=istem, capture_output=True, text=True, timeout=zaman_asimi, env=_ortam(), cwd=bos)
        except subprocess.TimeoutExpired:
            _kullanim_yaz(is_adi, m_adi, time.time() - t0, hata="zaman aşımı"); raise ClaudeHata("zaman aşımı")
    try:
        d = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        _kullanim_yaz(is_adi, m_adi, time.time() - t0, hata=(r.stderr or r.stdout or "yanıt yok")[:160])
        _sinir_kontrol(r.stderr or r.stdout or "")
        raise ClaudeHata((r.stderr or r.stdout or "yanıt yok").strip()[:300])
    _kullanim_yaz(is_adi, m_adi, time.time() - t0, d, "" if not d.get("is_error") else str(d.get("result") or "hata"))
    if d.get("is_error"):
        mesaj = str(d.get("result") or d.get("terminal_reason") or "hata")
        _sinir_kontrol(mesaj)
        if "logged in" in mesaj.lower() or "login" in mesaj.lower():
            try:
                DURUM.write_text(json.dumps({"program": True, "giris": False}), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        raise ClaudeHata(mesaj[:300])
    return str(d.get("result") or "")


def sor_akis(istem, sistem="", zaman_asimi=300, model_adi=None):
    """Yanıtı yazıldıkça parça parça verir (üreteç). Toplantı sohbetinde ilk kelimeler birkaç saniyede görünsün diye (2026-10-20;
    tam yanıtı beklemek 30-100 sn sürebiliyordu). Claude Code: --output-format stream-json --include-partial-messages."""
    p = program()
    if not p:
        raise ClaudeHata("Claude programı bulunamadı")
    komut = [p, "-p", "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
             "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--model", model_adi or model()]
    if sistem:
        komut += ["--system-prompt", sistem]
    is_adi, t0, m_adi = _is_adi(), time.time(), model_adi or model()
    with tempfile.TemporaryDirectory() as bos:
        pr = subprocess.Popen(komut, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_ortam(), cwd=bos, bufsize=1)
        pr.stdin.write(istem); pr.stdin.close()
        sonuc, verilen = None, 0
        try:
            for satir in pr.stdout:
                if time.time() - t0 > zaman_asimi:
                    pr.kill(); raise ClaudeHata("zaman aşımı")
                try:
                    d = json.loads(satir)
                except Exception:  # noqa: BLE001
                    continue
                if d.get("type") == "stream_event":
                    ev = d.get("event") or {}
                    if ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                        parca = ev["delta"].get("text") or ""
                        verilen += len(parca)
                        if parca:
                            yield parca
                elif d.get("type") == "result":
                    sonuc = d
        finally:
            if pr.poll() is None:
                pr.kill()
            pr.wait()
    _kullanim_yaz(is_adi, m_adi, time.time() - t0, sonuc, "" if sonuc and not sonuc.get("is_error") else str((sonuc or {}).get("result") or "yanıt yok"))
    if not sonuc or sonuc.get("is_error"):
        mesaj = str((sonuc or {}).get("result") or "yanıt yok")
        _sinir_kontrol(mesaj)
        raise ClaudeHata(mesaj[:300])
    if not verilen and sonuc.get("result"):                 # akış parçası gelmediyse tamamını ver
        yield str(sonuc["result"])


def sor_gorsel(istem, resimler, sistem="", zaman_asimi=900, model_adi=None):
    """Metin + resimler (jpg/png yolları) ile tek mesaj; yanıt metni. Claude Code'un stream-json girişiyle."""
    import base64
    p = program()
    if not p:
        raise ClaudeHata("Claude programı bulunamadı")
    _oncelik(_is_adi())
    icerik = [{"type": "text", "text": istem}]
    for r in resimler:
        tur = "image/png" if str(r).lower().endswith(".png") else "image/jpeg"
        icerik.append({"type": "image", "source": {"type": "base64", "media_type": tur, "data": base64.b64encode(Path(r).read_bytes()).decode()}})
    mesaj = json.dumps({"type": "user", "message": {"role": "user", "content": icerik}}) + "\n"
    komut = [p, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--tools", "", "--strict-mcp-config",
             "--setting-sources", "", "--no-session-persistence", "--model", model_adi or model()]
    if sistem:
        komut += ["--system-prompt", sistem]
    is_adi, t0, m_adi = _is_adi(), time.time(), model_adi or model()
    with tempfile.TemporaryDirectory() as bos:
        r = subprocess.run(komut, input=mesaj, capture_output=True, text=True, timeout=zaman_asimi, env=_ortam(), cwd=bos)
    sonuc = None
    for satir in (r.stdout or "").splitlines():
        try:
            d = json.loads(satir)
        except Exception:  # noqa: BLE001
            continue
        if d.get("type") == "result":
            sonuc = d
    _kullanim_yaz(is_adi, m_adi, time.time() - t0, sonuc, "" if sonuc and not sonuc.get("is_error") else str((sonuc or {}).get("result") or r.stderr or "yanıt yok"))
    if not sonuc:
        raise ClaudeHata((r.stderr or "yanıt yok").strip()[:300])
    if sonuc.get("is_error"):
        _sinir_kontrol(str(sonuc.get("result") or ""))
        raise ClaudeHata(str(sonuc.get("result") or "hata")[:300])
    return str(sonuc.get("result") or "")


def json_coz(metin):
    """Yanıttaki ilk JSON nesnesini çıkarır (```json bloğu ya da düz)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", metin, re.S)
    ham = m.group(1) if m else metin[metin.find("{"): metin.rfind("}") + 1]
    try:
        return json.loads(ham)
    except Exception:  # noqa: BLE001
        return {}


def sor_json(istem, sistem="", zaman_asimi=600, model_adi=None):
    sistem = (sistem + "\n" if sistem else "") + "Yanıtın YALNIZCA geçerli bir JSON nesnesi olsun; öncesinde ya da sonrasında açıklama yazma."
    c = json_coz(sor(istem, sistem, zaman_asimi, model_adi))
    if not c:
        raise ClaudeHata("Claude'un yanıtı okunamadı")
    return c


if __name__ == "__main__":
    print(json.dumps({**durum(zorla=True), "yol": program(), "model": model()}, ensure_ascii=False, indent=1))

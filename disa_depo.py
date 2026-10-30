"""disa_depo.py - Bir ürünü tek başına çalışan ayrı bir depo olarak keser (2026-10-25; kullanıcı: "her ürün ayrı depo, seri yok").

python disa_depo.py studio <hedef klasör>      Studio + ortak motor → hedef (var olan dosyaların üstüne yazar, fazlalıkları siler)
python disa_depo.py meet <hedef klasör>        Meet + ortak motor → hedef; ürüne özel dosyalar disa/meet/
python disa_depo.py pt <hedef klasör>          PT tek başına (pt_sunucu.py) → hedef; ürüne özel dosyalar disa/pt/
python disa_depo.py content <hedef klasör>     Content tek başına (content_sunucu.py) → hedef; ürüne özel dosyalar disa/content/
python disa_depo.py pt-medya <zip>             PT'nin görsel ve ses paketi (GitHub sürümüne konur)

Ne kopyalanır: ürünün sunucu parçaları + onların kullandığı modüller (kapanış), statik dosyalar, testler, şablonlar, lisans. Kişisel dosyalar
(ayarlar.json, profil/, markalar/, kayıtlar...) hiçbir zaman kopyalanmaz. Kesilen depo 'ürünler isteğe bağlı' mekanizmasıyla çalışır:
olmayan sunucu parçası = kapalı ürün (sunucu/10_sayfalar.py, 01_yardimcilar.mesgul_nedenler). Çıkış: hedefte `python -m pytest tests -q` ve
`python duman_testi.py hizli` geçmeli (bu betik çalıştırır, sonucu yazar).
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

URUNLER = {
    "studio": {
        "ad": "Studio",
        "parcalar": ["00_baslangic", "01_yardimcilar", "02_isci", "03_video_isleri", "06_marka", "07_cekirdek", "09_cekirdek", "10_sayfalar", "11_ozellik_sayaci", "12_api",
                     "13_takip", "16_altyapi_ve_meet", "17_disa_aktarim", "18_indirilenler", "21_studio", "22_misafir", "24_guvenlik"],
        "moduller": ["site", "transkript", "indir", "isimlendir", "adlar", "altyazi", "anlam", "arkaplan", "broll", "ceviri", "claude_yaz", "dublaj",
                     "dudak", "duzenle", "goruntu", "harfler", "kadraj", "kalite", "kapak", "kayit_json", "kitaplik_onbellek", "klipler", "konusan", "marka",
                     "ozet", "sahne_dizin", "sesler", "sor", "sohbet", "studio_duzelt", "studio_gelisim", "studio_onizle", "takip", "temizle", "terimler",
                     "yakma", "yayin", "haftalik", "notlar", "notlarim", "yedek", "geri_yukle", "sizinti", "ortak", "gizli", "duman_testi", "yeniden_baslat",
                     "videohub_mcp", "disa_depo"],
        "static": ["index.html", "studio_ek.js", "studio_ek.css", "misafir.js", "manifest.webmanifest", "ikon-180.png", "ikon-192.png", "ikon-512.png",
                   "ikon-512-maskable.png", "il", "logo", "ikon", "altyazi_ornek", "arka_ornek", "dublaj_ornek"],
        "dosyalar": ["requirements.txt", "pytest.ini", "LICENSE", "kurulum.sh", "ayarlar.ornek.json", ".gitignore", "atolye/markalar.ornek.json",
                     "tests/conftest.py", "tests/test_birimler.py", "tests/test_site.py", "tests/test_yedek.py"],
        "requirements_cikar": ["python-pptx", "scenedetect", "opencv-python-headless", "pywebpush", "segno"],
        "komut": ("Video Hub.command", "Studio.command"),
    },
}


def kes(urun, hedef, log=print):
    U = URUNLER[urun]
    hedef = Path(hedef).expanduser().resolve()
    if hedef == KOK or KOK in hedef.parents:
        raise SystemExit("Hedef, kaynak klasörün içinde olamaz.")
    hedef.mkdir(parents=True, exist_ok=True)
    kopyalanan = set()

    def kopyala(kaynak, yol):
        d = hedef / yol
        d.parent.mkdir(parents=True, exist_ok=True)
        if kaynak.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(kaynak, d, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
            for f in d.rglob("*"):
                if f.is_file():
                    kopyalanan.add(f.relative_to(hedef).as_posix())
        else:
            shutil.copy2(kaynak, d)
            kopyalanan.add(Path(yol).as_posix())

    for p in U["parcalar"]:
        kopyala(KOK / "sunucu" / f"{p}.py", f"sunucu/{p}.py")
    for m in sorted(set(U["moduller"]) | set(_kapanis(U["parcalar"], U["kapanis"], U.get("haric", MEET_HARIC)) if U.get("kapanis") else [])):
        if (KOK / f"{m}.py").exists():
            kopyala(KOK / f"{m}.py", f"{m}.py")
        else:
            log(f"  (yok, atlandı: {m}.py)")
    for s in U["static"]:
        if (KOK / "static" / s).exists():
            kopyala(KOK / "static" / s, f"static/{s}")
    for f in U["dosyalar"]:
        if (KOK / f).exists():
            kopyala(KOK / f, f)
    eski_ad, yeni_ad = U["komut"]
    if eski_ad and (KOK / eski_ad).exists():
        kopyala(KOK / eski_ad, yeni_ad)
    # ürüne özel düzeltmeler
    req = (hedef / "requirements.txt").read_text(encoding="utf-8").splitlines() if not U.get("requirements") else []
    if req:
        (hedef / "requirements.txt").write_text("\n".join(l for l in req if not any(l.startswith(c) for c in U["requirements_cikar"])) + "\n", encoding="utf-8")
    if U.get("requirements"):
        (hedef / "requirements.txt").write_text(U["requirements"], encoding="utf-8"); kopyalanan.add("requirements.txt")
    for kaynak in U.get("kopya", []):                         # veri klasörlerinden depoya giren dosyalar (PT hareket kartları, BLS dizini)
        for f in sorted(KOK.glob(kaynak)):
            kopyala(f, f.relative_to(KOK).as_posix())
    if U.get("sablon"):                                       # ürüne özel dosyalar (kurulum, başlatıcı, .gitignore, testler): disa/<ürün>/
        sk = KOK / U["sablon"]
        for f in sorted(sk.rglob("*")):
            if f.is_file() and f.name != ".DS_Store":
                rel = f.relative_to(sk).as_posix().replace("_gitignore", ".gitignore")
                kopyala(f, rel)
                if rel.endswith((".sh", ".command")):
                    (hedef / rel).chmod(0o755)
    if U.get("son"):                                          # ürüne özel son düzeltmeler (Meet: uzantıdan kardeş ürün parçaları çıkar)
        globals()[U["son"]](hedef)
    site = hedef / "site.py"
    if site.exists():
        site.write_text(site.read_text(encoding="utf-8").replace('"Video Hub.command"', f'"{yeni_ad}"').replace("Transkript sisteminin", f"{U['ad']} ürününün"), encoding="utf-8")
    gi = hedef / ".gitignore"
    ek = "\n# kesilen depo: örnek medya ve ekran görüntüsü depoya girer (monorepo'da *.mp4/*.jpg dışarıdaydı)\n!static/*_ornek/*.mp4\n!docs/ekran.jpg\n"
    if "!docs/ekran.jpg" not in gi.read_text(encoding="utf-8"):
        gi.write_text(gi.read_text(encoding="utf-8") + ek, encoding="utf-8")
    if urun in README:                                        # PT'nin README'si şablonda (disa/pt/README.md)
        (hedef / "README.md").write_text(README[urun], encoding="utf-8")
    kopyalanan.add("README.md"); kopyalanan.add("docs/ekran.jpg")
    (hedef / "docs").mkdir(exist_ok=True)
    if U.get("mimari", True):                                 # Content'in motoru yok: ortak mimari notu ona uymaz
        (hedef / "docs" / "MIMARI.md").write_text(_mimari(urun), encoding="utf-8"); kopyalanan.add("docs/MIMARI.md")
    # fazlalıkları sil (yalnız bu betiğin yazdığı türden dosyalar; .git, veri klasörleri dokunulmaz)
    for f in list(hedef.rglob("*")):
        rel = f.relative_to(hedef).as_posix()
        if f.is_file() and rel not in kopyalanan and not rel.startswith(".git/") and f.suffix in {".py", ".js", ".css", ".html", ".svg", ".png", ".md", ".txt", ".json", ".webmanifest", ".command", ".mp4", ".ini", ".sh"} \
                and not rel.startswith(("kayitlar/", "profil/", "ghost/", "indirilenler/", "yuklemeler/", ".onbellek/", "static/derlenmis/", "pt/", "pt_medya/", "modeller/", ".yedek/", ".cop/")) and rel not in ("ayarlar.json", "sesler.json", "takip.json", "CLAUDE.md"):
            f.unlink()
    for d in sorted((x for x in hedef.rglob("*") if x.is_dir() and ".git" not in x.parts), key=lambda x: -len(x.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    log(f"{len(kopyalanan)} dosya → {hedef}")
    return hedef


def dogrula(hedef, log=print):
    """Kesilen depoda testler: pytest + duman hizli (kaynak .venv ile; hedefte venv olmayabilir)."""
    py = KOK / ".venv" / "bin" / "python"
    sonuc = {}
    adimlar = [("pytest", [str(py), "-m", "pytest", "tests", "-q", "-x"])]
    if (Path(hedef) / "duman_testi.py").exists():
        adimlar.append(("duman hizli", [str(py), "duman_testi.py", "hizli"]))
    for ad, cmd in adimlar:
        r = subprocess.run(cmd, cwd=hedef, capture_output=True, text=True, timeout=1200)
        sonuc[ad] = r.returncode == 0
        log(f"  {'✓' if r.returncode == 0 else '✗'} {ad}" + ("" if r.returncode == 0 else "\n" + (r.stdout + r.stderr)[-1500:]))
    return sonuc


README = {"studio": """# Studio

Studio brings transcription, subtitles, video clips, dubbing and publishing drafts into one workspace on your Mac.
Built for Apple silicon. Open source under the MIT license.

![Studio](docs/ekran.jpg)

## What you can do

Paste a video link (YouTube, Instagram, TikTok, Vimeo…) or drop a file, then pick what you want:

- **Transcript** with speaker labels and voice recognition; Word, text and SRT files.
- **Summary**, highlights, timestamped chapters; ask questions about the video.
- **Subtitled video** (five caption styles), **clips** and face-tracked vertical **Shorts**, text-based editing, silence removal,
  export to Final Cut / Premiere / DaVinci.
- **Translation** and **dubbing** in the speaker's own voice.
- **Publishing kit:** title options, description and chapters, tags, thumbnail text and images, LinkedIn and Instagram copy.
- **Library** with text and picture search, channel watch, weekly digest; an invite link for a small closed group.

Interface in English or Turkish (TR/EN in the top bar).

## Install

Requirements: a Mac with Apple silicon, macOS 14 or newer, [Homebrew](https://brew.sh) and Git.

```bash
git clone https://github.com/yehsohimself/studio.git
cd studio
./kurulum.sh
.venv/bin/python site.py
```

Then open http://127.0.0.1:8765. For later launches, double-click `Studio.command`. The install script adds `ffmpeg`, `deno` and `uv`
with Homebrew, creates `.venv` with the Python packages and copies `ayarlar.ornek.json` → `ayarlar.json`. The speech model (~1.6 GB)
downloads on first use.

### Writing features: Claude or a local model

Transcription and speaker separation need nothing else. Summaries, translations, the publishing kit and other writing tasks need one of:

- **Claude** through your own subscription: install [Claude Code](https://claude.com/claude-code) and sign in once (`claude auth login`).
  When you use Claude, the text needed for that task is sent to Claude.
- **A local model:** `brew install ollama`, `brew services start ollama`, `ollama pull gemma3:4b`. Everything then stays on the Mac
  (slower, less accurate for long texts).

If neither is set up, transcription still works; summaries and writing tasks are skipped.

## Where your data goes

Speech recognition, speaker separation, subtitles, clips and dubbing run on your Mac. Video and audio files never leave it. For writing
tasks, the transcript (or the part needed) is sent to Claude only if you chose Claude; with Ollama nothing is sent. Downloads use
`yt-dlp`, which talks to the video site. Optional integrations (Cloudflare tunnel for invite links, sync.so for lip sync, Pexels for B-roll)
are off until you enable them in Settings.

## Tested on

MacBook Air M4, 16 GB, macOS 26.6, Claude Code signed in. Developed and used daily on this machine; a clean install in a fresh folder has
been done with the script above.

## Known limits

- macOS with Apple silicon only (mlx-whisper, Vision, AppKit).
- Code identifiers and comments are in Turkish; the interface is bilingual.
- Instagram and TikTok sometimes require a browser session (Settings → "Browser session").

## Development

`site.py` is a small loader; the code runs in `sunucu/00_… 24_….py` parts within one namespace. Tests: `.venv/bin/python -m pytest
tests -q` and `duman_testi.py hizli|birim|canli|studio`. After changing the server: `.venv/bin/python yeniden_baslat.py`. Architecture:
[docs/MIMARI.md](docs/MIMARI.md). `python sizinti.py` scans the repo for personal data (also run by the commit hook). This repo is cut from
a larger workspace that develops sibling products (Meet, Ghost, Content, PT) on the same engine; siblings that are not installed are off.

Issues and pull requests are welcome; say which video site and which step failed.

---

**Türkçe:** Video linki ya da dosyası → transkript, özet, çeviri, altyazılı video, klip ve dikey Shorts, kendi sesiyle dublaj, yayın
paketi; tek yerde, kendi Mac'inizde. Ses tanıma Mac'te çalışır; özet ve yazı işleri için Claude (kendi hesabınız; o işin metni Claude'a
gider) ya da yerel Ollama modeli gerekir. Kurulum: yukarıdaki dört komut, sonra tarayıcıda http://127.0.0.1:8765. Arayüz dili üst
çubuktaki TR/EN düğmesinden.
"""}



# ----------------------------------------------------------------------------- PT (2026-10-29)
PT_MEDYA_JSON = ["kartlar.json", "youtube.json", "youtube_sorgu.json", "anatomi.json", "storyboard.json"]
PT_MEDYA_HARIC = ("istekler.json", "_kisi.png", "_onizleme.png", "_ses_model", "bekleyen.json", "ham.mp4", "bas.png", "bit.png")

URUNLER["pt"] = {
    "ad": "PT",
    "parcalar": [],
    "moduller": ["pt", "pt_site", "pt_sunucu", "pt_beslenme", "pt_bls", "pt_form", "pt_hareket", "pt_hizli", "pt_ilk", "pt_kanit", "pt_kart",
                 "pt_kitaplik", "pt_koc", "pt_oneri", "pt_oyun", "pt_programlar", "pt_push", "pt_rota", "pt_saglik", "pt_ses", "pt_sohbet",
                 "pt_storyboard", "pt_anatomi", "pt_yemek", "pt_youtube", "claude_yaz", "ortak", "gizli", "sizinti"],
    "static": ["pt.html", "pt-sw.js", "pt.webmanifest", "pt-ikon-180.png", "pt-ikon-192.png", "pt-ikon-512.png", "pt-ikon-512-maskable.png", "logo/pt.svg"],
    "dosyalar": ["LICENSE", "pytest.ini", "tests/test_pt_oyun.py"],
    "kopya": [f"pt_medya/{a}" for a in PT_MEDYA_JSON] + ["modeller/bls/bls.json"],
    "sablon": "disa/pt",
    "requirements_cikar": [],
    "requirements": "flask\nrequests\npillow\nnumpy\npyobjc-framework-Vision\npytest\n",
    "komut": ("", "PT.command"),
}


# ----------------------------------------------------------------------------- Content (2026-10-29)
URUNLER["content"] = {
    "ad": "Content",
    "parcalar": [],
    "moduller": ["content", "content_site", "content_sunucu", "content_yontem", "content_kanit", "content_araclar", "content_dogrulama",
                 "content_test", "claude_yaz", "goruntu", "sesnot", "ortak", "gizli", "sizinti"],
    "static": ["content.html", "logo/content.svg"],
    "dosyalar": ["LICENSE", "pytest.ini"],
    "sablon": "disa/content",
    "requirements_cikar": [],
    "requirements": "yt-dlp[default,curl-cffi]\nflask\nrequests\npillow\nmlx-whisper\nscenedetect==0.7.2\nopencv-python-headless\n"
                    "pyobjc-framework-Vision\npyobjc-framework-Quartz\npytest\n",
    "komut": ("", "Content.command"),
    "mimari": False,
}


# ----------------------------------------------------------------------------- Meet (2026-10-29)
# Modüller elle sayılmaz: parçaların ve modüllerin içe aktardığı yerel modüllerin kapanışı (_kapanis). Kardeş ürünlerin modülleri (Ghost, Content,
# Couple, PT, Atölye) alınmaz; Meet kodunda onları çağıran yerler try/except ya da globals() denetimiyle korunur (testler ve açılış denemesi bunu sınar).
MEET_HARIC = re.compile(r"^(atolye|content|couple|pt|ghost_)|^(paylasim|kesif|karisim|tetik|konu_toplantisi|fikir_kartlari|reklam_arsivi|oranlar|"
                        r"hesaplar|performans|yerimleri|bultenler|abonelik|kantan|seckiler|teslim|ghost)$")
URUNLER["meet"] = {
    "ad": "Meet",
    "parcalar": ["00_baslangic", "01_yardimcilar", "02_isci", "03_video_isleri", "04_toplanti", "05_asana", "07_cekirdek", "07_meet", "08_canli",
                 "09_cekirdek", "09_meet", "10_sayfalar", "11_ozellik_sayaci", "12_api", "14_haftalik", "16_altyapi_ve_meet", "16_meet",
                 "17_disa_aktarim", "18_indirilenler", "20_meet_gelisim", "22_misafir", "23_misafir_meet", "24_guvenlik", "25_sahip_uzak",
                 "27_meet_altyazi", "28_meet_devam", "29_meet_saglik", "30_kayit_disi", "31_yazi_dili", "33_kayit_bekci"],
    "kapanis": ["site", "transkript", "canli", "canli_asistan", "sesnot", "duman_testi", "yeniden_baslat", "sizinti", "disa_depo", "yedek",
                "geri_yukle", "videohub_mcp", "isimlendir", "takip", "dolgu", "studio_duzelt"],
    "moduller": [],
    "static": ["index.html", "meet_ek.js", "meet_ek.css", "misafir.js", "misafir_meet.js", "sahip_uzak.js", "dil.js", "dil", "manifest.webmanifest",
               "note.webmanifest", "note-ikon-180.png", "note-ikon-192.png", "note-ikon-512.png", "note-ikon-512-maskable.png", "ikon-180.png",
               "ikon-192.png", "ikon-512.png", "ikon-512-maskable.png", "il", "logo", "ikon"],
    "dosyalar": ["requirements.txt", "pytest.ini", "LICENSE", "ayarlar.ornek.json", ".gitignore", "kaydedici/kaydedici.swift", "kaydedici/Info.plist",
                 "uzanti", "tests/conftest.py", "tests/test_birimler.py", "tests/test_site.py", "tests/test_yedek.py", "tests/test_meet_acil.py",
                 "tests/test_meet_altyazi.py", "tests/test_meet_bekleme.py", "tests/test_meet_devam.py", "tests/test_meet_gelisimim.py",
                 "tests/test_meet_kayit_disi.py", "tests/test_kayit_bekci.py"],
    "sablon": "disa/meet",
    "requirements_cikar": ["python-pptx", "scenedetect", "opencv-python-headless", "pywebpush", "auto-editor", "shazamio"],
    "komut": ("", "Meet.command"),
    "son": "_meet_son",
}


def _meet_son(hedef):
    """Meet deposunun Chrome uzantısı yalnız toplantı işini yapar: Ghost'un X/Instagram okuyucuları ve Atölye/Content sağ tık menüleri çıkar
    (kullanıcıya X ve Instagram izni sorulmasın). Kaynaktaki işaretler değişirse kesim burada durur (sessizce yarım uzantı çıkmasın)."""
    import json as _json
    u = hedef / "uzanti"
    m = _json.loads((u / "manifest.json").read_text(encoding="utf-8"))
    m["name"] = "Meet"
    m["description"] = ("Meet for Google Meet, Teams and Zoom on the web: tells the local Meet app when you are in a call, who is there and "
                        "who is speaking (from captions); side panel with prep notes, live suggestions, notes and summary. Talks only to Meet on this Mac.")
    m["permissions"] = [x for x in m["permissions"] if x != "contextMenus"]
    m["host_permissions"] = [x for x in m["host_permissions"] if not any(k in x for k in ("x.com", "instagram", ":8767"))]
    m["content_scripts"] = [c for c in m["content_scripts"] if not set(c["js"]) & {"x.js", "ig.js"}]
    (u / "manifest.json").write_text(_json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for f in ("x.js", "ig.js"):
        (u / f).unlink(missing_ok=True)
    b = (u / "background.js").read_text(encoding="utf-8")
    i, j = b.index("// ---- Creator atölyesi"), b.index("// ---- Kendini iyileştirme")
    b = b[:i] + b[j:]
    b = "\n".join(l for l in b.splitlines() if not l.lstrip().startswith(("if (m.tur === 'x_", "if (m.tur === 'ig_", "async function hesaplarAl()",
                                                                           "chrome.alarms.create('hesaplar'")))
    b = b.replace(" if (a.name === 'hesaplar') hesaplarAl();", "")
    assert "hesaplarAl" not in b and "contextMenus" not in b, "uzantı: Ghost/Atölye kalıntısı"
    (u / "background.js").write_text(b + "\n", encoding="utf-8")
    gi = hedef / ".gitignore"
    if "!uzanti/ikonlar/*.png" not in gi.read_text(encoding="utf-8"):
        gi.write_text(gi.read_text(encoding="utf-8") + "!uzanti/ikonlar/*.png\n", encoding="utf-8")


# ----------------------------------------------------------------------------- Ghost (2026-10-29)
# Ghost + yazıya dökme motoru (video ve podcast linklerinden taslak için). Meet, Content, Couple, PT, Atölye modülleri alınmaz; Ghost'un bunları
# çağıran yerleri try/except ile korunur. Kişiye özel kaynaklar, konular ve ses kodda değil: ilk açılışta kullanıcı kurar (ghost_kurulum.py).
GHOST_HARIC = re.compile(r"^(atolye|content|couple|pt|pt_|meet_|danisman|kisaca|sinyaller|onbrifing|canli|davetler|karar_zinciri|toplanti_kapisi|"
                         r"gorevler|sozler|kisiler|tarifler|sesli_ozet|teslim|sirketler)")
URUNLER["ghost"] = {
    "ad": "Ghost",
    "parcalar": ["00_baslangic", "01_yardimcilar", "02_isci", "03_video_isleri", "07_cekirdek", "07_ghost", "09_cekirdek", "10_sayfalar",
                 "11_ozellik_sayaci", "12_api", "16_altyapi_ve_meet", "17_disa_aktarim", "18_indirilenler", "19_ghost_gelisim", "24_guvenlik",
                 "32_ghost_kurulum"],
    "kapanis": ["site", "transkript", "sesnot", "duman_testi", "yeniden_baslat", "sizinti", "yedek", "geri_yukle", "isimlendir", "takip",
                "ghost_kurulum", "paylasim", "kesif", "karisim", "tetik", "konu_toplantisi", "fikir_kartlari", "hesaplar", "performans", "yerimleri",
                "ghost_blog", "ghost_defter", "ghost_gelisim", "ghost_hikaye", "ghost_kaynak", "ghost_kendi", "ghost_rehber", "ghost_tempo", "ghost_yanit",
                "abonelik", "bultenler", "kantan", "seckiler", "reklam_arsivi", "oranlar", "dil_cevir"],
    "haric": GHOST_HARIC,
    "moduller": [],
    "static": ["index.html", "ghost_tek.html", "dil.js", "dil", "manifest.webmanifest", "ikon-180.png", "ikon-192.png", "ikon-512.png",
               "ikon-512-maskable.png", "il", "logo", "ikon"],
    "dosyalar": ["requirements.txt", "pytest.ini", "LICENSE", "uzanti/x.js", "uzanti/ig.js", "uzanti/ikonlar",
                 "tests/conftest.py", "tests/test_birimler.py", "tests/test_site.py", "tests/test_ghost_tempo.py", "tests/test_ghost_kurulum.py"],
    "sablon": "disa/ghost",
    "requirements_cikar": ["python-pptx", "scenedetect", "opencv-python-headless", "pywebpush", "auto-editor", "shazamio", "segno"],
    "komut": ("", "Ghost.command"),
}


def _kapanis(parcalar, tohum, haric=MEET_HARIC):
    """Parçaların ve tohum modüllerin içe aktardığı yerel modüllerin kapanışı (kardeş ürün modülleri hariç)."""
    yerel = {p.stem for p in KOK.glob("*.py")}
    desen = re.compile(r"^\s*(?:import\s+([\w, ]+)|from\s+(\w+)\s+import)|__import__\(\s*[\"'](\w+)|import_module\(\s*[\"'](\w+)", re.M)

    def ithal(s):
        out = set()
        for m in desen.finditer(s):
            if m.group(1):
                out |= {x.strip().split(" as ")[0].split(".")[0] for x in m.group(1).split(",")}
            out |= {g for g in m.groups()[1:] if g}
        return {x for x in out if x in yerel and not haric.search(x)}
    kuyruk = [m for p in parcalar for m in ithal((KOK / "sunucu" / f"{p}.py").read_text(encoding="utf-8"))] + [t for t in tohum if t in yerel]
    gor = set()
    while kuyruk:
        m = kuyruk.pop()
        if m not in gor:
            gor.add(m); kuyruk += list(ithal((KOK / f"{m}.py").read_text(encoding="utf-8")))
    return sorted(gor)


def medya_paketi(hedef_zip, log=print):
    """PT'nin görsel ve ses paketi (git dışı; GitHub sürümüne konur). Kök JSON'lar depoda olduğu için pakete girmez."""
    import zipfile
    kaynak = KOK / "pt_medya"
    n = 0
    with zipfile.ZipFile(hedef_zip, "w", zipfile.ZIP_STORED) as z:
        for f in sorted(kaynak.rglob("*")):
            rel = f.relative_to(kaynak)
            if not f.is_file() or (f.suffix == ".json" and len(rel.parts) == 1) or any(x in PT_MEDYA_HARIC for x in rel.parts) \
                    or rel.name.startswith(("_kontrol", "_ok")) or f.name == ".DS_Store":
                continue
            z.write(f, rel.as_posix()); n += 1
    log(f"{n} dosya → {hedef_zip} ({Path(hedef_zip).stat().st_size / 1e6:.0f} MB)")
    return hedef_zip

def _mimari(urun):
    s = (KOK / "docs" / "MIMARI.md").read_text(encoding="utf-8")
    # ürün bölümünden yalnız bu ürün ve motor kalır
    a = s.find("## Ürünler"); b = s.find("## Veri")
    if a > 0 and b > a:
        satirlar, tut = [], False                         # bir madde ve devam satırları birlikte kalır ya da çıkar
        for l in s[a:b].splitlines():
            if l.startswith("## "):
                satirlar.append(l); tut = False
            elif l.startswith("- "):
                tut = l.startswith(f"- **{URUNLER[urun]['ad']}**")
                if tut:
                    satirlar.append(l)
            elif l.startswith("  ") and tut:
                satirlar.append(l)
        s = s[:a] + "\n".join(satirlar) + "\n\n" + s[b:]
    return s.replace("Altı ürün, tek sunucu süreci, ortak motor.", f"{URUNLER[urun]['ad']} ve ortak motor; kardeş ürünler kurulu değilse kapalıdır.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "pt-medya":
        medya_paketi(sys.argv[2]); raise SystemExit(0)
    if len(sys.argv) < 3 or sys.argv[1] not in URUNLER:
        raise SystemExit(__doc__)
    h = kes(sys.argv[1], sys.argv[2])
    dogrula(h)

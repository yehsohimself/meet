# sunucu/07_cekirdek.py — ortak çekirdek: indirme aracının (yt-dlp) güvenli güncellemesi ve açılışta yarım işlerin yüklenmesi (2026-10-29:
# 07_ghost.py'den ayrıldı; Ghost'suz kurulumlarda, ör. herkese açık Studio deposunda, bunlar hiç çalışmıyordu).
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.


def _guncelleme_kontrol():
    """Haftada bir indirme aracını sessizce güncelle."""
    try:
        if GUNCELLEME_IZI.exists() and time.time() - GUNCELLEME_IZI.stat().st_mtime < 7 * 86400:
            return
        _guncelle()
    except Exception:  # noqa: BLE001
        pass


def _ytdlp_surum():
    try:
        return subprocess.run([PYTHON, "-m", "yt_dlp", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _ytdlp_dene():
    """Yeni sürüm gerçekten çalışıyor mu: kısa ve kalıcı bir YouTube videosunun bilgisi ve ses biçimleri okunabiliyor mu."""
    try:
        r = subprocess.run([PYTHON, "-m", "yt_dlp", "-q", "--no-playlist", "--simulate", "--print", "%(id)s|%(format_id)s", "-f", "bestaudio",
                            "https://www.youtube.com/watch?v=jNQXAC9IVRw"], capture_output=True, text=True, timeout=120, env=_env())
        return r.returncode == 0 and r.stdout.startswith("jNQXAC9IVRw|")
    except Exception:  # noqa: BLE001
        return False


def _guncelle():
    """yt-dlp'yi günceller; yeni sürüm denemeden geçmezse eski sürüme geri döner (2026-10-19: bozuk bir sürüm bütün indirmeleri
    durdurabilirdi)."""
    uv = Path.home() / ".local" / "bin" / "uv"
    if not uv.exists():
        return False, "uv bulunamadı"
    eski = _ytdlp_surum()
    p = subprocess.run([str(uv), "pip", "install", "--python", PYTHON, "--only-binary", ":all:", "-U", "yt-dlp"],
                       capture_output=True, text=True, timeout=300, env=_env())
    GUNCELLEME_IZI.touch()
    yeni = _ytdlp_surum()
    if p.returncode == 0 and yeni != eski and eski and not _ytdlp_dene():
        subprocess.run([str(uv), "pip", "install", "--python", PYTHON, "--only-binary", ":all:", f"yt-dlp=={eski}"],
                       capture_output=True, text=True, timeout=300, env=_env())
        print(f"yt-dlp {yeni} denemeden geçmedi; {eski} sürümüne geri dönüldü", flush=True)
        return False, [f"Yeni sürüm ({yeni}) çalışmadı; eski sürüme ({eski}) geri dönüldü"]
    return p.returncode == 0, (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]


_yukle()

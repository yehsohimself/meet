# sunucu/08_canli.py — canlı yazıya dökme.
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.
# ----------------------------------------------------------------------------- canlı yazıya dökme (süren kayıt)
CANLI = KAYIT / ".canli"
CANLI_SCRIPT = KLASOR / "canli.py"
canli_surecler = {}          # kayıt adı -> Popen


def _canli_dongu():
    """kayitlar/ içinde büyümekte olan toplantı kaydı varsa canli.py'yi başlatır (ayar: oto_kayit)."""
    while True:
        try:
            if ayarlar_oku().get("oto_kayit", True) and KAYIT.exists():
                simdi = time.time()
                for yol in KAYIT.glob("Toplantı *.m4a"):
                    if yol.name.endswith(".mik.m4a"):            # yalnızca mikrofon kanalı; asıl kayıt ayrıca işleniyor
                        continue
                    ad = yol.stem
                    st = yol.stat()
                    if st.st_size < 20000 or simdi - st.st_mtime < 0:
                        continue
                    durum_var = (CANLI / f"{ad}.json").exists()
                    if simdi - st.st_mtime > 30 and not (durum_var and simdi - st.st_mtime < 15 * 60):
                        continue                                   # büyümüyor; yalnızca yarım kalmış canlı durum varsa bitirmek için aç
                    p = canli_surecler.get(ad)
                    if p is not None and p.poll() is None:
                        continue
                    durum = CANLI / f"{ad}.json"
                    if durum.exists():
                        try:
                            dv = json.loads(durum.read_text(encoding="utf-8"))
                        except Exception:  # noqa: BLE001
                            dv = {}
                        if dv.get("bitti"):
                            continue                               # bu kayıt bitmiş
                        if simdi - dv.get("guncelleme", 0) < 45:
                            continue                               # başka bir süreç (ör. site yeniden başlamadan önceki) hâlâ işliyor
                    CANLI.mkdir(parents=True, exist_ok=True)
                    log_dosya = open(CANLI / f"{ad}.log", "a", encoding="utf-8")
                    canli_surecler[ad] = subprocess.Popen([PYTHON, "-u", str(CANLI_SCRIPT), str(yol), str(durum)],
                                                          stdout=log_dosya, stderr=subprocess.STDOUT, cwd=str(KLASOR), env=_env())
                    print(f"Canlı yazıya dökme başladı: {ad}", flush=True)
                # Uzantının parça göndermeden bıraktığı boş kayıtlar (10 dk'dan eski)
                for eski in KAYIT.glob("*.webm"):
                    try:
                        if eski.stat().st_size == 0 and simdi - eski.stat().st_mtime > 600:
                            eski.unlink(missing_ok=True); eski.with_suffix(".json").unlink(missing_ok=True)
                    except Exception:  # noqa: BLE001
                        pass
                # Eski durum dosyalarını temizle (2 gün)
                for d in CANLI.glob("*.json") if CANLI.exists() else []:
                    if simdi - d.stat().st_mtime > 2 * 86400:
                        d.unlink(missing_ok=True); (CANLI / (d.stem + ".log")).unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            print(f"canlı döngü hatası: {e}", flush=True)
        time.sleep(10)



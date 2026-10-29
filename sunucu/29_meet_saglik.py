# Meet: toplantı sağlık özeti (2026-10-28; kullanıcı onayladı: "acil paket"). Toplantı sonrası akış bitince meet_gelisim.toplanti_saglik:
# ses var mı, kayıtta boşluk, kayıt erken bitti mi (altyazı sürmüş mü), uzantı/altyazı geldi mi, adsız kişi, Kısaca ve modeli, Drive, e-posta,
# Asana → veri["saglik"]; hata ya da uyarı varsa bildirim. 30 dk sonra bir kez daha bakılır: toplantı kayıttan sonra sürdüyse altyazısı o zaman gelmiş olur.
_toplanti_bitir_saglik_once = _toplanti_bitir


def _toplanti_bitir(is_):   # noqa: F811 — akış aynı; sonuna sağlık özeti
    sonuc = _toplanti_bitir_saglik_once(is_)
    if not is_.get("misafir") and is_.get("temel"):
        try:
            _meet_saglik_yaz(is_, bildir=True)
        except Exception as e:  # noqa: BLE001
            print(f"Toplantı sağlık özeti yazılamadı: {e}", flush=True)
        t = threading.Timer(1800, _meet_saglik_sonra, args=(is_.get("id"), is_.get("temel")))
        t.daemon = True; t.start()
    return sonuc


def _meet_saglik_yaz(is_, bildir=False, onceki=None):
    import kayit_json
    import meet_gelisim
    temel = is_["temel"]; js = KLASOR / f"{temel}.json"
    if not js.exists():
        return None
    d = json.loads(js.read_text(encoding="utf-8")); v = d["veri"]
    if not v.get("toplanti") or v.get("onay_bekliyor"):
        return None
    baska = [float(x.get("kayit_baslangic") or 0) for x in list(isler.values()) if x.get("toplanti") and x.get("id") != is_.get("id") and x.get("kayit_baslangic")]
    s = meet_gelisim.toplanti_saglik(v, d.get("segmentler") or [], is_, ayar=ayarlar_oku(), baska_kayitlar=baska)

    def yaz(dd):
        dd["veri"]["saglik"] = s
    kayit_json.guncelle(js, yaz)
    yeni = [m for m in s["maddeler"] if m["seviye"] in ("hata", "uyari") and m["kod"] not in (onceki or set())]
    if bildir and yeni:
        ad = re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2} · ", "", v.get("baslik") or "").split(" · ")[0]
        _bildir(("Toplantı kaydında sorun" if any(m["seviye"] == "hata" for m in yeni) else "Toplantı notları · dikkat") + (f" · {ad}" if ad else ""),
                yeni[0]["metin"] + (f" (+{len(yeni) - 1} not daha)" if len(yeni) > 1 else ""), url=_meet_url(temel))
        try:
            meet_gelisim.olay("uyari", f"{ad or temel}: {yeni[0]['metin']}", temel)
        except Exception:  # noqa: BLE001
            pass
    return s


def _meet_saglik_sonra(is_id, temel):
    """30 dk sonra: yalnız yeni çıkan sorunlar (ör. toplantı kayıttan sonra sürdü) bildirilir."""
    try:
        is_ = isler.get(is_id) or {"id": is_id, "temel": temel}
        js = KLASOR / f"{temel}.json"
        if not js.exists():
            return
        onceki = {m["kod"] for m in (json.loads(js.read_text(encoding="utf-8"))["veri"].get("saglik") or {}).get("maddeler") or []}
        _meet_saglik_yaz(is_, bildir=True, onceki=onceki)
    except Exception as e:  # noqa: BLE001
        print(f"Toplantı sağlık özeti (ikinci bakış): {e}", flush=True)

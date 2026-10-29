"""karar_zinciri.py - Kararların toplantılar arası zinciri (2026-10-23, ChatGPT brifi Meet 2).

Bir toplantıda alınan karar, aynı müşteri/şirketle önceki bir toplantının kararını değiştirdiyse, geri aldıysa ya da yeniden onayladıysa bunu iki
toplantıya da yazar: yeni kararda `zincir` (eskisine bağlantı), eski kararda `sonra` (yenisine bağlantı). Okuma ekranında "Bu karar 14 Ekim'deki
kararı değiştirdi" / "23 Ekim'de değişti" olarak görünür. Konu benzerliği yetmez: model yalnızca açık ilişkileri bağlar.

zincirle(veri, temel, kilit=None) → bağ sayısı. Kısaca kartı (veri["kisaca"]["kararlar"]) hazırlandıktan sonra çalışır.
Elle (eski toplantılar, eskiden yeniye): python karar_zinciri.py --hepsi
"""
import contextlib
import json
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
ILISKI = {"degistirdi", "geri_aldi", "teyit"}


def _tarih(t):
    return time.strftime("%Y-%m-%d", time.localtime(t)) if t else ""


def zincirle(veri, temel, kilit=None, log=print):
    import claude_yaz
    import ozet as ozet_modulu
    import sinyaller
    yeni = (veri.get("kisaca") or {}).get("kararlar") or []
    if not yeni or veri.get("misafir") or claude_yaz.MISAFIR.get():      # davetlinin kararları sahibin toplantılarıyla zincirlenmez
        return 0
    eski = []
    for t, v in sinyaller._gecmis(veri, temel, gun=180, en_cok=8):
        for j, k in enumerate((v.get("kisaca") or {}).get("kararlar") or []):
            if str(k.get("karar") or "").strip():
                eski.append({"temel": t, "j": j, "baslik": v.get("baslik") or "", "tarih": _tarih(v.get("olusturma")), "karar": k["karar"],
                             "alinti": k.get("alinti") or "", "sn": k.get("sn")})
    if not eski:
        return 0
    istem = (
        f"Toplantı: {veri.get('baslik') or ''} ({_tarih(veri.get('olusturma') or time.time())})\n"
        "Bu toplantıda alınan kararları, aynı müşteriyle ÖNCEKİ toplantılarda alınan kararlarla karşılaştır. Yalnızca AÇIK ilişkileri bağla:\n"
        "- degistirdi: yeni karar eskisinin yerine geçiyor (tarih, bütçe, kapsam, yön, sorumlu, rakam değişti)\n"
        "- geri_aldi: eskisinden vazgeçildi, iptal edildi\n"
        "- teyit: aynı karar yeniden onaylandı (yalnızca toplantıda açıkça yeniden onaylandıysa)\n"
        "Aynı konudan bahsetmek YETMEZ; iki karar aynı şeyi belirliyor olmalı. Emin değilsen bağlama. aciklama: neyin neye döndüğü, tek cümle, ≤18 kelime "
        "(ör. 'Teslim 30 Ekim'den 6 Kasım'a kaydı'). Uydurma.\n"
        'Yalnızca JSON: {"baglar": [{"yeni": 0, "eski": 3, "iliski": "degistirdi", "aciklama": "..."}]}\n\n'
        "BU TOPLANTININ KARARLARI:\n" + "\n".join(f"[Y{i}] {k.get('karar')} — \"{k.get('alinti') or ''}\"" for i, k in enumerate(yeni))
        + "\n\nÖNCEKİ KARARLAR:\n" + "\n".join(f"[E{i}] ({e['tarih']} · {e['baslik']}) {e['karar']} — \"{e['alinti']}\"" for i, e in enumerate(eski[:80])))
    with claude_yaz.toplanti():
        c = ozet_modulu._json_coz(ozet_modulu._sor(istem, json_bekle=True, num_ctx=16384, zaman_asimi=300)) or {}
    baglar = []
    for b in c.get("baglar") or []:
        try:
            i = int(str(b.get("yeni")).lstrip("Yy")); e = eski[int(str(b.get("eski")).lstrip("Ee"))]
        except (TypeError, ValueError, IndexError):
            continue
        il = str(b.get("iliski") or "")
        if il in ILISKI and 0 <= i < len(yeni):
            baglar.append((i, e, il, str(b.get("aciklama") or "").strip()[:200]))
    for k in yeni:                                              # yeniden çalışınca eski bağlar silinip yeniden yazılır
        k.pop("zincir", None)
    for i, e, il, ac in baglar:
        yeni[i].setdefault("zincir", []).append({"iliski": il, "temel": e["temel"], "baslik": e["baslik"], "tarih": e["tarih"], "karar": e["karar"],
                                                 "sn": e["sn"], "aciklama": ac})
    # Eski toplantıya geri bağlantı (degistirdi / geri_aldi: eski karar artık geçerli değil; teyit: hâlâ geçerli)
    eskiler = {}
    for i, e, il, ac in baglar:
        eskiler.setdefault(e["temel"], []).append((e["j"], {"iliski": il, "temel": temel, "baslik": veri.get("baslik") or "",
                                                            "tarih": _tarih(veri.get("olusturma") or time.time()), "karar": yeni[i].get("karar"),
                                                            "sn": yeni[i].get("sn"), "aciklama": ac}))
    for t, L in eskiler.items():
        yol = KLASOR / f"{t}.json"
        with (kilit or contextlib.nullcontext()):
            try:
                d = json.loads(yol.read_text(encoding="utf-8"))
                kk = (d["veri"].get("kisaca") or {}).get("kararlar") or []
                for j, s in L:
                    if j < len(kk):
                        kk[j]["sonra"] = [x for x in kk[j].get("sonra") or [] if x.get("temel") != temel] + [s]
                yol.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception as ex:  # noqa: BLE001
                log(f"      Karar zinciri: {t} güncellenemedi ({ex})")
    veri.setdefault("kisaca", {})["zincir_zaman"] = time.time()
    if baglar:
        log(f"      Karar zinciri: {len(baglar)} karar önceki toplantılara bağlandı")
    return len(baglar)


def hepsi(gun=120):
    """Eski toplantılar, eskiden yeniye (her biri yalnızca kendinden öncekilere bakar)."""
    L = []
    for js in KLASOR.glob("transkript_*.json"):
        try:
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
        except Exception:  # noqa: BLE001
            continue
        if v.get("toplanti") and not v.get("onay_bekliyor") and (v.get("kisaca") or {}).get("kararlar") and (v.get("olusturma") or 0) > time.time() - gun * 86400:
            L.append((v.get("olusturma") or 0, js))
    for _, js in sorted(L):
        d = json.loads(js.read_text(encoding="utf-8"))           # zincirle yalnızca ÖNCEKİ dosyalara yazar; bu dosya taze okunur
        n = zincirle(d["veri"], js.stem)
        js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{d['veri'].get('baslik')}: {n} bağ", flush=True)


if __name__ == "__main__":
    if "--hepsi" in sys.argv:
        hepsi()
    else:
        js = Path(sys.argv[1])
        d = json.loads(js.read_text(encoding="utf-8"))
        print(zincirle(d["veri"], js.stem), "bağ")
        js.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

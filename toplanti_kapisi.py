"""toplanti_kapisi.py - Kayıt gerçekten bir iş toplantısı mı? (2026-10-22; kullanıcı: "saçma bir kayıtsa toplantı olmadığını anlayıp listeye
eklemeyebilirsin; hatta bana sor, kabul edersem ekle"). 21 Ekim'de maç izlerken yapılan bir arkadaş sohbeti ("IK 18") toplantı diye bir şirkete dosyalanmıştı.

Kural: takvimde bir görüşmeyle eşleşen kayıt toplantıdır (soru sorulmaz). Diğerlerinde Claude (sonnet, toplantı izniyle) kısa bir değerlendirme yapar:
{toplanti, tur, guven, neden}. "Değil" ve güven ≥ 0,65 ise kayıt listeye girmez; kullanıcı onaylarsa toplantı akışı (şirket, Kısaca, danışman, notlar,
Drive, görevler) o zaman çalışır. Claude yoksa ya da hata verirse kayıt toplantı sayılır (hiçbir şey kaybolmasın).
"""
import re

ESIK = 0.65


def _orneklem(segmentler, kelime=2200):
    """Baştan, ortadan ve sondan parçalar (yalnızca baş yanıltıcı olabilir: toplantıdan önceki sohbet)."""
    s = [x.get("metin", "") for x in segmentler or []]
    if not s:
        return ""
    n = len(s); parca = lambda a, b: " ".join(s[a:b])   # noqa: E731
    metin = parca(0, n // 3)[: kelime * 3] + "\n…\n" + parca(n // 3, 2 * n // 3)[: kelime * 2] + "\n…\n" + parca(2 * n // 3, n)[: kelime * 2]
    return " ".join(metin.split()[:kelime])


def degerlendir(veri, segmentler, log=print):
    if veri.get("takvim"):
        return {"toplanti": True, "guven": 0.95, "tur": "is_toplantisi", "neden": "Takvimdeki bir görüşmeyle eşleşti."}
    kelime = sum(len(str(x.get("metin", "")).split()) for x in segmentler or [])
    if kelime < 40:
        return {"toplanti": False, "guven": 0.9, "tur": "bos", "neden": "Kayıtta neredeyse hiç konuşma yok."}
    try:
        import claude_yaz
        with claude_yaz.toplanti():
            if not claude_yaz.hazir():
                return {"toplanti": True, "guven": 0.0, "tur": "bilinmiyor", "neden": ""}
            kisiler = sorted({str(a) for a in (veri.get("etiket") or {}).values()})
            c = claude_yaz.sor_json(
                "Aşağıdaki ses kaydı otomatik olarak 'toplantı' diye kaydedildi (bilgisayarda mikrofon ve bir görüşme uygulaması açıktı). Bu gerçekten "
                "bir İŞ TOPLANTISI mı (müşteri, ekip, ajans, iş görüşmesi, sunum provası, iş üzerine telefon görüşmesi)? Yoksa toplantı OLMAYAN bir şey mi: "
                "arkadaş/aile sohbeti, maç ya da dizi izlerken konuşma, video/yayın/podcast sesi, tek kişinin kendi kendine konuşması, boş/gürültülü kayıt?\n"
                "Emin değilsen toplanti=true de (yanlışlıkla bir iş toplantısını kaybetmek, fazladan sormaktan daha kötü).\n"
                'JSON: {"toplanti": true, "tur": "is_toplantisi|ozel_sohbet|video_yayin|tek_kisi|bos", "guven": 0.0-1.0, "neden": "kullanıcıya tek cümle, sade Türkçe"}\n\n'
                f"Pencere/sekme başlığı: {veri.get('baslik') or '-'}\nUygulama: {veri.get('uygulama') or '-'}\nKonuşmacılar: {', '.join(kisiler) or '-'}\n"
                f"Süre: {round((veri.get('sure') or 0) / 60)} dk\n\nKONUŞMADAN PARÇALAR:\n{_orneklem(segmentler)}", model_adi="sonnet", zaman_asimi=180)
    except Exception as e:  # noqa: BLE001
        log(f"      Toplantı kapısı değerlendiremedi ({e}); toplantı sayıldı")
        return {"toplanti": True, "guven": 0.0, "tur": "bilinmiyor", "neden": ""}
    try:
        g = float(c.get("guven") or 0)
    except (TypeError, ValueError):
        g = 0.0
    sonuc = {"toplanti": bool(c.get("toplanti", True)), "guven": max(0.0, min(1.0, g)), "tur": str(c.get("tur") or "")[:30],
             "neden": re.sub(r"\s+", " ", str(c.get("neden") or ""))[:240]}
    log(f"      Toplantı kapısı: {'toplantı' if sonuc['toplanti'] else 'toplantı değil'} ({sonuc['tur']}, güven {sonuc['guven']:.2f}) {sonuc['neden'][:90]}")
    return sonuc


def sorulmali(sonuc):
    return bool(sonuc) and not sonuc.get("toplanti") and (sonuc.get("guven") or 0) >= ESIK

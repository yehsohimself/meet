"""sohbet.py - Tek bir toplantıyla (ya da videoyla) sohbet (2026-10-20). Kullanıcı toplantı sayfasında Claude'la konuşur gibi soru sorar:
"Ayşe bütçe için tam ne demişti?", "Kim neyi üstlendi?". Her soruda transkriptin tamamı (zaman + konuşmacı), özet, notlar ve kullanıcının kendi
notları + son 12 mesajlık konuşma geçmişi Claude'a gider. Yanıtta alıntılar [dk:sn] zamanıyla verilir; sitede tıklanınca o ana gidilir.
Geçmiş `veri["sohbet"]` = [{rol: ben|claude, metin, zaman}] (site kilit altında yazar). Toplantı içeriği yalnızca 'Toplantılarda da Claude' açıksa.
"""
import json
import time
from pathlib import Path

GECMIS_MESAJ = 12


def _baglam(d):
    from transkript import paragrafla
    veri = d["veri"]
    etiket = {str(k): v for k, v in (veri.get("etiket") or {}).items()}
    par = paragrafla(d["segmentler"], etiket)
    metin = "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in par)
    ek = []
    o = veri.get("ozet") or {}
    if isinstance(o, dict) and o.get("ozet"):
        ek.append("ÖZET: " + o["ozet"])
    n = veri.get("notlar") or {}
    if n.get("yapilacaklar"):
        ek.append("YAPILACAKLAR (notlardan): " + "; ".join(f"{y.get('is')} ({y.get('kim') or 'sahibi belirsiz'})" for y in n["yapilacaklar"] if isinstance(y, dict)))
    try:
        import notlarim
        ek.append(notlarim.istem_ek(veri).strip())
    except Exception:  # noqa: BLE001
        pass
    tarih = time.strftime("%d.%m.%Y", time.localtime(veri.get("olusturma") or time.time()))
    kisiler = ", ".join(sorted({p["ad"] for p in par}))
    return (f"BAŞLIK: {veri.get('baslik') or ''}\nTARİH: {tarih}\nKONUŞMACILAR: {kisiler}\n" + "\n".join(x for x in ek if x)
            + "\n\nTRANSKRİPT ([dk:sn] Konuşmacı: söz):\n" + metin[:260000])


def cevapla(json_yolu, soru, gecmis=None):
    """Döner: yanıt metni (markdown). Hata: RuntimeError (kullanıcıya gösterilebilir Türkçe)."""
    return "".join(cevapla_akis(json_yolu, soru, gecmis))


def cevapla_akis(json_yolu, soru, gecmis=None):
    """Yanıtı yazıldıkça parça parça verir (üreteç)."""
    import claude_yaz
    d = json.loads(Path(json_yolu).read_text(encoding="utf-8"))
    toplanti = bool(d["veri"].get("toplanti"))
    if not claude_yaz.hazir(toplanti_icerik=toplanti):
        if claude_yaz.MISAFIR.get():
            raise RuntimeError("Bu özellik için Hesabınız’dan (sağ üstteki dişli) Claude anahtarınızı ekleyin.")
        raise RuntimeError("Claude şu an kullanılamıyor (giriş yok, abonelik sınırı ya da Ayarlar'da toplantılarda Claude kapalı).")
    try:
        m = claude_yaz.MISAFIR.get()                         # davetli: kendi adı
        ben = ((m.get("ad") or "") if m else (json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8")).get("benim_adim") or "")).split()[0]
    except Exception:  # noqa: BLE001
        ben = ""
    tur = "toplantı" if toplanti else "video"
    konusma = "\n".join(f"{'KULLANICI' if m.get('rol') == 'ben' else 'SEN'}: {m.get('metin', '')}" for m in (gecmis or [])[-GECMIS_MESAJ:])
    sistem = (f"Sen bu {tur}yu baştan sona dinlemiş, titiz ve samimi bir asistansın. Kullanıcıyla ({ben or 'kullanıcı'}) sohbet ediyorsun. "
              "Kurallar: Yalnızca aşağıdaki transkripte ve notlara dayan; orada yoksa açıkça 'bu konuşulmadı' ya da 'transkriptte yok' de, uydurma. "
              "Birinin ne dediği sorulursa sözünü kısa alıntıyla ver ve zamanını [dk:sn] biçiminde yaz (ör. [12:34]); her önemli bilginin yanına zaman ekle. "
              "Doğal, kısa Türkçe; önce doğrudan yanıt, sonra gerekirse kısa maddeler. Başlık ya da 'İşte' gibi giriş yazma. ")
    if ben:
        sistem += f"Kullanıcının kendisi transkriptte '{ben}' adıyla geçebilir; ona 'siz' diye hitap et."
    istem = (_baglam(d) + ("\n\nŞİMDİYE KADARKİ SOHBET:\n" + konusma if konusma else "") + f"\n\nKULLANICININ YENİ SORUSU: {soru}")
    with claude_yaz.toplanti() if toplanti else _bos():
        try:
            yield from claude_yaz.sor_akis(istem, sistem, zaman_asimi=300)
        except claude_yaz.ClaudeHata as e:
            raise RuntimeError(f"Claude yanıt veremedi: {e}") from e


class _bos:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

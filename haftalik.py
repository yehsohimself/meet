"""haftalik.py - Claude ile toplu özetler ve toplantıdan belgeler.

- takip_ozeti(gun=7): takip edilen kanallardan son N günde gelen videoların tek sayfalık özeti (ne konuşuldu, kim neyi iddia etti,
  ayrışan görüşler, dikkat çeken rakamlar, izlenmeye değer olanlar).
- musteri_ozeti(gun=7): son N gündeki toplantılar müşteri müşteri: bu hafta, kararlar, açık işler, bekleyen sorular, sonraki adım.
  Pazartesi sabahı site kendiliğinden hazırlar ve e-postayla gönderir (ayar `haftalik_eposta`).
- brief(json): toplantıdan creative brief / iş tanımı (yalnızca konuşulanlar; konuşulmayan alan "Toplantıda konuşulmadı").
- takip_epostasi(json): katılımcılara gidecek takip e-postası TASLAĞI (gönderilmez; Mail'de taslak olarak açılır).

Çıktılar ozetler/ klasöründe (.md + .docx); brief <temel>.brief.md/.docx. Toplantı içeriği Claude'a yalnızca
'Toplantılarda da Claude' ayarı açıksa gider (claude_yaz.toplanti()).
Elle: python haftalik.py takip|musteri [gün]  ·  python haftalik.py brief|eposta transkript_x.json
"""
import json
import re
import sys
import time
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
OZETLER = KLASOR / "ozetler"


def _ayar():
    import ortak                                           # tek sürüm (sırlar dahil; 2026-10-25)
    return ortak.ayar()


def _kayitlar(gun):
    """Son `gun` gündeki transkriptler: [(yol, veri)] (segmentler hariç, hızlı)."""
    sinir = time.time() - gun * 86400
    out = []
    for js in KLASOR.glob("transkript_*.json"):
        try:
            if js.stat().st_mtime < sinir - 86400:
                continue
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
            if (v.get("olusturma") or js.stat().st_mtime) >= sinir:
                out.append((js, v))
        except Exception:  # noqa: BLE001
            continue
    return sorted(out, key=lambda x: x[1].get("olusturma") or 0)


def _tarih(t):
    return time.strftime("%d.%m.%Y", time.localtime(t or time.time()))


def _kaydet(tur, baslik, md):
    """ozetler/<tur> <tarih>.md + .docx; döner: {"ad", "md", "docx", "tarih"}."""
    import marka
    from docx import Document
    from docx.shared import Cm, Pt
    OZETLER.mkdir(exist_ok=True)
    ad = f"{'Takip özeti' if tur == 'takip' else 'Müşteri özeti'} {time.strftime('%Y-%m-%d')}"
    (OZETLER / f"{ad}.md").write_text(md, encoding="utf-8")
    doc = Document()
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7); s.left_margin = s.right_margin = Cm(2.2)
    st = doc.styles["Normal"]; st.font.name = "Helvetica Neue"; st.font.size = Pt(10.5)
    marka._md_docx(doc, md)
    doc.save(OZETLER / f"{ad}.docx")
    kayit = {"tur": tur, "ad": ad, "baslik": baslik, "tarih": time.time()}
    dizin = OZETLER / ".dizin.json"
    try:
        liste = json.loads(dizin.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        liste = []
    liste = [x for x in liste if x.get("ad") != ad] + [kayit]
    dizin.write_text(json.dumps(liste[-60:], ensure_ascii=False, indent=1), encoding="utf-8")
    return {**kayit, "md": md}


def liste():
    try:
        return json.loads((OZETLER / ".dizin.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def oku(ad):
    yol = OZETLER / f"{ad}.md"
    return yol.read_text(encoding="utf-8") if yol.exists() and yol.parent == OZETLER else ""


def takip_ozeti(gun=7, log=print):
    import claude_yaz
    if not claude_yaz.hazir(toplanti_icerik=False):
        raise RuntimeError("Claude bağlı değil")
    videolar = [(js, v) for js, v in _kayitlar(gun) if v.get("takip") and not v.get("toplanti")]
    if not videolar:
        return None
    from transkript import paragrafla
    parcalar = []
    butce = max(1500, 60000 // len(videolar))                 # toplam ~60 bin kelime
    for n, (js, v) in enumerate(videolar, 1):
        o = v.get("ozet") or {}
        try:
            d = json.loads(js.read_text(encoding="utf-8"))
            metin = " ".join(p["metin"] for p in paragrafla(d["segmentler"], v.get("etiket") or {}))
        except Exception:  # noqa: BLE001
            metin = ""
        kel = metin.split()
        parcalar.append(f"[{n}] {v.get('baslik')} · {v.get('kanal') or (v.get('takip') or {}).get('ad', '')} · {_tarih(v.get('olusturma'))} · {v.get('link', '')}\n"
                        f"Özet: {o.get('ozet', '')}\nÖne çıkanlar: {'; '.join(o.get('maddeler') or [])}\n"
                        f"Transkript (kısaltılmış): {' '.join(kel[:butce])}")
    log(f"      {len(videolar)} video Claude ile özetleniyor...")
    istem = (f"Kullanıcı aşağıdaki YouTube kanallarını takip ediyor; son {gun} günde gelen {len(videolar)} video aşağıda (numaralı). "
             "Ona tek sayfalık, doğal Türkçeyle bir 'bu hafta ne konuşuldu' özeti yaz. Markdown biçimi:\n"
             "# Takip özeti · <tarih aralığı>\n(2-3 cümlelik genel tablo)\n## Öne çıkanlar\n- 5-8 madde: somut bilgi, iddia ya da gelişme; sonunda kaynak [n]\n"
             "## Kim ne dedi\n- kanal kanal 1-2 cümle\n## Ayrışan görüşler\n- aynı konuda farklı iddialar varsa (yoksa bu bölümü yazma)\n"
             "## Dikkat çeken rakamlar\n- (yoksa yazma)\n## İzlemeye değer\n- en çok 3 video [n] ve neden\n"
             "Kurallar: yalnızca aşağıdaki içerikten; uydurma yok; hype yok; büyük resmi gören, sakin bir ton. Tarih yazmayı başlıkla sınırla.\n\n"
             + "\n\n".join(parcalar))
    md = claude_yaz.sor(istem, "Sen kullanıcının kişisel araştırma asistanısın; kısa, yoğun ve doğal Türkçe yazarsın.", zaman_asimi=900).strip()
    md = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", md).strip()
    kaynaklar = "\n".join(f"{n}. {v.get('baslik')} — {v.get('link', '')}" for n, (_js, v) in enumerate(videolar, 1))
    md += "\n\n## Kaynaklar\n" + kaynaklar
    return _kaydet("takip", f"Takip özeti · {len(videolar)} video", md)


def musteri_ozeti(gun=7, log=print):
    import claude_yaz
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            raise RuntimeError("Claude bağlı değil ya da toplantılarda kapalı")
        toplantilar = [(js, v) for js, v in _kayitlar(gun) if v.get("toplanti")]
        if not toplantilar:
            return None
        gruplar = {}
        for js, v in toplantilar:
            gruplar.setdefault(v.get("musteri") or "Diğer", []).append(v)
        bloklar = []
        for m, liste_ in gruplar.items():
            satir = [f"### MÜŞTERİ: {m}"]
            for v in liste_:
                n = v.get("notlar") or {}
                o = v.get("ozet") or {}
                yap = n.get("yapilacaklar") or [{"is": y, "kim": "", "ne_zaman": ""} for y in (o.get("yapilacaklar") or [])]
                satir.append(f"- Toplantı: {v.get('baslik')} ({_tarih(v.get('olusturma'))}); katılımcılar: {', '.join(v.get('katilimcilar') or [])}\n"
                             f"  Bağlam: {n.get('baglam') or o.get('ozet', '')}\n"
                             f"  Kararlar: {'; '.join(n.get('kararlar') or o.get('kararlar') or [])}\n"
                             f"  Yapılacaklar: {'; '.join((y.get('is', '') + (' — ' + y['kim'] if y.get('kim') else '') + (' (' + y['ne_zaman'] + ')' if y.get('ne_zaman') else '')) for y in yap if isinstance(y, dict))}\n"
                             f"  Açık sorular: {'; '.join(n.get('acik_sorular') or [])}\n  Sonraki adımlar: {'; '.join(n.get('sonraki_adimlar') or [])}")
            bloklar.append("\n".join(satir))
        ad = _ayar().get("benim_adim") or ""
        log(f"      {len(toplantilar)} toplantı ({len(gruplar)} müşteri) Claude ile özetleniyor...")
        istem = (f"Aşağıda kullanıcının ({ad}) son {gun} gündeki toplantılarının notları müşteri müşteri var. Pazartesi sabahı okuyacağı, "
                 "doğal Türkçeyle bir haftalık müşteri özeti yaz. Markdown:\n# Haftalık müşteri özeti · <tarih aralığı>\n(2-3 cümle: haftanın genel tablosu)\n"
                 "## <Müşteri adı>\n**Bu hafta:** 2-3 cümle\n**Kararlar:**\n- ...\n**Açık işler:**\n- iş — kim (varsa tarih); kullanıcının kendi işlerini başa al\n"
                 "**Bekleyen sorular:**\n- ...\n**Sonraki adım:** tek cümle\n"
                 "Boş kalan alt başlığı yazma. Yalnızca notlardaki bilgiyi kullan; uydurma. 'Diğer' grubunu en sona koy.\n\n" + "\n\n".join(bloklar))
        md = claude_yaz.sor(istem, "Sen kullanıcının titiz iş asistanısın; kısa, net ve doğal Türkçe yazarsın.", zaman_asimi=900).strip()
    md = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", md).strip()
    return _kaydet("musteri", f"Müşteri özeti · {len(toplantilar)} toplantı", md)


def eposta_gonder(kayit):
    """Haftalık özeti kullanıcının ilk e-posta adresine gönderir (Mail). Döner: hata metni ya da ''."""
    import marka
    import notlar
    adresler = [a for a in (_ayar().get("benim_epostalar") or []) if a.strip()]
    if not adresler:
        return "Ayarlar'da e-posta adresi yok"
    konu = re.sub(r"^#\s*", "", kayit["md"].split("\n", 1)[0]).strip() or kayit["baslik"]
    return notlar.gonder(konu, marka._md_duz(kayit["md"]) + "\n\nVideo Hub", adresler[0], adresler[0])


def _veri(json_yolu):
    d = json.loads(Path(json_yolu).read_text(encoding="utf-8"))
    return d, d["veri"], d["segmentler"]


def _toplanti_metni(veri, seg):
    from transkript import paragrafla
    par = paragrafla(seg, {str(k): v for k, v in (veri.get("etiket") or {}).items()})
    return "\n".join(f"[{int(p['bas']) // 60:02d}:{int(p['bas']) % 60:02d}] {p['ad']}: {p['metin']}" for p in par)


def brief(json_yolu, log=print):
    """Toplantıdan creative brief / iş tanımı (.brief.md + .brief.docx)."""
    import claude_yaz
    import marka
    from docx import Document
    from docx.shared import Cm, Pt
    json_yolu = Path(json_yolu)
    d, veri, seg = _veri(json_yolu)
    with claude_yaz.toplanti() if veri.get("toplanti") else _bos():
        if not claude_yaz.hazir():
            raise RuntimeError("Claude bağlı değil ya da toplantılarda kapalı")
        log("      Brief Claude ile yazılıyor...")
        istem = (f"Aşağıdaki toplantıdan ({veri.get('baslik')}; müşteri: {veri.get('musteri') or 'belirsiz'}) bir ajans için creative brief / iş tanımı "
                 "belgesi çıkar. Markdown:\n# Brief: <işin adı>\n**Müşteri:** ...  \n**Tarih:** toplantı tarihi\n## Arka plan\n## Amaç\n## Hedef kitle\n"
                 "## Ana mesaj ve ton\n## Teslimatlar\n- format, adet, mecra, süre\n## Takvim\n## Bütçe\n## Sorumlular\n- kim ne yapacak\n"
                 "## Onay süreci\n## Açık sorular\n- netleşmesi gerekenler\n"
                 "Kurallar: yalnızca toplantıda konuşulanlar; konuşulmayan alanın altına tek satır 'Toplantıda konuşulmadı.' yaz; uydurma. "
                 "Doğal, net Türkçe; işle ilgili İngilizce terimleri (brief, creative, KV, packshot) olduğu gibi kullan.\n\n"
                 + (f"Toplantı notları: {json.dumps(veri.get('notlar'), ensure_ascii=False)[:6000]}\n\n" if veri.get("notlar") else "")
                 + "TRANSKRİPT:\n" + _toplanti_metni(veri, seg))
        md = claude_yaz.sor(istem, "Sen deneyimli bir ajans hesap yöneticisisin.", zaman_asimi=900).strip()
    md = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", md).strip()
    temel = json_yolu.with_suffix("")
    Path(f"{temel}.brief.md").write_text(md, encoding="utf-8")
    doc = Document()
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7); s.left_margin = s.right_margin = Cm(2.2)
    st = doc.styles["Normal"]; st.font.name = "Helvetica Neue"; st.font.size = Pt(10.5)
    marka._md_docx(doc, md)
    doc.save(f"{temel}.brief.docx")
    veri["brief"] = {"metin": md, "zaman": time.time()}
    json_yolu.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return veri["brief"]


def takip_epostasi(json_yolu, log=print):
    """Katılımcılara gidecek takip e-postası taslağı: {konu, govde, alicilar}. GÖNDERİLMEZ."""
    import claude_yaz
    json_yolu = Path(json_yolu)
    d, veri, seg = _veri(json_yolu)
    ay = _ayar()
    benim = {a.strip().lower() for a in (ay.get("benim_epostalar") or [])}
    alicilar = [k.get("eposta") for k in ((veri.get("takvim") or {}).get("katilimcilar") or [])
                if isinstance(k, dict) and k.get("eposta") and k["eposta"].lower() not in benim and "resource.calendar" not in k["eposta"]]
    with claude_yaz.toplanti():
        if not claude_yaz.hazir():
            raise RuntimeError("Claude bağlı değil ya da toplantılarda kapalı")
        log("      Takip e-postası Claude ile yazılıyor...")
        istem = (f"{ay.get('benim_adim') or 'Kullanıcı'} adına, aşağıdaki toplantının katılımcılarına gidecek kısa bir takip e-postası yaz. "
                 "Doğal, sıcak ama profesyonel Türkçe; 'siz' dili; kurumsal kalıp ve abartı yok. Yapı: kısa teşekkür + 1 cümle bağlam; "
                 "'Konuştuklarımız' (3-5 madde, somut); 'Kim ne yapacak' (madde: iş — kişi, varsa tarih); tek cümlelik sonraki adım; kapanış ve ad. "
                 "Yalnızca konuşulanlar; uydurma. Markdown kullanma; maddeler için '• '. "
                 "Yalnızca JSON: {\"konu\": \"...\", \"govde\": \"...\"}\n\n"
                 + (f"Toplantı notları: {json.dumps(veri.get('notlar'), ensure_ascii=False)[:6000]}\n\n" if veri.get("notlar") else "")
                 + f"Toplantı: {veri.get('baslik')}\nTRANSKRİPT:\n" + _toplanti_metni(veri, seg))
        c = claude_yaz.sor_json(istem, "Sen kullanıcının iş yazışmalarını hazırlayan asistanısın.", zaman_asimi=600)
    sonuc = {"konu": str(c.get("konu") or "").strip()[:200], "govde": str(c.get("govde") or "").strip(), "alicilar": alicilar, "zaman": time.time()}
    veri["takip_eposta"] = sonuc
    json_yolu.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return sonuc


class _bos:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(1)
    is_ = sys.argv[1]
    if is_ in ("takip", "musteri"):
        g = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        k = (takip_ozeti if is_ == "takip" else musteri_ozeti)(g)
        print(k["md"] if k else "Bu aralıkta içerik yok.")
    elif is_ == "brief":
        print(brief(sys.argv[2])["metin"])
    elif is_ == "eposta":
        e = takip_epostasi(sys.argv[2]); print(e["konu"]); print(e["govde"]); print("Alıcılar:", ", ".join(e["alicilar"]))

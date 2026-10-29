"""videohub_mcp.py - Video Hub'ı Claude uygulamasına bağlayan MCP sunucusu (stdio).

Claude masaüstü uygulamasında sohbet ederken kitaplığa, toplantılara, açık işlere ve haftalık özetlere erişim; yazıya dökme,
indirme, klip, çeviri ve marka içerik paketi başlatma. Okuma araçları dosyaları doğrudan okur; işlem araçları yerel
siteye (http://127.0.0.1:8765) istek gönderir. E-posta GÖNDEREN ya da silen araç YOKTUR (bilerek).

Kayıt: ~/Library/Application Support/Claude/claude_desktop_config.json → mcpServers["video-hub"] =
  {"command": "<klasör>/.venv/bin/python", "args": ["<klasör>/videohub_mcp.py"]}
Elle deneme: .venv/bin/python videohub_mcp.py --dene
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR))
SITE = "http://127.0.0.1:8765"


def _marka_kodu():
    """markalar/<kod>/stil.json dosyalarından ilki (kullanıcının içerik serisi); kodda marka adı yok (2026-10-25)."""
    d = sorted((KLASOR / "markalar").glob("*/stil.json"))
    return d[0].parent.name if d else "marka"

from mcp.server.mcpserver import MCPServer  # noqa: E402  (mcp 2.x; 1.x'teki FastMCP)

mcp = MCPServer("Video Hub", instructions=(
    "Kullanıcının yerel kitaplığı (Studio ve Meet): yazıya dökülmüş videolar ve toplantı kayıtları, özetler, kararlar, "
    "yapılacaklar, toplantı notları, haftalık özetler, marka içerik paketleri. Türkçe yanıt ver. "
    "Bir transkripte atıf yaparken başlığını ve [dakika:saniye] zamanını söyle. Toplantı içerikleri gizlidir; yalnızca "
    "kullanıcıyla konuşurken kullan. İşlem başlatan araçlar (yaziya_dok, indir, klip_olustur, cevir, finansal_terapi_paketi) "
    "uzun sürebilir; başlattıktan sonra isler() ile durumu gösterebilirsin. Creator atölyesi: atolye_calismalari, atolye_oku, "
    "atolye_baslat, atolye_akis_degistir."))


# ----------------------------------------------------------------------------- yardımcılar
def _api(yol, govde=None, yontem=None):
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    req = urllib.request.Request(SITE + yol, data=veri, method=yontem or ("POST" if govde is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:  # noqa: BLE001
            return {"hata": f"HTTP {e.code}"}
    except urllib.error.URLError:
        return {"hata": "Video Hub sitesine ulaşılamadı (http://127.0.0.1:8765 kapalı olabilir)."}


def _oku(temel):
    if not re.match(r"^[\w\-]+$", temel or ""):
        raise ValueError("Geçersiz transkript adı")
    js = KLASOR / f"{temel}.json"
    if not js.exists():
        raise ValueError(f"Transkript bulunamadı: {temel}")
    return json.loads(js.read_text(encoding="utf-8"))


def _zaman(sn):
    import ortak                                           # tek sürüm: bir saatin üstünde h:mm:ss (2026-10-25)
    return ortak.zaman(sn)


def _tarih(t):
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(t or 0))


def _tum_veri():
    out = []
    for js in KLASOR.glob("transkript_*.json"):
        try:
            v = json.loads(js.read_text(encoding="utf-8"))["veri"]
            if v.get("misafir"):                  # Studio davetlilerinin kayıtları
                continue
            out.append((js.stem, v))
        except Exception:  # noqa: BLE001
            continue
    return sorted(out, key=lambda x: -(x[1].get("olusturma") or 0))


# ----------------------------------------------------------------------------- okuma araçları
@mcp.tool()
def kitaplik(tur: str = "hepsi", musteri: str = "", gun: int = 0, limit: int = 30) -> str:
    """Kitaplıktaki transkriptleri listeler (en yeniden eskiye).
    tur: 'hepsi' | 'video' | 'toplanti'; musteri: yalnızca bu müşterinin toplantıları (marka adı);
    gun: son N gün (0 = hepsi). Her satırda 'temel' adı var; transkript_oku için bunu kullan."""
    sinir = time.time() - gun * 86400 if gun else 0
    satirlar = []
    for temel, v in _tum_veri():
        if tur == "toplanti" and not v.get("toplanti"):
            continue
        if tur == "video" and v.get("toplanti"):
            continue
        if musteri and (v.get("musteri") or "Diğer").casefold() != musteri.casefold():
            continue
        if sinir and (v.get("olusturma") or 0) < sinir:
            continue
        o = (v.get("ozet") or {}).get("ozet") or ""
        satirlar.append(f"- temel={temel} | {v.get('baslik') or temel} | {_tarih(v.get('olusturma'))} | {int((v.get('sure') or 0) // 60)} dk"
                        + (f" | toplantı · {v.get('musteri') or 'Diğer'}" if v.get("toplanti") else f" | {v.get('kanal') or ''}")
                        + (f"\n  {o[:220]}" if o else ""))
        if len(satirlar) >= limit:
            break
    return "\n".join(satirlar) or "Kayıt bulunamadı."


@mcp.tool()
def transkript_oku(temel: str, bolum: str = "ozet", baslangic_dk: float = 0, bitis_dk: float = 0) -> str:
    """Bir transkripti okur. bolum: 'ozet' (özet, öne çıkanlar, bölümler, kararlar, yapılacaklar, toplantı notları) |
    'tam' (konuşmacı adlı, zaman damgalı tam metin; uzunsa baslangic_dk/bitis_dk ile aralık ver)."""
    d = _oku(temel); v = d["veri"]
    bas = [f"# {v.get('baslik') or temel}", f"Tarih: {_tarih(v.get('olusturma'))} · Süre: {int((v.get('sure') or 0) // 60)} dk · "
           f"Konuşmacılar: {', '.join(sorted(set(str(a) for a in (v.get('etiket') or {}).values())))}"
           + (f" · Müşteri: {v.get('musteri') or 'Diğer'}" if v.get("toplanti") else "") + (f" · Link: {v.get('link')}" if str(v.get("link", "")).startswith("http") else "")]
    if bolum != "tam":
        o = v.get("ozet") or {}
        if o.get("ozet"):
            bas += ["", "## Özet", o["ozet"]]
        for ad, anahtar in (("Öne çıkanlar", "maddeler"), ("Kararlar", "kararlar"), ("Yapılacaklar", "yapilacaklar")):
            if o.get(anahtar):
                bas += ["", f"## {ad}"] + [f"- {m}" for m in o[anahtar]]
        if o.get("bolumler"):
            bas += ["", "## Bölümler"] + [f"- [{_zaman(b.get('sn', 0))}] {b.get('baslik', '')}" for b in o["bolumler"]]
        n = v.get("notlar")
        if n:
            bas += ["", "## Toplantı notları", n.get("baglam", "")]
            bas += [f"- {k.get('baslik')}: {k.get('ozet')}" for k in n.get("konular") or []]
            if n.get("acik_sorular"):
                bas += ["Açık sorular:"] + [f"- {q}" for q in n["acik_sorular"]]
            if n.get("yapilacaklar"):
                bas += ["Kim ne yapacak:"] + [f"- {y.get('is')}" + (f" — {y['kim']}" if y.get("kim") else "") + (f" ({y['ne_zaman']})" if y.get("ne_zaman") else "") for y in n["yapilacaklar"]]
        if v.get("brief"):
            bas += ["", "## Brief (özet)", v["brief"]["metin"][:3000]]
        bas += ["", "(Tam metin için bolum='tam'.)"]
        return "\n".join(bas)
    from transkript import paragrafla
    par = paragrafla(d["segmentler"], v["etiket"])
    b0, b1 = baslangic_dk * 60, (bitis_dk * 60 if bitis_dk else 1e9)
    metin = [f"[{_zaman(p['bas'])}] {p['ad']}: {p['metin']}" for p in par if b0 <= p["bas"] < b1]
    sonuc = "\n".join(bas + [""] + metin)
    if len(sonuc) > 90000:
        kes = sonuc[:90000]
        return kes + f"\n\n[... metin uzun; devamı için baslangic_dk={int(par[len(kes.splitlines()) - 3]['bas'] // 60) if len(par) > 3 else 0} ile tekrar çağır]"
    return sonuc


@mcp.tool()
def ara(sorgu: str, temel: str = "") -> str:
    """Kitaplıkta metin araması (kelime eşleşmesi). Sonuçlarda transkript, zaman ve paragraf döner."""
    q = urllib.parse.urlencode({"q": sorgu, **({"temel": temel} if temel else {})})
    r = _api(f"/api/ara?{q}")
    if isinstance(r, dict) and r.get("hata"):
        return r["hata"]
    return "\n".join(f"- temel={x['temel']} | {x['baslik'][:60]} | [{_zaman(x['sn'])}] {x['ad']}: {x['metin'][:300]}" for x in r[:25]) or "Eşleşme yok."


@mcp.tool()
def acik_isler(musteri: str = "", gun: int = 30) -> str:
    """Son N gündeki toplantılardan açık işler (yapılacaklar), kim ve ne zaman bilgisiyle; isteğe bağlı müşteri filtresi."""
    sinir = time.time() - gun * 86400
    out = []
    for temel, v in _tum_veri():
        if not v.get("toplanti") or (v.get("olusturma") or 0) < sinir:
            continue
        if musteri and (v.get("musteri") or "Diğer").casefold() != musteri.casefold():
            continue
        isler_ = (v.get("notlar") or {}).get("yapilacaklar") or [{"is": y} for y in ((v.get("ozet") or {}).get("yapilacaklar") or [])]
        if not isler_:
            continue
        out.append(f"## {v.get('baslik')} (temel={temel})")
        out += [f"- {y.get('is')}" + (f" — {y['kim']}" if y.get("kim") else "") + (f" ({y['ne_zaman']})" if y.get("ne_zaman") else "")
                + (" [Asana'da]" if y.get("is") in (v.get("asana") or {}) else "") for y in isler_]
    return "\n".join(out) or "Bu aralıkta açık iş yok."


@mcp.tool()
def haftalik_ozet(tur: str = "musteri") -> str:
    """En son haftalık özet: tur 'musteri' (toplantılar müşteri müşteri) ya da 'takip' (takip edilen kanallar)."""
    import haftalik
    son = next((x for x in reversed(haftalik.liste()) if x.get("tur") == tur), None)
    return haftalik.oku(son["ad"]) if son else "Henüz bu türde haftalık özet yok; site üzerinden 'Şimdi hazırla' denebilir."


@mcp.tool()
def isler() -> str:
    """Sıradaki, süren ve son biten işler (yazıya dökme, indirme, klip vb.)."""
    r = _api("/api/isler")
    L = r if isinstance(r, list) else (r.get("isler") or [])
    if isinstance(L, dict):
        L = list(L.values())
    L = sorted(L, key=lambda i: -(i.get("olusturma") or 0))[:15]
    return "\n".join(f"- {i.get('durum')} · {i.get('tur') or 'transkript'} · {str(i.get('baslik') or i.get('link') or '')[:70]}"
                     + (f" · %{i.get('ilerleme')}" if i.get("durum") == "calisiyor" else "") + (f" · temel={i['temel']}" if i.get("temel") else "")
                     + (f" · hata: {i['hata'][:120]}" if i.get("hata") else "") for i in L) or "İş yok."


@mcp.tool()
def indirilenler(temel: str = "") -> str:
    """İndirilen ve üretilen videolar (klipler, Shorts, altyazılı videolar); isteğe bağlı transkripte göre filtre."""
    r = _api("/api/indirilenler")
    if isinstance(r, dict):
        return r.get("hata", "")
    L = [x for x in r if not temel or x.get("temel") == temel][:40]
    return "\n".join(f"- {x['ad']} | {x.get('cozunurluk', '')} | {int(x.get('sure') or 0)} sn | {x.get('yol', '')}" for x in L) or "Yok."


# ----------------------------------------------------------------------------- işlem araçları
@mcp.tool()
def yaziya_dok(link: str, ozet: bool = True, konusmacilar: bool = True, dil: str = "auto", ceviri_dili: str = "", finansal_terapi: bool = False) -> str:
    """Bir video linkini (YouTube, Instagram, Vimeo...) yazıya dökmeyi sıraya alır. finansal_terapi=True: bitince ilk kurulu
    markanın içerik paketi ve Shorts videoları kendiliğinden hazırlanır. ceviri_dili: 'en' gibi; bitince çevirir."""
    r = _api("/api/baslat", {"link": link, "ozet": ozet, "konusmaci": konusmacilar, "dil": dil, "ceviri_dil": ceviri_dili,
                             **({"marka": _marka_kodu()} if finansal_terapi else {})})
    return f"Hata: {r['hata']}" if r.get("hata") else f"Sıraya alındı (iş {r.get('id')})." + (f" Uyarı: {r['uyari']}" if r.get("uyari") else "")


@mcp.tool()
def indir(link: str, kalite: str = "720") -> str:
    """Videoyu indirir. kalite: mp3 | 360 | 480 | 720 | 1080 | en."""
    r = _api("/api/baslat", {"islem": "indir", "link": link, "kalite": kalite})
    return f"Hata: {r['hata']}" if r.get("hata") else f"İndirme sıraya alındı (iş {r.get('id')})."


@mcp.tool()
def klip_olustur(temel: str, baslangic: str, bitis: str, dikey: bool = True, altyazi_stili: str = "pop", kanca: str = "") -> str:
    """Transkriptin videosundan klip üretir. baslangic/bitis 'm:ss' ya da 'h:mm:ss'. dikey=True: yüz takipli 9:16 (Shorts).
    altyazi_stili: kutu | sade | karaoke | pop | vurgu. kanca: üstte duracak başlık, iki satır için 'SATIR 1 / SATIR 2'."""
    _oku(temel)
    r = _api("/api/baslat", {"islem": "klip", "temel": temel, "kesit": f"{baslangic}-{bitis}", "dikey": dikey, "stil": altyazi_stili,
                             "kalite": "1080" if dikey else "720", "en_az": 1080 if dikey else 0, "kanca": kanca})
    return f"Hata: {r['hata']}" if r.get("hata") else f"Klip sıraya alındı (iş {r.get('id')}); bitince indirilenler klasörüne düşer."


@mcp.tool()
def cevir(temel: str, dil: str = "en") -> str:
    """Transkripti (ve özetini) çevirir; altyazı (.srt), metin ve iki dilli Word dosyası üretir."""
    _oku(temel)
    r = _api(f"/api/ceviri/{urllib.parse.quote(temel)}", {"dil": dil})
    return f"Hata: {r['hata']}" if r.get("hata") else "Çeviri başladı."


@mcp.tool()
def finansal_terapi_paketi(temel: str) -> str:
    """Var olan bir transkript için marka içerik paketini (kapak, YouTube, blog, Shorts, kurgu notları,
    LinkedIn, Instagram) hazırlar; Shorts videoları da kendiliğinden oluşturulur. Birkaç dakika sürer."""
    _oku(temel)
    _api(f"/api/marka-etiket/{urllib.parse.quote(temel)}", {"marka": _marka_kodu()})
    r = _api(f"/api/marka/{urllib.parse.quote(temel)}", {"marka": _marka_kodu(),
                                                          "secim": ["kapak", "youtube", "blog", "shorts", "kurgu", "linkedin", "instagram"]})
    return f"Hata: {r['hata']}" if r.get("hata") else "Paket hazırlanıyor; bitince Word belgesi transkriptin yanında olur."


@mcp.tool()
def paket_oku(temel: str) -> str:
    """Hazırlanmış marka içerik paketinin metni (kapak, YouTube, Shorts, kurgu notları, LinkedIn, Instagram, blog)."""
    yol = KLASOR / f"{temel}.{_marka_kodu()}.txt"
    return yol.read_text(encoding="utf-8") if yol.exists() else "Bu transkript için paket yok; finansal_terapi_paketi ile hazırlanabilir."


# ----------------------------------------------------------------------------- creator atölyesi
@mcp.tool()
def atolye_calismalari() -> str:
    """Creator atölyesi çalışmaları (konu, brief, durum, akış sayısı) ve kadrosu olan kategoriler."""
    d = _api("/api/atolye")
    if d.get("hata"):
        return d["hata"]
    satir = [f"- {c['id']} · {c['kategori']} · {_tarih(c.get('zaman') or 0)} · {c.get('durum')} · {c.get('video', 0)} video, {c.get('akis', 0)} akış"
             f" · brief: {(c.get('brief') or '')[:90]}" for c in d.get("calismalar") or []]
    return ("Çalışmalar:\n" + "\n".join(satir) if satir else "Henüz çalışma yok.") + \
        "\nKadrolar: " + ", ".join(f"{k['ad']} ({len(k.get('creatorlar') or [])})" for k in (d.get("kadro") or {}).values())


@mcp.tool()
def atolye_oku(calisma_id: str, bolum: str = "akislar") -> str:
    """Bir atölye çalışmasını okur. bolum: akislar (prodüksiyon tabloları + creator brief) | rapor (trend raporu) | videolar (incelenen
    creator videoları, ölçüler, neden seçildikleri)."""
    d = _api("/api/atolye/" + urllib.parse.quote(calisma_id))
    if not d or d.get("hata"):
        return (d or {}).get("hata") or "Çalışma bulunamadı."
    if bolum == "rapor":
        return d.get("rapor") or "Rapor henüz yok."
    if bolum == "videolar":
        return "\n\n".join(f"{v.get('kanal')} · {v.get('baslik')} · {v.get('izlenme', 0):,} izlenme"
                           + (f" · olağanının {v['viral']} katı" if v.get("viral") else "") + f"\n{v.get('url')}\nNeden: {v.get('neden', '')}"
                           for v in d.get("videolar") or []) or "Video yok."
    out = []
    for i, a in enumerate(d.get("akislar") or [], 1):
        out.append(f"AKIŞ {i}: {a.get('baslik')} ({a.get('bicim')}, {a.get('sure')}, kanca: {a.get('kanca_turu', '')})\n{a.get('fikir', '')}")
        out += [f"SAHNE {n} ({s.get('zaman')}) | GÖRÜNTÜ: {s.get('goruntu')} | SÜPER: {s.get('super') or '-'} | SES: {s.get('ses')}"
                for n, s in enumerate(a.get("sahneler") or [], 1)]
        out.append("CREATOR BRIEF: " + json.dumps(a.get("creator_brief") or {}, ensure_ascii=False))
    return "\n".join(out) or f"Akışlar henüz hazır değil (durum: {d.get('durum')}, adım: {d.get('adim')})."


@mcp.tool()
def atolye_baslat(kategori: str, brief: str = "", bicim: str = "ikisi", ornek_linkler: str = "", marka: str = "", urun: str = "") -> str:
    """Creator atölyesi başlatır: konuda tutmuş creator videolarını bulur, çözümler, trend raporu ve brief'e uygun 3 akış yazar
    (20-40 dk). bicim: kisa | uzun | ikisi. ornek_linkler: boşlukla ayrılmış TikTok/Instagram/YouTube linkleri.
    marka: atolye/markalar.json'daki marka kodu; verilirse marka profili
    (hedef kitle, ton, zorunlular, yasaklar, rakipler) brief'e kendiliğinden eklenir ve brief yalnızca kampanyaya özel kısım olur.
    urun: markanın ürün adı (ör. 'Stelatopia')."""
    d = _api("/api/atolye/calistir", {"kategori": kategori, "brief": brief, "bicim": bicim, "linkler": ornek_linkler, "marka": marka, "urun": urun})
    return d.get("hata") or f"Başladı (çalışma {d.get('id')}). Bitince atolye_oku ile okunabilir."


@mcp.tool()
def atolye_akis_degistir(calisma_id: str, akis_no: int, talimat: str) -> str:
    """Bir atölye akışını talimatla yeniden yazdırır (birkaç dakika); sonra atolye_oku ile okunur."""
    d = _api(f"/api/atolye/{urllib.parse.quote(calisma_id)}/akis", {"islem": "duzelt", "no": akis_no, "talimat": talimat})
    return d.get("hata") or "Yeniden yazılıyor."


if __name__ == "__main__":
    if "--dene" in sys.argv:
        print(kitaplik(limit=5)); print(); print(acik_isler(gun=7)[:800]); print(); print(isler()[:500])
    else:
        mcp.run()

"""harfler.py - Büyük harf kuralı (2026-10-24; kullanıcı: "İngilizce hiçbir kelimede büyük harf İ kullanma. MİGROS olur ama. Dil bilgisine hakim ol.").

Kelime kelime karar: Türkçe kelime ve Türk markası Türkçe kuralla büyür (i → İ, ı → I: MİGROS, BİRİKTİREYİM), İngilizce kelime İngilizce kuralla
(i → I: PEPSICO, NETFLIX, LINKEDIN). Python'un düz .upper()'ı Türkçe kelimelerde yanlıştı ('birikt' → 'BIRIKT'); Türkçe .upper() da İngilizcede
yanlıştı ('Cosmetics' → 'COSMETİCS'). Arayüzdeki eşi static/index.html `ustHarf` (aynı listeler).
İngilizce sayılan: Türkçe harfi (çğıöşü) olmayan ve (bilinen İngilizce/yabancı ad, iç büyük harf (PepsiCo), İngilizceye özgü harf dizisi (th, sh, ch, w, q,
x, ph, ck, ee, oo, ou, -ing, -tion, -ics, -ly, sessiz+y sonu)) kelime. Kalanı Türkçe (şüphede Türkçe: 'PREMİUM' hatası 'BİRİKTİREYIM' hatasından az zararlı).
"""
import re
from functools import lru_cache
from pathlib import Path

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜâîû]")
# Türk markaları ve Türkçe sayılacak adlar (İngilizce kalıplara uysa bile Türkçe büyür)
TR_AD = {"migros", "garanti", "turkcell", "galatasaray", "fenerbahçe", "istanbul", "izmir", "ankara", "akbank", "ziraat", "trendyol", "getir", "yemeksepeti",
         "sahibinden", "pegasus", "bim", "video", "film", "link", "radyo", "sinema", "kredi", "internet", "dijital", "strateji", "kreatif",
         "mini", "taksi", "pizza", "kafe", "spor"}
EN_AD = {"linkedin", "instagram", "tiktok", "youtube", "netflix", "spotify", "iphone", "ipad", "openai", "chatgpt", "claude", "gemini", "studio", "content",
         "meet", "ghost", "couple", "pepsico", "cosmetics", "note", "nike", "adidas", "disney", "pixar", "netflix", "amazon", "microsoft", "google", "apple", "meta", "tiktok",
         "cannes", "lions", "clio", "pencil", "white", "black", "silver", "bronze", "gold", "grand", "prix", "titanium", "brief", "insight", "online", "live",
         "story", "reels", "viral", "creator", "influencer", "social", "media", "digital", "marketing", "campaign", "idea", "first", "big", "time", "life",
         "with", "this", "kit", "win", "wifi", "display", "backstop", "display", "office",
         "inside", "side", "line", "mine", "nine", "fine", "site", "smile", "nice", "price", "prime", "crime", "drive", "five", "rise", "wise", "king",
         "creative", "executive", "native", "premium", "medium", "public", "basic", "junior", "senior", "session", "ticket", "editing", "cookie", "organizer",
         "officer", "chief", "hair", "foundation", "frontier", "paris", "android", "gemini", "codex", "lotion", "peeling", "anti", "beauty", "design", "fashion",
         "music", "magic", "pilot", "light", "night", "right", "high", "fair", "saint", "visual", "visit", "visa", "mission", "vision", "pitch", "pick"}
# 'ea' ve '-ive' kalıp değil: reaksiyon, realite, motive Türkçede de böyle yazılır
EN_KALIP = re.compile(r"(th|sh|ch|w|q|x|ph|ck|ee|oo|ou|ing$|tion|sion$|ics$|ly$|ity$|[bcdfghjklmnprstvz]y$)", re.I)
ON = set("eiöü")
ARKA = set("aıou")


@lru_cache(maxsize=1)
def _sozluk():
    try:
        return {w.strip().lower() for w in Path("/usr/share/dict/words").read_text(encoding="utf-8", errors="ignore").split() if len(w) >= 4}
    except Exception:  # noqa: BLE001
        return set()


_EK = {}


def _ek(anahtar):
    """Kullanıcının markaları: ayarlar.json `harf_tr` / `harf_en` (küçük harf listeleri; 60 sn önbellek). Kodda marka adı yok (2026-10-25)."""
    import time
    c = _EK.get(anahtar)
    if c and time.time() - c[0] < 60:
        return c[1]
    try:
        import ortak
        v = {str(x).lower() for x in (ortak.ayar().get(anahtar) or [])}
    except Exception:  # noqa: BLE001
        v = set()
    _EK[anahtar] = (time.time(), v)
    return v


def ingilizce_mi(kelime):
    w = kelime.strip("'’\".,:;!?()[]«»“”-–—/")
    if not w or TR_HARF.search(w):
        return False
    k = w.lower()
    if k in TR_AD or k in _ek("harf_tr"):
        return False
    if k in EN_AD or k in _ek("harf_en") or re.search(r"[a-z][A-Z]", w) or EN_KALIP.search(k):
        return True
    return False                                           # sözlük denemesi Türkçe kelimeleri de İngilizce saydı (lira, aile, vitamin, hakim): kesin işaret yoksa Türkçe


def _tr_ust(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


IKI_DILLI = {"in", "is", "it", "if", "i", "his", "bit", "pin", "fit", "hit", "film", "mini", "link"}   # yanındaki kelimeye göre karar


def ust(s):
    """Metni kelime kelime doğru büyük harfe çevirir. Kesme işaretinden sonraki ek Türkçedir: Instagram'da → INSTAGRAM'DA.
    İki dilde de kelime olanlar ('it', 'bit', 'his') önceki ya da sonraki kelime İngilizceyse İngilizce: 'THIS IS IT' ama 'İŞ BİTTİ, İT GİBİ'."""
    P = re.split(r"(\s+|[/·|,;:()\[\]])", str(s or ""))
    G = []
    for parca in P:
        m = re.match(r"^(.*?)(['’].*)$", parca)
        G.append((m.group(1), m.group(2)) if m else (parca, ""))
    ing = [bool(g.strip()) and ingilizce_mi(g) for g, _ in G]
    kel = [i for i, (g, _) in enumerate(G) if g.strip() and re.search(r"\w", g)]
    iki = {i for i in kel if G[i][0].strip("'’\".,:;!?").lower() in IKI_DILLI}
    for i in iki:
        ing[i] = False
    for _ in range(3):                                     # 'THIS IS IT': karar zincirle yayılır
        for j, i in enumerate(kel):
            if i in iki and not ing[i]:
                komsu = ([kel[j - 1]] if j > 0 else []) + ([kel[j + 1]] if j + 1 < len(kel) else [])
                ing[i] = any(ing[k] for k in komsu)
    return "".join((g.upper() if e else _tr_ust(g)) + _tr_ust(ek) for (g, ek), e in zip(G, ing))


if __name__ == "__main__":
    for t in ["Migros", "Netflix", "PepsiCo", "CheckYourSocial", "Ev alamayacaksam neden biriktireyim?", "LinkedIn · bu hafta",
              "Garanti BBVA", "Instagram'da ilk 11", "Digital strateji", "Inner Circle", "Dijital Terapi", "Social media için dijital kampanya"]:
        print(t, "→", ust(t))

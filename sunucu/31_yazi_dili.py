# sunucu/31_yazi_dili.py — Meet: notların dili (2026-10-29; Meet herkese açık depo olarak İngilizce kitleye açılırken). Toplantı istemleri Türkçe
# yazılmış; Kısaca, koçluk notu, sinyaller, notlar e-postası, sohbet ve canlı öneriler istemin dilinde çıkıyordu. Dil: ayar `notlar_dili` > özet dili
# (`_ozet_dili`: arayüz İngilizceyse İngilizce) > "auto" ise toplantının konuşulan dili. Türkçe kurulumda hiçbir şey değişmez (ek talimat yok).
# Yalnız toplantılar: Studio videolarının özet dili kendi ayarıyla kalır. site.py bu dosyayı diğer parçalarla AYNI ad alanında yürütür.
import claude_yaz as _cy
from flask import g


def _notlar_dili(veri=None):
    ay = ayarlar_oku()
    d = str(ay.get("notlar_dili") or _ozet_dili(ay) or "tr")
    if d == "auto":
        d = str((veri or {}).get("dil") or "")
    return d if re.fullmatch(r"[a-z]{2}", d) and d != "tr" else None


def _veri_dili(temel, toplanti_sart=True):
    try:
        import kitaplik_onbellek
        v = kitaplik_onbellek.veri(temel) or {}
    except Exception:  # noqa: BLE001
        return None
    return _notlar_dili(v) if v.get("toplanti") or not toplanti_sart else None


_toplanti_bitir_dilsiz = _toplanti_bitir


def _toplanti_bitir(is_):
    # kayıt henüz toplantı diye işaretlenmeden çağrılır: "auto"da konuşulan dil kaydın kendisinden okunur (yoksa İngilizce kurulumda notlar Türkçe çıkıyordu)
    with _cy.yazi_dili(_veri_dili(is_.get("temel") or "", toplanti_sart=False) or _notlar_dili()):
        return _toplanti_bitir_dilsiz(is_)


@app.before_request
def _yazi_dili_istek():
    """Toplantı sayfasındaki istekler (Kısaca, koçluk, sohbet, tarif, notlar...) o toplantının not diliyle yazar."""
    temel = (request.view_args or {}).get("temel")
    d = _veri_dili(temel) if temel else None
    if d:
        g.yazi_dili_t = _cy.YAZI_DILI.set(d)


@app.teardown_request
def _yazi_dili_bitir(_hata=None):
    t = g.pop("yazi_dili_t", None)
    if t is not None:
        try:
            _cy.YAZI_DILI.reset(t)
        except ValueError:
            pass


_env_dilsiz = _env


def _env():
    """Alt süreçler (yazıya dökme, canlı yazıya dökme) ayar düzeyindeki not dilini alır."""
    e = _env_dilsiz()
    d = _notlar_dili()
    if d:
        e["VH_YAZI_DILI"] = d
    return e


try:                                                          # canlı öneriler site sürecinde üretilir
    import canli_asistan as _ca
    _ca_uret_dilsiz = _ca.uret

    def _ca_uret(*a, **k):
        with _cy.yazi_dili(_notlar_dili()):
            return _ca_uret_dilsiz(*a, **k)
    _ca.uret = _ca_uret
except ImportError:
    pass

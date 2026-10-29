#!/usr/bin/env python3
"""
site.py - Meet ürününün bilgisayarda çalışan web arayüzü.

Başlatmak için "Meet.command" dosyasına çift tıklayın
veya: .venv/bin/python site.py   ->  http://127.0.0.1:8765
"""
from pathlib import Path as _Path

# 2026-10-23: kod sunucu/ altındaki parçalara bölündü (kullanıcı onayı). Parçalar numara sırasıyla BU dosyanın ad alanında yürütülür:
# tek dosyadaki davranışın aynısı (ortak durum, rota kayıt sırası, açılışta başlayan iş parçacıkları). Yeni kod ilgili parçaya yazılır.
for _parca in sorted((_Path(__file__).resolve().parent / "sunucu").glob("[0-9][0-9]_*.py")):
    exec(compile(_parca.read_text(encoding="utf-8"), str(_parca), "exec"), globals())

if __name__ == "__main__":
    print(f"Transkript sitesi: http://127.0.0.1:{PORT}", flush=True)
    host = "0.0.0.0" if ayarlar_oku().get("ag_paylasimi") else "127.0.0.1"
    from werkzeug.serving import make_server
    for _p in URUN_PORTLARI:
        if _p != PORT:
            try:
                _srv = make_server(host, _p, app, threaded=True)
                threading.Thread(target=_srv.serve_forever, daemon=True).start()
            except OSError as _e:
                print(f"{_p} açılamadı: {_e}", flush=True)
    app.run(host=host, port=PORT, debug=False, threaded=True)

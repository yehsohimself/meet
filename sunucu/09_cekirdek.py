# sunucu/09_cekirdek.py — ortak çekirdek: meşguliyet ucu (yeniden_baslat.py kullanır), iş kuyruğu işçileri ve haftalık araç güncellemesi
# (2026-10-29: 09_atolye.py'den ayrıldı; Atölye'siz kurulumlarda, ör. herkese açık Studio deposunda, işçiler hiç başlamıyor, işler sırada kalıyordu).
# site.py bu dosyayı diğer parçalarla AYNI ad alanında, numara sırasıyla yürütür; tek başına çalıştırılmaz.


@app.get("/api/mesgul")
def mesgul_get():
    n = mesgul_nedenler()
    return jsonify({"mesgul": bool(n), "nedenler": n})


threading.Thread(target=_dayanikli(_isci, "yazıya dökme"), daemon=True).start()
threading.Thread(target=_dayanikli(_isci_indir, "video"), daemon=True).start()
threading.Thread(target=_guncelleme_kontrol, daemon=True).start()

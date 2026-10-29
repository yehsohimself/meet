#!/usr/bin/env python3
"""
isimlendir.py - Bitmiş bir transkriptte konuşmacı adlarını değiştirir, txt ve docx'i yeniler.

Kullanım:
    python isimlendir.py transkript_tr.json "Konuşmacı 1=Ali" "Konuşmacı 2=Ayşe"
    python isimlendir.py transkript_tr.json "Ali=Ayşe"        (adı adla değiştirmek de olur)
    python isimlendir.py transkript_tr.json --sil "Konuşmacı 3"    (hayalet konuşmacıyı komşulara dağıt)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transkript import ciktilari_yaz, hayalet_temizle, log  # noqa: E402


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    json_yolu = Path(sys.argv[1])
    if not json_yolu.is_absolute():
        json_yolu = Path(__file__).resolve().parent / json_yolu
    veri_tum = json.loads(json_yolu.read_text(encoding="utf-8"))
    veri, segmentler = veri_tum["veri"], veri_tum["segmentler"]

    degisim, silinecek = {}, []
    argv = sys.argv[2:]
    while "--sil" in argv:
        i = argv.index("--sil")
        silinecek.append(argv[i + 1])
        del argv[i:i + 2]
    for ad in silinecek:
        k = next((k for k, v in veri["etiket"].items() if v == ad), None)
        if k is None:
            raise SystemExit(f"HATA: '{ad}' bulunamadı. Mevcut adlar: " + ", ".join(veri["etiket"].values()))
        segmentler = hayalet_temizle(segmentler, zorla=[k])
        del veri["etiket"][k]
        log(f"'{ad}' silindi, cümleleri komşu konuşmacılara dağıtıldı.")

    for arg in argv:
        if "=" not in arg:
            raise SystemExit(f"HATA: 'Eski=Yeni' biçiminde olmalı: {arg}")
        eski, yeni = [x.strip() for x in arg.split("=", 1)]
        degisim[eski] = yeni

    bulundu = False
    for k, ad in list(veri["etiket"].items()):
        if ad in degisim:
            veri["etiket"][k] = degisim[ad]
            bulundu = True
    if not bulundu and degisim:
        raise SystemExit("HATA: Verilen adlar bulunamadı. Mevcut adlar: "
                         + ", ".join(veri["etiket"].values()))

    temel = json_yolu.with_suffix("")
    ciktilari_yaz(temel, veri, segmentler)
    try:
        import sesler as sesler_modulu
        sesler_modulu.ogren(veri, log)
    except Exception:  # noqa: BLE001
        pass
    log(f"Güncellendi: {temel}.txt ve {temel}.docx")
    log("Konuşmacılar: " + ", ".join(veri["etiket"].values()))


if __name__ == "__main__":
    main()

"""kayit_json.py - Transkript JSON'una "yeniden oku, yalnız kendi alanını yaz" kuralı ve süreçler arası dosya kilidi (2026-10-25).

Neden: ceviri.py (30 dk sonra) ve marka.py işin başında okudukları `veri`yi işin sonunda bütünüyle yazıyordu; o sırada site (ad değişikliği,
paylaşım taslağı, kurgu, koleksiyon) aynı dosyaya yazdıysa değişiklikler siliniyordu. Ayrıca iki süreç aynı anda yazınca dosya bozulabiliyordu.

guncelle(yol, fn)   : kilit altında dosyayı yeniden okur, fn(d) ile yalnız gerekli alanları değiştirir, geçici dosyaya yazıp yerine koyar.
kilit(yol)          : aynı dosya için süreçler arası kilit (fcntl.flock, <yol>.lock); site içindeki `kilit` (thread) ile birlikte kullanılır.
"""
import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def kilit(yol, bekle_sn=120):
    yol = Path(yol)
    k = yol.with_name(yol.name + ".lock")
    fd = os.open(str(k), os.O_CREAT | os.O_RDWR, 0o600)
    t0 = time.time()
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - t0 > bekle_sn:
                    raise TimeoutError(f"{yol.name} kilidi {bekle_sn} sn içinde alınamadı")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def yaz(yol, d):
    """Atomik yazım (geçici dosya + yerine koyma). Kilit çağıranda olmalı."""
    yol = Path(yol)
    tmp = yol.with_name(yol.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")   # girintisiz: %38 küçük, 4× hızlı (2026-10-25)
    tmp.replace(yol)


def guncelle(yol, fn):
    """Kilit altında: oku → fn(d) (d = {"veri", "segmentler"}; True/None döner, False = yazma) → yaz. Döner: güncel d."""
    yol = Path(yol)
    with kilit(yol):
        d = json.loads(yol.read_text(encoding="utf-8"))
        if fn(d) is not False:
            yaz(yol, d)
        return d

# Mimari

Meet ve ortak motor; kardeş ürünler kurulu değilse kapalıdır. Bu belge kodun nasıl düzenlendiğini anlatır; kişiye özel notlar depoda değildir.

## Sunucu

- `site.py` yükleyicidir: `sunucu/00_baslangic.py … 26_pt_uzak.py` parçalarını numara sırasıyla aynı ad alanında çalıştırır. Ortak durum
  (Flask `app`, `isler`, `kilit`, iş kuyrukları, `ayarlar_oku/yaz`) ilk parçalarda kurulur; sonraki parçalar rota ve arka plan döngüsü ekler.
  Bir işlevi başka parçada genişletmek için sarmalama kalıbı kullanılır: `_x_onceki = x` sonra `def x(...)`. Aynı adı sarmalamadan ikinci kez
  tanımlamak yasaktır; `duman_testi.py hizli` bunu yakalar.
- Portlar `URUN_PORTLARI`: 8765 Studio, 8766 Meet, 8767 Ghost, 8768 Couple, 8769 Content, 8770 davetli kapısı (Cloudflare tüneli), 8771 PT.
  Sayfaya `data-urun` ile ürün söylenir; `static/index.html` Studio, Meet ve Ghost'u çizer; Couple, Content ve PT'nin sayfaları ayrıdır
  (`static/couple.html`, `content.html`, `pt.html`). Ürüne özel ekler `static/<ürün>_ek.js/css`.
- Güvenlik katmanı (`24_guvenlik.py`): ayar yanıtlarında sır maskeleme, tür doğrulama, JSON hata yanıtı, yalnız 127.0.0.1'den yazılabilen
  uçlar (uzantı ve kaydedici bu Mac'te), gzip, değişmez statik önbellek. Davetli kapısı (`22_misafir.py`): 8770'te varsayılan ret, izinli
  uç listesi, sahiplik denetimi, oran sınırı; davetlinin Claude'u yalnız kendi anahtarıyla.
- Yeniden başlatma yalnız `yeniden_baslat.py` ile: `/api/mesgul` boşalınca, `duman_testi.py hizli + birim + testler` geçerse.

## Motor (ürünlerin ortak kullandığı modüller)

- `transkript.py`: link ya da dosya → ses → mlx-whisper (Apple grafik işlemcisi) ile yazıya dökme; VAD pencereleri, karışık dil, kurtarma geçişi,
  uydurma filtresi; konuşmacı ayırma ayrı süreçte (sherpa-onnx), ses izleri; txt + json hemen, docx/srt gecikmeli (`ERTELE_SN`); kontrol noktası
  (`.onbellek/is/`) ile kaldığı yerden devam.
- `claude_yaz.py`: Claude Code programını araçsız, temiz ortamda çağırır (`sor`, `sor_json`, `sor_akis`, `sor_gorsel`); kullanım kaydı,
  abonelik sınırı, arka plan bütçesi, davetli bağlamı (`MISAFIR`).
- `ozet.py` (özet; Claude varsa tek seferde, yoksa Ollama parçalı), `ceviri.py`, `altyazi.py` (anlamlı altyazı kırılımı), `yakma.py` (altyazılı
  video, klip, dikey kadraj, kelime stilleri; PNG çizimi AppKit ile), `kadraj.py` (yüz takibi), `dublaj.py` (Chatterbox, MLX), `klipler.py`,
  `kapak.py`, `terimler.py` (transkript temizliği), `sesler.py` (konuşmacı tanıma profilleri), `harfler.py` (Türkçe/İngilizce büyük harf kuralı).
- `ortak.py`: `zaman`, `saniye`, `ayar`, `kimlik` (kurulumun sahibi: ad, e-postalar, X hesabı, takım; hepsi ayarlardan), `sirket_adlari`,
  `temel_gecerli`, `guvenli_ad`. `kayit_json.py`: kilitli ve atomik JSON güncelleme. `kitaplik_onbellek.py`: transkript listesi önbelleği.
  `gizli.py`: sırlar macOS Anahtar Zinciri'nde.
- `sizinti.py`: depoya kişisel bilgi sızmasını denetler (ayarlardaki adlar + genel desenler); duman testi ve commit kancası çağırır.

## Ürünler
- **Meet** (`sunucu/04_toplanti.py`, `16_`, `20_`, `23_`, `25_`; `meet_*.py`, `kisaca.py`, `danisman.py`, `sinyaller.py`, `notlarim.py`,
  `tarifler.py`, `sohbet.py`, `sirketler.py`, `kisiler.py`, `takvim.py`, `gorevler.py`): kayıt (`kaydedici/`, Swift, ScreenCaptureKit) ve Chrome
  uzantısı (`uzanti/`) sinyalleri → yazıya dökme → şirket/müşteri seçimi → Kısaca, danışman notu, sinyaller → Drive ve Asana. Şirketler ve
  müşteriler yalnız `ayarlar.json` `sirketler` listesinden okunur.

## Veri (git dışı)

`ayarlar.json` (kişi, şirketler, müşteriler, kimlikler), `profil/` (Ghost profili, danışman geçmişi, kişi notları), `markalar/`,
`atolye/markalar.json`, `atolye/kadro.json`, `kayitlar/`, `indirilenler/`, `ghost/`, `couple/`, `content/`, `pt/`, `misafir/`, transkript
dosyaları ve bütün medya. Gece yedeği (`yedek.py`) bunların JSON ve belge kısmını Drive'a zip olarak alır; `geri_yukle.py` geri yükler.
Şablonlar: `ayarlar.ornek.json`, `atolye/markalar.ornek.json`.

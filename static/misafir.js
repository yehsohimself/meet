/* misafir.js — Studio davetlilerinin arayüzü (2026-10-24). Yalnız davet linkiyle açılan 8770 kapısında, sunucu tarafından sayfaya eklenir.
   Sahibe ait her şey gizlenir (ürün menüsü, ayarlar, Takip, koleksiyonlar, Finder/Drive, diğer ürünlere geçişler); Ayarlar düğmesi misafirin
   kendi panelini açar: günlük hak, kendi Claude anahtarı, çıkış. Asıl koruma sunucudadır (sunucu/22_misafir.py); burası yalnız görünüm. */
(() => {
if (document.documentElement.dataset.misafir !== '1') return;
const css = document.createElement('style');
css.textContent = `
  .urunbtn,.urunler,#yuz button:not([data-v="video"]):not([data-v="kitaplik"]),#libTab button[data-v="tk"],#kolFiltre,#kolRow,
  .st-grup.genel,#dlFinder,#stSonra .ghost,#stSonra [data-st="ct"],#tGhost,#musteriOneri{display:none!important}
  .ms-dlg{position:fixed;inset:0;z-index:90;background:rgba(0,0,0,.45);display:grid;place-items:center;padding:16px}
  .ms-kart{width:min(440px,100%);background:var(--surface);color:var(--ink);border:1px solid var(--hair2);border-radius:18px;padding:22px;box-shadow:var(--shadow2)}
  .ms-kart h3{margin:0 0 4px;font-size:20px} .ms-kart p{margin:6px 0;color:var(--muted);font-size:14px;line-height:1.5}
  .ms-kart .row{display:flex;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap}
  .ms-kart input{flex:1;min-width:0;border:0;background:var(--fill);color:var(--ink);border-radius:10px;padding:10px 12px;font:inherit;font-size:14px;outline:none}
  .ms-kart .sp{flex:1}
  .ms-not{max-width:760px;margin:0 auto 14px;font-size:13px;color:var(--muted);text-align:center}`;
document.head.appendChild(css);
const json = async (u, o) => { const r = await fetch(u, o); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.hata || 'Olmadı'); return j; };

// Menülerde sahibe ait seçenekler
const SAHIBE = /Finder|Drive|Koleksiyon|Content|Couple|Dudakları|Ghost|Klasörü aç/;
const _pop = popover;
popover = function(anchor, items, opts){   // eslint-disable-line no-global-assign
  items = (items || []).filter(it => !it || !SAHIBE.test(String(it[0] || '')));
  return _pop(anchor, items, opts);
};

async function panel(){
  let b = {}; try{ b = await json('/api/misafir/ben'); }catch(e){}
  const d = document.createElement('div'); d.className = 'ms-dlg';
  d.innerHTML = `<div class="ms-kart" role="dialog" aria-label="Hesabınız">
    <h3>${esc(b.ad || 'Davetli')}</h3>
    <p>Bugün ${b.bugun ?? 0} / ${b.gunluk ?? 3} video. Videolar en çok ${b.en_uzun_dk ?? 60} dakika olabilir. Yalnızca sizin videolarınız burada görünür.</p>
    <p><b>Claude anahtarı</b> ${b.anahtar ? '· eklendi' : ''}<br>${b.anahtar ? 'Özet, çeviri, yayın paketi ve Sor sizin Claude hesabınızla yapılıyor.' : 'Eklemezseniz özet ve çeviri bu bilgisayardaki daha basit bir modelle yapılır; Sor ve yayın paketi için anahtar gerekir. Anahtar, sizi davet edenin Mac’inde Anahtar Zinciri’nde saklanır.'}</p>
    <div class="row">${b.anahtar ? '<span class="sp"></span><button class="sbtn red" type="button" data-a="sil">Anahtarı kaldır</button>'
      : '<input type="password" placeholder="sk-ant-… (console.anthropic.com ya da claude setup-token)" autocomplete="off"><button class="sbtn blue" type="button" data-a="ekle">Ekle</button>'}</div>
    <div class="row"><button class="sbtn plain" type="button" data-a="cikis">Çıkış yap</button><span class="sp"></span><button class="sbtn" type="button" data-a="kapat">Kapat</button></div></div>`;
  document.body.appendChild(d);
  const kapat = () => d.remove();
  d.onclick = e => { if (e.target === d) kapat(); };
  d.querySelector('[data-a="kapat"]').onclick = kapat;
  d.querySelector('[data-a="cikis"]').onclick = async () => { await fetch('/api/misafir/cikis', {method: 'POST'}); location.reload(); };
  d.querySelector('[data-a="ekle"]')?.addEventListener('click', async () => {
    try{ await json('/api/misafir/anahtar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({anahtar: d.querySelector('input').value.trim()})}); toast('Claude anahtarınız eklendi'); kapat(); panel(); }
    catch(e){ toast(e.message); } });
  d.querySelector('[data-a="sil"]')?.addEventListener('click', async () => { await fetch('/api/misafir/anahtar', {method: 'DELETE'}); toast('Anahtar kaldırıldı'); kapat(); panel(); });
}
const ayar = $('#ayarBtn');
if (ayar){ const yeni = ayar.cloneNode(true); yeni.title = 'Hesabınız'; yeni.setAttribute('aria-label', 'Hesabınız'); ayar.replaceWith(yeni); yeni.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); panel(); }, true); }
const brand = $('.brand'); if (brand){ brand.onclick = e => { e.preventDefault(); location.assign('/'); }; }
// ana sayfada kısa not
const h = $('#composer') || $('#link')?.closest('section');
if (h && !$('.ms-not')){ const n = document.createElement('div'); n.className = 'ms-not'; n.textContent = `${(window.MISAFIR || {}).ad || 'Davetli'} olarak kullanıyorsunuz. Yalnızca sizin videolarınız görünür.`; h.after(n); }
document.title = 'Studio';
})();

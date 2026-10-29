/* misafir_meet.js — Meet davetlilerinin arayüzü (2026-10-24). Yalnız davet kapısında (8770) sunucu ekler; asıl koruma sunucudadır
   (sunucu/22_misafir.py + 23_misafir_meet.py), burası yalnız görünüm.
   Studio sayfasında: davette Meet de açıksa üstte "Meet" geçişi. Meet sayfasında: sahibe ait her şey gizlenir (şirketler, durum, takvim, sözler, kişiler,
   Asana, Drive, notlar e-postası, tarifler, Couple), kayıt ve dosya yükleme davetlinin kendi uçlarına gider, hesap paneli Meet sınırlarını söyler. */
(() => {
if (document.documentElement.dataset.misafir !== '1') return;
const U = window.MISAFIR_URUNLER || ['studio'], MEET = document.documentElement.dataset.urun === 'note', SAHIP = window.MISAFIR_SAHIP || 'davet eden';
const json = async (u, o) => { const r = await fetch(u, o); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.hata || 'Olmadı'); return j; };

// iki ürün açıksa üst çubukta öbürüne geçiş
if (U.includes('studio') && U.includes('meet')){
  const sag = document.querySelector('.nav .sag, .nav .r, .nav > div:last-child');
  const a = document.createElement('a'); a.className = 'ms-gecis'; a.href = MEET ? '/' : '/?u=meet'; a.textContent = MEET ? 'Studio' : 'Meet';
  a.title = MEET ? 'Videolar için Studio' : 'Toplantılar için Meet';
  (sag || document.body).prepend(a);
}
const css = document.createElement('style');
css.textContent = `.ms-gecis{display:inline-flex;align-items:center;height:32px;padding:0 14px;border-radius:999px;background:var(--fill);color:var(--ink);font:600 13px var(--sans);text-decoration:none;margin-right:8px}
  .ms-not{max-width:760px;margin:10px 0 0;font:400 13px/1.5 var(--sans);color:var(--muted)}`
  + (MEET ? `
  #tDurumSat,#meetDurumBtn,#tVurgu,#tBekBtn,#onBrifingKutu,#canliKutu,#notBar,#haftalikKutu,#tGhost,#tKisiler,#tKapsam,#tSoz,#tYorum,#musteriOneri,
  #kayitMusteri,#kayitAmac,#kayitOto,.tkprof,#tarifKutu,#notlarKutu,.tnotac,.kgorev,.tpsayi,#tSiraKart,#tSor,#asanaBar{display:none!important}
  .ms-uyari{margin:0 0 14px;padding:12px 16px;border-radius:14px;background:var(--tint);color:var(--ink);font:400 13.5px/1.5 var(--sans)}
  .ms-uyari button{margin-left:6px}
  body.tSayfa[data-tsek="ozet"] #doc .sagk > #ozetKutu.ms-goster{display:block!important}
  body.ms-anahtarsiz #kisacaKutu,body.ms-anahtarsiz #tSesli{display:none!important}` : '');
document.head.appendChild(css);
if (!MEET) return;

// kayıt ve dosya: davetlinin kendi uçları (kayıt sahibin klasörüne değil, davetlinin klasörüne gider)
const _fetch = window.fetch;
window.fetch = function(u, o){
  if (typeof u === 'string'){
    if (u === '/api/kayit/baslat') u = '/api/misafir/toplanti/baslat';
    else if (u === '/api/kayit/yukle') u = '/api/misafir/toplanti/yukle';
    else { const m = /^\/api\/kayit\/([0-9a-f]{8})\/(parca|bitir)$/.exec(u); if (m) u = `/api/misafir/toplanti/${m[1]}/${m[2]}`; }
  }
  return _fetch.call(this, u, o);
};
// menülerde sahibin araçları
const _pop = popover;
popover = function(anchor, items, opts){   // eslint-disable-line no-global-assign
  return _pop(anchor, (items || []).filter(it => !it || !/Düzenle|Couple|Asana|Drive|Notları|Takip e-postası|Brief/.test(String(it[0] || ''))), opts);
};
document.title = 'Meet';
const brand = document.querySelector('.brand'); if (brand) brand.onclick = e => { e.preventDefault(); location.assign('/?u=meet'); };
const kayitNot = document.querySelector('#kayitNot');
if (kayitNot) kayitNot.innerHTML = 'Google Meet, Teams ya da Zoom için “Mikrofon + bilgisayar sesi” seçin; Chrome’un paylaşım penceresinde <b>Tüm ekran</b>’ı seçip <b>Sistem sesini de paylaş</b>’ı işaretleyin. Görüntü kaydedilmez. <b>Kaydetmeden önce toplantıdakilere haber verin.</b>';
// başlığın altında kısa ve dürüst not
function notYaz(){
  const yer = document.querySelector('.tprofil .tpbilgi'); if (!yer || yer.querySelector('.ms-not')) return;
  const n = document.createElement('p'); n.className = 'ms-not';
  n.textContent = `${(window.MISAFIR || {}).ad || 'Davetli'} olarak kullanıyorsunuz. Toplantılarınızı burada yalnızca siz görürsünüz; kayıtlar sizi davet eden kişinin bilgisayarında saklanır.`;
  yer.append(n);
}
// toplantı sayfası: Claude anahtarı yoksa "Kısaca" ve danışman notu çıkmaz; bunu sayfada açıkça söyle (özet yine görünür)
let ANAHTAR = null; json('/api/misafir/ben').then(b => { ANAHTAR = !!b.anahtar; }).catch(() => {});
function toplantiNotu(){
  const sag = document.querySelector('body.tSayfa #doc .sagk'), bar = sag?.querySelector('#tSekBar');
  if (!sag || !bar || ANAHTAR !== false || document.querySelector('#kisacaKutu .kp')) { document.body.classList.remove('ms-anahtarsiz'); return; }
  document.body.classList.add('ms-anahtarsiz');            // Kısaca ve sesli özet anahtarsız çıkmaz: yerine düz özet
  let n = sag.querySelector('.ms-uyari');
  if (!n){ n = document.createElement('div'); n.className = 'ms-uyari'; n.dataset.sek = 'ozet';
    n.innerHTML = 'Bu toplantının özeti bilgisayardaki basit modelle çıkarıldı. Kim ne yapacak, danışman notu ve “Bu toplantıya sor” için Claude anahtarınızı ekleyin.<button class="sbtn" type="button">Anahtar ekle</button>';
    n.querySelector('button').onclick = panel; }
  if (bar.nextElementSibling !== n) bar.after(n);
  const oz = document.querySelector('#ozetKutu');
  if (oz){ oz.dataset.sek = 'ozet'; oz.classList.add('ms-goster'); if (n.nextElementSibling !== oz) n.after(oz); }
}
notYaz(); new MutationObserver(() => { notYaz(); toplantiNotu(); }).observe(document.body, {childList: true, subtree: true});

// hesap paneli: Meet sınırları
async function panel(){
  let b = {}; try{ b = await json('/api/misafir/ben'); }catch(e){}
  const d = document.createElement('div'); d.className = 'ms-dlg';
  d.innerHTML = `<div class="ms-kart" role="dialog" aria-label="Hesabınız">
    <h3>${esc(b.ad || 'Davetli')}</h3>
    <p>Bugün ${b.bugun ?? 0} / ${b.gunluk ?? 3} kayıt. Toplantılar en çok 120 dakika olabilir. Toplantılarınızı burada yalnızca siz görürsünüz.</p>
    <p><b>Claude anahtarı</b> ${b.anahtar ? '· eklendi' : ''}<br>${b.anahtar ? 'Özet, kim ne yapacak, danışman notu ve “Bu toplantıya sor” sizin Claude hesabınızla yapılıyor.' : 'Eklemezseniz özet bu bilgisayardaki daha basit bir modelle yapılır; danışman notu ve “Bu toplantıya sor” için anahtar gerekir. Anahtar, sizi davet edenin Mac’inde Anahtar Zinciri’nde saklanır.'}</p>
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
const ayar = document.querySelector('#ayarBtn');
if (ayar){ const yeni = ayar.cloneNode(true); yeni.title = 'Hesabınız'; yeni.setAttribute('aria-label', 'Hesabınız'); ayar.replaceWith(yeni); yeni.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); panel(); }, true); }
})();

// Yan panel (3.15, 2026-10-27; kullanıcı: "yan panelin deneyimini çok geliştir, bazı tuşlar işlevsiz, real-time koçluk buraya kayabilir").
// Simgeye tıklayınca açılır (açılır pencere kaldırıldı). Panel o anki duruma göre şekil alır:
//   toplantıda  → kayıt durumu, canlı koçluk kartları (geri bildirimli), amaç, not/işaret, şu ana kadar, konuşulanlar, hazırlık notu
//   bitince     → notlar hazırlanıyor (adım) ya da hazır (kısaca + Aç)
//   boşta       → sıradaki toplantının hazırlığı ve amacı, toplantılarınıza sorun, son toplantılar
// Veriler Mac'teki Meet'ten (5 sn'de bir). Yazı kutularına yazarken yenileme o bölümü yeniden çizmez.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
function md(m){                                                   // küçük markdown: **kalın**, - madde, satırlar
  let h = '', liste = false;
  for (const t of String(m || '').split('\n')){
    const s = esc(t.trim()).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    if (/^[-•*]\s+/.test(t.trim())){ if (!liste){ h += '<ul>'; liste = true; } h += `<li>${s.replace(/^[-•*]\s+/, '')}</li>`; continue; }
    if (liste){ h += '</ul>'; liste = false; }
    if (s) h += `<p>${s.replace(/^#+\s*/, '')}</p>`;
  }
  return h + (liste ? '</ul>' : '');
}
const sure = sn => { sn = Math.max(0, Math.floor(sn || 0)); return sn >= 3600 ? `${Math.floor(sn / 3600)}:${String(Math.floor(sn / 60) % 60).padStart(2, '0')}:${String(sn % 60).padStart(2, '0')}` : `${Math.floor(sn / 60)}:${String(sn % 60).padStart(2, '0')}`; };
const once = z => { const d = Math.floor(Date.now() / 1000 - z); return d < 60 ? 'Şimdi' : d < 3600 ? `${Math.floor(d / 60)} dk önce` : `${Math.floor(d / 3600)} sa önce`; };
async function site(){ const s = await chrome.storage.local.get('site'); return (s.site || 'http://127.0.0.1:8765').replace(/\/$/, ''); }
const meetAdres = a => a.replace(/:8765$/, ':8766');
async function al(yol, o){ const r = await fetch((await site()) + yol, o); if (!r.ok) throw new Error(r.status); return r.json(); }
const yaziyor = () => ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);

// ---------------------------------------------------------------- iskelet: bölümler bir kez kurulur, içerikleri güncellenir
$('#ana').innerHTML = `
  <div id="uyari"></div>
  <section id="bittiB" hidden></section>
  <section id="payB" hidden><h2 id="payBas">Konuşma payı</h2><div class="kart"><div class="pay" id="pay"></div><p class="soluk" id="payNot" style="margin-top:6px"></p></div></section>
  <section id="kocB" hidden><h2>Canlı öneriler <span class="say" id="kocSay" hidden></span></h2><div id="koc"></div></section>
  <section id="amacB" hidden><h2>Bu toplantıdan ne çıkmalı?</h2><div id="amac"></div></section>
  <section id="notB" hidden><h2>Not alın</h2>
    <div class="giris"><input id="notGir" placeholder="Not yazın, ↩ kaydeder" aria-label="Toplantı notu"><button id="isaret" type="button" title="Bu anı önemli diye işaretler; toplantı notlarında o ana bağlanır">★ Önemli an</button></div>
    <div class="notlar" id="notlar"></div></section>
  <section id="ozetB" hidden><h2>Şu ana kadar</h2><div class="kart" id="ozet"></div></section>
  <details id="akisB" hidden><summary id="akisBas">Konuşulanlar</summary><div class="kart"><div class="akis" id="akis"></div></div></details>
  <section id="hazirB" hidden><h2 id="hazirBas">Hazırlık</h2><div class="kart" id="hazir"></div></section>
  <details id="hazirD" hidden><summary>Hazırlık notu</summary><div class="kart" id="hazir2"></div></details>
  <section id="sorB"><h2>Toplantılarınıza sorun</h2>
    <div class="giris"><input id="sorGir" placeholder="Örn. bu ekiple en son ne karar vermiştik?" aria-label="Toplantılarınıza sorun"><button id="sorBtn" type="button">Sor</button></div>
    <div id="sorSonuc"></div></section>
  <section id="sonB" hidden><h2>Son toplantılar</h2><div class="kart liste" id="son"></div></section>
  <section id="ilkB" hidden><h2>Nasıl çalışır</h2><div class="kart"><ol class="adimlar">
    <li><b>Toplantıya girin.</b> Google Meet, Zoom ya da Teams; kayıt kendiliğinden başlar, bir şeye basmanız gerekmez.</li>
    <li><b>Bu panel açık kalsın.</b> Toplantı sürerken konuşma payınız, öneriler ve not alma burada görünür.</li>
    <li><b>Bitince notlar hazırlanır.</b> Özet, kararlar ve size düşen işler birkaç dakika içinde Meet’te açılır.</li></ol>
    <p class="soluk">Google Meet’te altyazıyı açarsanız konuşanların adları daha doğru çıkar.</p></div></section>`;

let ADRES = 'http://127.0.0.1:8765', DURUM = {kayit: false}, KAYIT_AD = '', amacAnahtar = '';
$('#meetAc').onclick = () => chrome.tabs.create({url: meetAdres(ADRES) + '/'});

// ---------------------------------------------------------------- ana döngü
async function yenile(){
  ADRES = await site();
  let v, uzanti = {}, canli = {}, ob = {}, isler = [];
  try{ v = await al('/api/kayit/canli-durum'); }
  catch(e){ return baglantiYok(); }
  [uzanti, canli, ob, isler] = await Promise.all([al('/api/uzanti/durum').catch(() => ({})), al('/api/canli').catch(() => ({})),
    al('/api/on-brifing').catch(() => ({})), al('/api/isler').catch(() => [])]);
  DURUM = v; KAYIT_AD = v.ad || '';
  const toplantida = !!v.kayit || gorusmede(uzanti);
  durumCiz(v, uzanti);
  uyariCiz(v, uzanti);
  kocCiz(v, toplantida);
  payCiz(v, toplantida);
  $('#notB').hidden = !toplantida; if (toplantida) notlarCiz();
  ozetCiz(canli, toplantida);
  const s = hazirlikSec(ob, toplantida);
  hazirlikCiz(s, ob, toplantida);
  amacCiz(s, toplantida);
  bittiCiz(Array.isArray(isler) ? isler : [], toplantida);
  if (!toplantida) sonCiz(); else { $('#sonB').hidden = true; $('#ilkB').hidden = true; }
}

function baglantiYok(){
  $('#durum').className = 'durum uyari'; $('#durumMetin').textContent = 'Mac’teki Meet’e ulaşılamıyor';
  $('#uyari').innerHTML = '<section><div class="kart uyarikart"><p><b>Bu Mac’teki Meet’e ulaşılamıyor.</b></p><p class="soluk">Mac uykudaysa ya da kapalıysa toplantılar kaydedilmez. Mac açılınca Meet kendiliğinden başlar.</p></div></section>';
}

// 2026-10-28: u.aktif = bir toplantı sekmesi açık (giriş ekranı dahil); gerçekten görüşmede olmak u.arama (eski sitede alan yoksa aktif)
const gorusmede = u => !!u.aktif && (u.arama ?? true) && !u.bekleme;
function durumCiz(v, u){
  const d = $('#durum'), m = $('#durumMetin');
  if (v.kayit){
    d.className = 'durum ' + (v.sorun ? 'uyari' : 'kayit');
    m.innerHTML = (v.sorun ? esc(v.sorun) : 'Kaydediliyor') + ` · ${sure(v.sure)}` + (v.canli && v.canli.segment ? ' <small>· yazıya dökülüyor</small>' : '');
  } else if (gorusmede(u)){ d.className = 'durum uyari'; m.textContent = 'Toplantıdasınız · kayıt başlamadı'; }
  else if (u.aktif && u.bekleme){ d.className = 'durum'; m.innerHTML = 'Giriş ekranı <small>· görüşmeye girince kayıt kendiliğinden başlar</small>'; }
  else { d.className = 'durum'; m.innerHTML = 'Toplantı yok <small>· toplantıya girince kayıt kendiliğinden başlar</small>'; }
  const baslik = v.baslik || (u.aktif && u.baslik) || '';
  $('#baslik').textContent = baslik || 'Meet';
  const k = (v.katilimcilar && v.katilimcilar.length ? v.katilimcilar : (u.aktif ? u.katilimcilar || [] : []));
  $('#kisiler').hidden = !k.length; $('#kisiler').textContent = k.join(', ');
}

function uyariCiz(v, u){
  let h = '';
  if (!v.kayit && gorusmede(u)) h = `<div class="kart uyarikart"><p><b>Toplantıdasınız ama kayıt başlamadı.</b></p><p class="soluk">Kayıt, toplantı penceresi ekranda ve ses gelirken birkaç saniye içinde başlar. Bir dakika içinde başlamazsa toplantı sekmesini öne getirin.</p></div>`;
  else if (v.kayit && v.altyazi_kapali) h = `<div class="kart uyarikart"><p><b>Google Meet’te altyazı kapalı.</b></p><p class="soluk">Kayıt sürüyor; ama altyazı açık olursa konuşanların adları ve terimler çok daha doğru çıkar. Toplantı ekranında CC (altyazı) düğmesine basın.</p></div>`;
  else if (v.kayit && v.sorun) h = `<div class="kart uyarikart"><p><b>${esc(v.sorun)}</b></p><p class="soluk">Kaydedici birkaç saniyede bir yeniden bağlanmayı deniyor. Kopan süre kayıtta sessiz kalır.</p></div>`;
  $('#uyari').innerHTML = h ? `<section>${h}</section>` : '';
}

// ---------------------------------------------------------------- canlı koçluk
const TUR_AD = {mentor: 'Öneri', hatirlatma: 'Hatırlatma', oneri: 'Şöyle diyebilirsiniz'};
function kocCiz(v, toplantida){
  $('#kocB').hidden = !toplantida;
  if (!toplantida) return;
  const L = (v.kartlar || []).slice().reverse(), simdi = Date.now() / 1000;
  const yeni = L.filter(k => simdi - (k.zaman || 0) < 120).length;
  $('#kocSay').hidden = !yeni; $('#kocSay').textContent = yeni;
  $('#koc').innerHTML = L.length ? L.slice(0, 4).map((k, i) => {
    const cls = k.tur === 'hatirlatma' ? 'h' : k.tur === 'oneri' ? 'o' : '';
    const ana = k.tur === 'mentor' ? (k.yap || k.gozlem) : k.tur === 'oneri' ? `“${k.soyle}”` : k.metin;
    const alt = k.tur === 'mentor' ? [k.gozlem && k.yap ? `<p class="soluk">${esc(k.gozlem)}</p>` : '', k.soyle ? `<p class="soyle">“${esc(k.soyle)}”</p>` : ''].join('')
      : k.tur === 'oneri' ? (k.durum ? `<p class="soluk">${esc(k.durum)}</p>` : '') : (k.dayanak ? `<p class="soluk">${esc(k.dayanak)}</p>` : '');
    return `<div class="kart koc ${cls} ${simdi - (k.zaman || 0) < 120 ? 'yeni' : i > 0 ? 'eski' : ''}">
      <div class="ust2"><span>${TUR_AD[k.tur] || 'Öneri'}</span><span>${once(k.zaman || simdi)}</span></div>
      <div class="yap">${esc(ana)}</div>${alt}
      <div class="geri" data-z="${k.zaman}"><button type="button" data-g="iyi" class="${k.geri === 'iyi' ? 'sec' : ''}">İşe yaradı</button><button type="button" data-g="kotu" class="${k.geri === 'kotu' ? 'sec' : ''}">Yaramadı</button></div></div>`;
  }).join('') : `<div class="kart"><p class="soluk">${v.kayit ? 'Toplantı sürdükçe burada yerinde, tek cümlelik öneriler belirir: konuşma dengesi, bekleyen karar, kapanış, geçen toplantıdan hatırlatma.' : 'Kayıt başlayınca öneriler burada belirir.'}</p></div>`;
}
$('#koc').addEventListener('click', async e => {
  const b = e.target.closest('[data-g]'); if (!b) return;
  const z = +b.parentElement.dataset.z, secili = b.classList.contains('sec');
  b.parentElement.querySelectorAll('button').forEach(x => x.classList.remove('sec')); if (!secili) b.classList.add('sec');
  try{ await al('/api/kayit/kart', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ad: KAYIT_AD, zaman: z, geri: secili ? null : b.dataset.g})}); }catch(err){}
});

// ---------------------------------------------------------------- konuşma payı (27 Ekim): siz ne kadar konuşuyorsunuz
function payCiz(v, toplantida){
  const P = v.pay && v.pay.paylar;
  $('#payB').hidden = !(toplantida && P && Object.keys(P).length);
  if ($('#payB').hidden) return;
  const ben = (v.pay.ben || '').toLocaleLowerCase('tr');
  const L = Object.entries(P);
  const renk = ['#FF5F1F', '#3b63e6', '#30a46c', '#af52de', '#ff9f0a', '#8e8e93'];
  $('#pay').innerHTML = `<div class="paycubuk">${L.map(([a, y], i) => `<i style="width:${y}%;background:${a.toLocaleLowerCase('tr').startsWith(ben) && ben ? 'var(--vurgu)' : renk[(i % 5) + 1]}" title="${esc(a)} %${y}"></i>`).join('')}</div>`
    + `<div class="payad">${L.map(([a, y], i) => `<span><b style="background:${a.toLocaleLowerCase('tr').startsWith(ben) && ben ? 'var(--vurgu)' : renk[(i % 5) + 1]}"></b>${esc(a.split(' ')[0])} %${y}</span>`).join('')}</div>`;
  const benY = (L.find(([a]) => ben && a.toLocaleLowerCase('tr').startsWith(ben)) || [])[1];
  const kisi = L.length;
  $('#payNot').textContent = benY == null ? (v.pay.yaklasik ? 'Mikrofonunuzdan yaklaşık hesaplanıyor.' : '')
    : benY > Math.max(60, 100 / kisi + 25) ? 'Konuşmanın çoğu sizde; bir soru sorup dinlemek iyi gelebilir.'
    : benY < Math.min(15, 100 / kisi - 10) && kisi <= 4 ? 'Az konuşuyorsunuz; söyleyecekleriniz varsa araya girin.' : (v.pay.yaklasik ? 'Mikrofonunuzdan yaklaşık hesaplanıyor.' : '');
}

// ---------------------------------------------------------------- notlar
async function notlarCiz(){
  try{
    const l = await al('/api/canli/notlar'); const sinir = Date.now() / 1000 - 3 * 3600;
    $('#notlar').innerHTML = l.filter(n => n.ts > sinir).slice(-10).map(n => `<span class="${n.tur}"><b>${new Date(n.ts * 1000).toLocaleTimeString('tr-TR', {hour: '2-digit', minute: '2-digit'})}</b>${n.tur === 'isaret' ? '★ ' : ''}${esc(n.metin || 'Önemli an')}</span>`).join('');
  }catch(e){}
}
async function notEkle(tur){
  const g = $('#notGir'), metin = g.value.trim(); if (tur === 'not' && !metin) return;
  try{ await al('/api/canli/not', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tur, metin})}); g.value = ''; notlarCiz(); }
  catch(e){ g.placeholder = 'Kaydedilemedi; Mac açık ve uyanık mı?'; }
}
$('#notGir').addEventListener('keydown', e => { if (e.key === 'Enter') notEkle(e.metaKey || e.ctrlKey ? 'isaret' : 'not'); });
$('#isaret').onclick = () => notEkle('isaret');

// ---------------------------------------------------------------- şu ana kadar + konuşulanlar
function ozetCiz(c, toplantida){
  const var_ = toplantida && c && c.aktif;
  $('#ozetB').hidden = !var_; $('#akisB').hidden = !var_;
  if (!var_) return;
  const o = c.ozet || {};
  const liste = (a, b) => (o[a] || []).length ? `<p class="soluk" style="margin-top:8px">${b}</p><ul>${o[a].map(x => `<li>${esc(typeof x === 'string' ? x : (x.is || x.metin || ''))}</li>`).join('')}</ul>` : '';
  $('#ozet').innerHTML = (o.ozet ? `<p>${esc(o.ozet)}</p>` : '<p class="soluk">Özet ilk birkaç dakikadan sonra burada oluşur ve üç dakikada bir tazelenir.</p>') + liste('kararlar', 'Kararlar') + liste('yapilacaklar', 'Yapılacaklar');
  const S = c.segmentler || [];
  $('#akisBas').textContent = 'Konuşulanlar';
  const a = $('#akis'), altta = a.scrollHeight - a.scrollTop - a.clientHeight < 30;
  a.innerHTML = S.map(x => `<div><span>${sure(x.bas)}</span>${esc(x.metin)}</div>`).join('') || '<p class="soluk">Henüz yazı yok.</p>';
  if (altta) a.scrollTop = a.scrollHeight;
}

// ---------------------------------------------------------------- hazırlık ve amaç
function hazirlikSec(ob, toplantida){
  const sr = ob.suren, sir = ob.siradaki;
  if (toplantida) return sr || (sir && sir.bas - Date.now() / 1000 < 900 ? sir : null);
  if (ob.bekleme) return sr || {ad: '', bekleme: true, bas: Date.now() / 1000, kisiler: []};   // giriş ekranı: bu toplantının notu (hazırlanıyor olabilir)
  return sir || null;
}
function hazirlikCiz(s, ob, toplantida){
  const k = s ? (s === ob.suren ? ob.suren : (ob.kayitlar || []).find(x => x.id === s.id)) : null;
  const kisiler = s && (s.kisiler || []).length ? `<p class="soluk">${esc(s.kisiler.slice(0, 6).join(', '))}</p>` : '';
  const metin = k && k.metin ? md(k.metin) : '';
  if (toplantida){                                                // toplantıda ikinci planda: katlanır
    $('#hazirB').hidden = true; $('#hazirD').hidden = !metin;
    if (metin) $('#hazir2').innerHTML = metin;
    return;
  }
  $('#hazirD').hidden = true; $('#hazirB').hidden = !s;
  if (!s) return;
  if (ob.bekleme){                                               // giriş ekranı (2026-10-28): not girmeden hazır
    $('#hazirBas').textContent = 'Bu toplantı · girmeden önce';
    const bos = ob.hazirlaniyor ? '<p class="soluk">Bu kişilerle önceki görüşmelerden açık işler ve bekleyen sorular hazırlanıyor…</p>'
      : '<p class="soluk">İçerideki kişilerin adları ya da toplantının adı göründüğünde, önceki görüşmelerden hazırlık notu burada belirir.</p>';
    $('#hazir').innerHTML = `${s.ad ? `<p><b>${esc(s.ad)}</b></p>` : ''}${kisiler}${metin || bos}`;
    return;
  }
  const kala = Math.round((s.bas - Date.now() / 1000) / 60);
  $('#hazirBas').textContent = 'Sıradaki toplantı' + (kala > 0 && kala < 600 ? ` · ${kala} dk sonra` : '');
  $('#hazir').innerHTML = `<p><b>${esc(s.ad || 'Toplantı')}</b></p>${kisiler}${metin || '<p class="soluk">Toplantıdan 10 dakika önce burada bu kişilerle önceki toplantılardan açık işler ve bekleyen sorular belirir.</p>'}`;
}
async function amacCiz(s, toplantida){
  const goster = !!s || toplantida;
  $('#amacB').hidden = !goster; if (!goster) return;
  const anahtar = s ? `${s.bas}|${s.ad}` : 'elle';
  if (anahtar === amacAnahtar || yaziyor()) return;
  amacAnahtar = anahtar;
  let metin = ''; try{ metin = (await al('/api/amac?anahtar=' + encodeURIComponent(anahtar))).metin || ''; }catch(e){}
  amacGoster(metin, s);
}
function amacGoster(metin, s){
  const kutu = $('#amac');
  if (metin){
    kutu.innerHTML = `<div class="kart amac"><div class="m"><b>Amaç</b>${esc(metin)}</div><button class="duz" type="button">Değiştir</button></div>`;
    kutu.querySelector('.duz').onclick = () => amacYaz(metin, s);
  } else amacYaz('', s);
}
function amacYaz(eski, s){
  const kutu = $('#amac');
  kutu.innerHTML = `<div class="giris"><input id="amacGir" placeholder="Örn. bütçe onayı ve teslim tarihi" aria-label="Toplantının amacı"><button type="button" id="amacBtn">Kaydet</button></div><p class="soluk" style="margin:6px 2px 0">Toplantı bitince tutup tutmadığı notlara yazılır; koçluk da buna göre yönlendirir.</p>`;
  const g = $('#amacGir'); g.value = eski;
  const kaydet = async () => {
    const metin = g.value.trim();
    try{ await al('/api/amac', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({anahtar: amacAnahtar || 'elle', metin, ad: s ? s.ad : '', bas: s ? s.bas : 0})}); g.blur(); amacGoster(metin, s); }
    catch(e){ g.placeholder = 'Kaydedilemedi; Mac açık ve uyanık mı?'; }
  };
  g.addEventListener('keydown', e => { if (e.key === 'Enter') kaydet(); });
  $('#amacBtn').onclick = kaydet;
}

// ---------------------------------------------------------------- toplantı bitince
function bittiCiz(isler, toplantida){
  const b = $('#bittiB'), simdi = Date.now() / 1000;
  const T = isler.filter(i => i.toplanti && !i.misafir);
  const suren = T.find(i => i.durum === 'calisiyor' || i.durum === 'sirada');
  const biten = T.filter(i => i.durum === 'bitti' && i.temel && simdi - (i.bitis || 0) < 3 * 3600).sort((a, c) => (c.bitis || 0) - (a.bitis || 0))[0];
  if (toplantida && !suren){ b.hidden = true; return; }
  if (suren){
    b.hidden = false;
    b.innerHTML = `<h2>Son toplantı</h2><div class="kart"><p><b>Notlar hazırlanıyor</b></p><p class="soluk">${esc((suren.adim_metni || '').replace(/^\[\d\/\d\]\s*/, '') || 'Sırada')}</p><div class="cubuk"><i style="width:${Math.max(4, suren.ilerleme || 0)}%"></i></div></div>`;
  } else if (biten){
    b.hidden = false;
    const u = `${meetAdres(ADRES)}/#t=${encodeURIComponent(biten.temel)}`;
    b.innerHTML = `<h2>Son toplantı · ${once(biten.bitis)}</h2><div class="kart"><p><b>${esc((biten.baslik || '').replace(/^\d{4}-\d\d-\d\d \d\d\.\d\d · /, '') || 'Toplantı')}</b></p><p class="soluk" id="bittiKisa"></p><a class="birincil" href="${u}" target="_blank">Notları aç</a></div>`;
    sonKisa(biten.temel);
  } else b.hidden = true;
}
let SON = null, SON_ZAMAN = 0;
async function sonListe(){
  if (SON && Date.now() - SON_ZAMAN < 60000) return SON;
  try{ SON = (await al('/api/gecmis')).filter(x => x.toplanti && !x.onay_bekliyor); SON_ZAMAN = Date.now(); }catch(e){ SON = SON || []; }
  return SON;
}
async function sonKisa(temel){
  const x = (await sonListe()).find(y => y.temel === temel), el = $('#bittiKisa');
  if (el && x && x.kisa) el.textContent = x.kisa.length > 220 ? x.kisa.slice(0, 218) + '…' : x.kisa;
}
async function sonCiz(){
  const ust = $('#bittiB').hidden ? '' : ($('#bittiB a.birincil')?.getAttribute('href') || '');      // üstte kartı olan toplantı listede tekrar etmesin
  const T = await sonListe(), L = T.filter(x => !ust.endsWith('#t=' + encodeURIComponent(x.temel))).slice(0, 4);
  $('#ilkB').hidden = !!T.length || !$('#hazirB').hidden || !$('#bittiB').hidden;          // hiç toplantı yoksa: ilk kullanım kartı
  $('#sonB').hidden = !L.length;
  $('#son').innerHTML = L.map(x => {
    const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d)\.(\d\d) · (.*)$/.exec(x.baslik || '');
    const ad = m ? m[6] : (x.baslik || 'Toplantı'), tarih = m ? `${+m[3]}.${m[2]} ${m[4]}.${m[5]}` : '';
    return `<a href="${meetAdres(ADRES)}/#t=${encodeURIComponent(x.temel)}" target="_blank"><b style="font-weight:500">${esc(ad)}</b><span>${tarih}</span></a>`;
  }).join('');
}

// ---------------------------------------------------------------- sor
async function sor(){
  const g = $('#sorGir'), soru = g.value.trim(); if (!soru) return;
  const s = $('#sorSonuc'); s.innerHTML = '<div class="kart" style="margin-top:8px"><p class="soluk">Toplantılarınıza bakıyorum…</p></div>';
  try{
    const j = await al('/api/sor', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({soru, kapsam: 'toplanti'})});
    const kay = (j.kaynaklar || []).slice(0, 5).map(k => `<a class="kaynak" target="_blank" href="${meetAdres(ADRES)}/#t=${encodeURIComponent(k.temel)}">[${k.no}] ${esc((k.baslik || '').replace(/^\d{4}-\d\d-\d\d \d\d\.\d\d · /, '').slice(0, 40))}</a>`).join('');
    s.innerHTML = `<div class="kart sonuc" style="margin-top:8px">${md(j.cevap || 'Bir şey bulamadım.')}${kay ? `<div>${kay}</div>` : ''}</div>`;
  }catch(e){ s.innerHTML = '<div class="kart" style="margin-top:8px"><p class="soluk">Yanıt alınamadı; Mac açık ve uyanık mı?</p></div>'; }
}
$('#sorGir').addEventListener('keydown', e => { if (e.key === 'Enter') sor(); });
$('#sorBtn').onclick = sor;

yenile(); setInterval(yenile, 5000);

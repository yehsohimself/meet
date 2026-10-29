// background.js - Kaydı yönetir: sekme sesi (yalnızca toplantı sekmesi) + mikrofon → offscreen belgede MediaRecorder → siteye parçalar.
const VARSAYILAN_SITE = 'http://127.0.0.1:8765';
let durum = { kayitId: null, tabId: null, bas: 0, platform: '', baslik: '', katilimcilar: [], kuyruk: [], manuel: false };

async function site(){ const s = await chrome.storage.local.get('site'); return (s.site || VARSAYILAN_SITE).replace(/\/$/, ''); }
async function post(yol, govde){ const r = await fetch((await site()) + yol, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(govde)}); return r.ok ? r.json() : null; }

async function offscreenHazirla(){
  const var_ = await chrome.offscreen.hasDocument?.();
  if (var_) return;
  await chrome.offscreen.createDocument({url: 'offscreen.html', reasons: ['USER_MEDIA'], justification: 'Toplantı sekmesinin sesini ve mikrofonu kaydetmek için'});
}

async function kaydiBaslat(tabId, bilgi){
  if (durum.kayitId) return;
  const s = await site();
  // Önce Chrome sekme sesine izin veriyor mu bak; vermiyorsa sitede kayıt AÇMA (boş kayıt birikmesin).
  let streamId = null;
  try{
    const sekme = await chrome.tabs.get(tabId).catch(() => null);
    if (!sekme || !/^https:\/\/(meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|[^/]*\.zoom\.us)\//.test(sekme.url || '')){ ikon('', 'Bu sayfa bir toplantı sayfası değil'); return; }
    streamId = await chrome.tabCapture.getMediaStreamId({targetTabId: tabId});
  }
  catch(e){ ikon('', 'Adlar aktarılıyor; ses masaüstü kaydediciden'); return; }   // Chrome izin vermedi (simgeye tıklanmamış): sesi masaüstü kaydedici alır; beklenen durum, hata değil
  const j = await post('/api/kayit/baslat', {baslik: '', kaynak: 'uzantı:' + (bilgi.platform || 'web')}).catch(() => null);
  if (!j || !j.id){ ikon('!', 'Site kapalı'); return; }
  await offscreenHazirla();
  durum = {...durum, kayitId: j.id, tabId, bas: Date.now(), platform: bilgi.platform || '', baslik: bilgi.baslik || '', katilimcilar: bilgi.katilimcilar || []};
  chrome.runtime.sendMessage({hedef: 'offscreen', tur: 'baslat', streamId, kayitId: j.id, site: s});
  chrome.tabs.sendMessage(tabId, {tur: 'kayit_durumu', id: j.id, bas: durum.bas}).catch(() => {});
  ikon('●', 'Kaydediliyor');
  chrome.storage.session.set({kayit: {id: j.id, bas: durum.bas, tabId}});
}

async function kaydiDurdur(){
  if (!durum.kayitId) return;
  const id = durum.kayitId, tabId = durum.tabId;
  chrome.runtime.sendMessage({hedef: 'offscreen', tur: 'durdur'});
  await new Promise(r => setTimeout(r, 2500));                       // son parça yüklensin
  await post(`/api/kayit/${id}/konusmacilar`, {olaylar: durum.kuyruk.splice(0), katilimcilar: durum.katilimcilar, baslik: durum.baslik}).catch(() => {});
  await post(`/api/kayit/${id}/bitir`, {baslik: '', katilimcilar: durum.katilimcilar}).catch(() => {});
  durum = {...durum, kayitId: null, tabId: null, bas: 0, manuel: false};
  chrome.storage.session.remove('kayit');
  if (tabId) chrome.tabs.sendMessage(tabId, {tur: 'kayit_durumu', id: null}).catch(() => {});
  ikon('', 'Kayıt bitti; yazıya dökülüyor');
}

function ikon(metin, baslik){ chrome.action.setBadgeText({text: metin}); chrome.action.setBadgeBackgroundColor({color: metin === '●' ? '#ff3b30' : '#FF5F1F'}); chrome.action.setTitle({title: 'Meet · ' + baslik}); }

chrome.runtime.onMessage.addListener((m, sender, yanit) => {
  (async () => { try {
    if (m.hedef === 'offscreen') return;                              // offscreen'e giden mesajlar
    const tabId = sender.tab?.id;
    if (m.tur === 'nabiz'){
      const r = await post('/api/uzanti/durum', {surum: chrome.runtime.getManifest().version, aktif: m.aktif, bekleme: !!m.bekleme, platform: m.platform, baslik: m.baslik, katilimcilar: m.katilimcilar, kayit: durum.kayitId || '', tani: m.tani || null}).catch(() => null);
      // Sekme başına tek deneme; servis çalışanı yeniden başlasa da (Chrome arka planı sık kapatır) tekrarlanmasın.
      const ss = await chrome.storage.session.get('denendi').catch(() => ({}));
      if (m.aktif && !durum.kayitId && r && r.oto_kayit && tabId && ss.denendi !== tabId){ await chrome.storage.session.set({denendi: tabId}); await kaydiBaslat(tabId, m); }
      if (!m.aktif && ss.denendi === tabId) await chrome.storage.session.remove('denendi');
      if (m.katilimcilar?.length) durum.katilimcilar = m.katilimcilar;
      if (m.baslik) durum.baslik = m.baslik;
    }
    if (m.tur === 'arama_basladi' && tabId){ const r = await post('/api/uzanti/durum', {surum: chrome.runtime.getManifest().version, aktif: true, platform: m.platform, baslik: m.baslik, katilimcilar: m.katilimcilar}).catch(() => null); if (r && r.oto_kayit) await kaydiBaslat(tabId, m); }
    if (m.tur === 'arama_bitti' && durum.kayitId && !durum.manuel) await kaydiDurdur();
    if (m.tur === 'olaylar'){ if (m.katilimcilar?.length) durum.katilimcilar = m.katilimcilar;
      if (durum.kayitId){ durum.kuyruk.push(...(m.olaylar || []).map(o => ({t: o.t ?? (o.ts - durum.bas / 1000), ad: o.ad})));
        if (durum.kuyruk.length) await post(`/api/kayit/${durum.kayitId}/konusmacilar`, {olaylar: durum.kuyruk.splice(0), katilimcilar: durum.katilimcilar, baslik: m.baslik}).catch(() => {}); }
      else if ((m.olaylar || []).length || m.katilimcilar?.length) await post('/api/uzanti/olaylar', {olaylar: (m.olaylar || []).map(o => ({ts: o.ts, ad: o.ad})), katilimcilar: m.katilimcilar, baslik: m.baslik}).catch(() => {}); }
    if (m.tur === 'brif'){ const j = await fetch((await site()) + '/api/on-brifing').then(r => r.json()).catch(() => null); return yanit(j || {}); }   // giriş ekranı kartı
    if (m.tur === 'panel_ac'){ try{ await chrome.sidePanel.open({tabId}); return yanit({tamam: true}); }catch(e){ return yanit({tamam: false}); } }
    if (m.tur === 'kayit_durum'){ const j = await kayitDurumAl(); return yanit(j || {kayit: false, baglanti: false}); }
    if (m.tur === 'altyazi'){ await post('/api/uzanti/altyazi', {satirlar: m.satirlar || [], platform: m.platform, baslik: m.baslik}).catch(() => null); return yanit({tamam: true}); }
    if (m.tur === 'durum'){ yanit({kayitId: durum.kayitId, bas: durum.bas, platform: durum.platform, baslik: durum.baslik, katilimcilar: durum.katilimcilar}); return; }
    if (m.tur === 'manuel_baslat'){ const [t] = await chrome.tabs.query({active: true, currentWindow: true}); if (t) { durum.manuel = true; await kaydiBaslat(t.id, {platform: 'manuel', baslik: t.title}); } }
    if (m.tur === 'manuel_durdur') await kaydiDurdur();
    if (m.tur === 'offscreen_hata'){ ikon('!', m.mesaj || 'Kayıt hatası'); }
    yanit({tamam: true});
  } catch(e){ try{ yanit({tamam: false, hata: String(e)}); }catch(_){} } })();   // hiçbir hata "Uncaught" olarak kalmasın
  return true;
});

chrome.tabs.onRemoved.addListener(tabId => { if (durum.kayitId && tabId === durum.tabId) kaydiDurdur(); });

// ---- Kendini iyileştirme (2026-10-20): 16-20 Ekim'de bozuk content.js uzantıyı susturdu ve kimse fark etmedi. ----
// 1) Diskteki dosyalar değişince (yeni sürüm) uzantı kendini yeniler; elle chrome://extensions → yenile gerekmez.
// 2) Kurulum/yenilemede açık toplantı sekmelerine içerik betiği yeniden yerleştirilir (sayfayı yenilemek gerekmez).
// 3) Her dakika siteye "uzantı canlı" nabzı gider (toplantı olmasa da); site uzantı susarsa Transcript'te uyarır.
const TOPLANTI_DESEN = ['https://meet.google.com/*', 'https://teams.microsoft.com/*', 'https://teams.live.com/*', 'https://*.zoom.us/*'];
async function diskSurumu(){ try{ const r = await fetch(chrome.runtime.getURL('manifest.json') + '?t=' + Date.now(), {cache: 'no-store'}); return (await r.json()).version; }catch(e){ return null; } }
async function iyiles(){
  const d = await diskSurumu();
  if (d && d !== chrome.runtime.getManifest().version){ chrome.runtime.reload(); return; }
  post('/api/uzanti/canli', {surum: chrome.runtime.getManifest().version}).catch(() => {});
}
async function sekmelereYerlestir(){
  try{ const sekmeler = await chrome.tabs.query({url: TOPLANTI_DESEN});
    for (const t of sekmeler){ try{ await chrome.scripting.executeScript({target: {tabId: t.id}, files: ['content.js']}); }catch(e){} } }catch(e){}
}
// Simgede kayıt işareti (3.13, 2026-10-27): Mac'teki kaydedici toplantıyı kaydederken araç çubuğundaki simgede kırmızı "REC", sorun varsa turuncu "!".
// Google Meet sekmesi açık değilken de (başka sekmede not alırken) kaydın sürdüğü görünsün. Toplantı sekmesi 5 sn'de bir sorar; ayrıca 30 sn'de bir alarm.
async function kayitDurumAl(){
  let j = null;
  try{ const r = await fetch((await site()) + '/api/kayit/canli-durum'); j = r.ok ? await r.json() : null; }catch(e){}
  if (durum.kayitId) return j;                                        // uzantının kendi sekme kaydı kendi işaretini kullanır
  const sure = sn => sn >= 3600 ? `${Math.floor(sn / 3600)}:${String(Math.floor(sn / 60) % 60).padStart(2, '0')}:${String(sn % 60).padStart(2, '0')}` : `${Math.floor(sn / 60)}:${String(sn % 60).padStart(2, '0')}`;
  try{
    if (j && j.kayit){
      chrome.action.setBadgeText({text: j.sorun ? '!' : 'REC'});
      chrome.action.setBadgeBackgroundColor({color: j.sorun ? '#ff9f0a' : '#ff3b30'});
      chrome.action.setBadgeTextColor?.({color: '#ffffff'});
      chrome.action.setTitle({title: 'Meet · ' + (j.sorun || 'Kaydediliyor') + ' · ' + sure(j.sure || 0)});
    } else {
      const b = await chrome.action.getBadgeText({});
      if (b === 'REC' || b === '!'){ chrome.action.setBadgeText({text: ''}); chrome.action.setTitle({title: 'Meet Toplantı Yardımcısı'}); }
    }
  }catch(e){}
  return j;
}
chrome.alarms.create('kayit', {periodInMinutes: 0.5}); kayitDurumAl();
// Simgeye tıklayınca yan panel açılır (3.15; eski açılır penceredeki düğmeler işlevsizdi). Toplantı sekmesindeki göstergeden de açılabilir.
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {});
chrome.alarms.create('iyiles', {periodInMinutes: 1});
// İzlenen hesap listesi (Ghost, 3.3): yarım saatte bir siteden alınır; x.js ana akışta yalnız bu hesapları okur
chrome.alarms.onAlarm.addListener(a => { if (a.name === 'kayit') kayitDurumAl(); if (a.name === 'iyiles') iyiles(); });
chrome.runtime.onInstalled.addListener(() => { sekmelereYerlestir(); iyiles(); });
chrome.runtime.onStartup.addListener(() => iyiles());

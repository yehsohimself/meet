// offscreen.js - Sekme sesi + mikrofonu karıştırır, 15 sn'lik parçalar halinde siteye yükler.
let rec = null, ctx = null, akislar = [], kuyruk = Promise.resolve(), kayitId = null, site = '';

chrome.runtime.onMessage.addListener(async m => {
  if (m.hedef !== 'offscreen') return;
  if (m.tur === 'baslat') await baslat(m);
  if (m.tur === 'durdur') await durdur();
});

async function baslat(m){
  if (rec) return;
  kayitId = m.kayitId; site = m.site;
  let sekme = null, mik = null;
  try{ sekme = await navigator.mediaDevices.getUserMedia({audio: {mandatory: {chromeMediaSource: 'tab', chromeMediaSourceId: m.streamId}}, video: false}); }
  catch(e){ chrome.runtime.sendMessage({tur: 'offscreen_hata', mesaj: 'Sekme sesi alınamadı'}); return; }
  try{ mik = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}}); }
  catch(e){ chrome.runtime.sendMessage({tur: 'offscreen_hata', mesaj: 'Mikrofon izni yok (uzantı ayarlarından verin)'}); }
  ctx = new AudioContext(); const dest = ctx.createMediaStreamDestination();
  const sekmeKaynak = ctx.createMediaStreamSource(sekme); sekmeKaynak.connect(dest); sekmeKaynak.connect(ctx.destination);   // kullanıcı duymaya devam etsin
  if (mik){ ctx.createMediaStreamSource(mik).connect(dest); }
  akislar = [sekme, mik].filter(Boolean);
  const mime = ['audio/webm;codecs=opus', 'audio/webm'].find(x => MediaRecorder.isTypeSupported(x)) || '';
  rec = new MediaRecorder(dest.stream, mime ? {mimeType: mime, audioBitsPerSecond: 64000} : {});
  rec.ondataavailable = e => { if (!e.data?.size) return; const b = e.data; kuyruk = kuyruk.then(async () => { for (let d = 0; d < 3; d++){ try{ const r = await fetch(`${site}/api/kayit/${kayitId}/parca`, {method: 'POST', body: b}); if (r.ok) return; }catch(err){} await new Promise(x => setTimeout(x, 2000)); } }); };
  rec.start(15000);
}

async function durdur(){
  if (!rec) return;
  const r = rec; rec = null;
  await new Promise(res => { r.onstop = res; r.stop(); });
  await kuyruk;
  akislar.forEach(a => a.getTracks().forEach(t => t.stop())); akislar = [];
  try{ await ctx.close(); }catch(e){} ctx = null;
}

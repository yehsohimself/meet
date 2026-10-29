/* meet_ek.js — Meet'in kendini geliştiren yapısının arayüzü (2026-10-24). index.html'e tek satırla yüklenir; yalnız Meet'te (data-urun="note") çalışır.
   1) Başlıkta "Meet durumu" düğmesi → pencere: sağlık, kendiliğinden yapılanlar (geri alınabilir), ölçüler, haftalık değerlendirme, öneriler, yenilikler.
   2) Toplantı sayfası: adsız kişinin yanında ▶ (sesini dinleyip ad vermek için), "Ekranda paylaşılanlar" şeridi, sesinden tanındı notu (Geri al).
   3) "Sizden beklenenler" → Başkalarından: gecikmiş işe "Hatırlat" (nazik takip mesajı taslağı; Kopyala ya da Mail'de taslak; gönderilmez). */
(() => {
  if (document.documentElement.dataset.urun !== 'note') return;
  const MISAFIR = document.documentElement.dataset.misafir === '1';   // davetli: yalnız ses örneği ve ekranda paylaşılanlar (sahibin durumu, sözleri yok)
  const UZAK = document.documentElement.dataset.uzak === '1';         // eşleştirilmiş telefondan dışarıdan: davet ve telefon ayarları yalnız Mac'te
  // Telefonda (ekran paylaşımı yok) kayıt doğrudan mikrofonla: "bilgisayar sesi" seçeneği gizlenir (2026-10-25)
  if (!navigator.mediaDevices?.getDisplayMedia){
    const st = document.createElement('style'); st.textContent = '#kayitKaynak,#kayitSistemEkle{display:none!important}'; document.head.append(st);
    const mik = () => document.querySelector('#kayitKaynak button:not([data-v="sistem"])')?.click();
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mik); else setTimeout(mik, 0);
  }
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/static/meet_ek.css?v=19'; document.head.append(css);
  const $q = (s, k = document) => k.querySelector(s), $$q = (s, k = document) => [...k.querySelectorAll(s)];
  const e = s => (typeof esc === 'function' ? esc(s) : String(s ?? ''));
  const j = async (url, govde) => { const r = await fetch(url, govde === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(govde)});
    const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.hata || 'İşlem yapılamadı'); return d; };
  const bildir = (t, b, f) => (typeof toast === 'function' ? toast(t, b, f) : null);
  const gunAd = z => { const f = (Date.now() / 1000 - z) / 86400; return f < 1 ? 'bugün' : f < 2 ? 'dün' : Math.round(f) + ' gün önce'; };

  /* ---------------------------------------------------------------- 1) Meet durumu */
  const dlg = document.createElement('dialog'); dlg.className = 'sheet panel mdlg'; dlg.id = 'meetDlg';
  dlg.innerHTML = '<div class="ktop"><h4>Meet durumu</h4><button type="button" class="tiny" data-k="kapat">Kapat</button></div><div id="meetIc"><p class="hint">Yükleniyor…</p></div>';
  document.body.append(dlg);
  dlg.addEventListener('click', ev => { if (ev.target === dlg || ev.target.dataset.k === 'kapat') dlg.close(); });
  let DUR = null, zt = null;
  async function durumYukle(){ try{ DUR = await j('/api/meet/durum'); }catch(_){ DUR = null; } dugmeCiz(); if (dlg.open) icCiz(); }
  // Giriş: masaüstünde durum satırının sonunda "Durum" bağlantısı (satır 15 sn'de bir yeniden yazılır, gözlemci geri ekler); telefonda satır gizli, hap düğme
  const ac = () => { icCiz(); dlg.showModal(); durumYukle(); };
  function etiket(){ if (!DUR) return {sinif: 'bos', metin: 'Durum', ek: ''}; const S = DUR?.saglik || [], hata = S.filter(s => s.durum === 'hata').length, uy = S.filter(s => s.durum === 'uyari').length;
    const yeni = (DUR?.oneriler || []).filter(o => o.durum === 'bekliyor').length;
    return {sinif: hata ? 'hata' : uy ? 'uyari' : 'ok', metin: hata ? `${hata} sorun` : 'Durum', ek: yeni ? `${yeni} öneri` : ''}; }   // turuncu nokta notları söyler; sayı yalnız sorun ve öneri için
  function dugmeCiz(){
    const e_ = etiket(), sat = $q('#tDurumSat');
    // 2026-10-29 sadeleştirme: ana sayfada yalnız gerçek sorun (hata) ya da bekleyen öneri varken; uyarılar kendiliğinden düzelir ya da durum
    // satırında zaten yazar (disk). Meet durumu her zaman Ayarlar → "Meet durumu ve gelişmiş ayarlar"dan açılır.
    if (e_.sinif !== 'hata' && !e_.ek){ $q('.mdlink', sat || document)?.remove(); $q('#meetDurumBtn')?.remove(); return; }
    if (e_.sinif !== 'hata'){ e_.metin = e_.ek; e_.ek = ''; e_.sinif = 'ok'; }
    if (sat && sat.textContent.trim()){
      let l = $q('.mdlink', sat);
      if (!l){ l = document.createElement('button'); l.type = 'button'; l.className = 'textbtn mdlink'; l.onclick = ac; sat.append(' · ', l); }
      const h = `<i class="${e_.sinif}"></i>${e_.metin}${e_.ek ? `<span>${e_.ek}</span>` : ''}`; if (l.innerHTML !== h) l.innerHTML = h; }
    const yer = $q('#tBekBtn'); if (!yer) return;
    let b = $q('#meetDurumBtn');
    if (!b){ b = document.createElement('button'); b.type = 'button'; b.id = 'meetDurumBtn'; b.onclick = ac; yer.after(b); }
    b.title = 'Kayıt, uzantı, takvim, adlar ve Meet’in kendiliğinden yaptıkları';
    b.className = 'mdbtn ' + e_.sinif; b.innerHTML = `<i></i>${e_.metin === 'Durum' ? 'Meet durumu' : e_.metin}${e_.ek ? `<span>${e_.ek}</span>` : ''}`;
  }
  const OLCU = o => {
    const y = (a, b) => b ? Math.round(100 * a / b) + '%' : '—';
    return [['Toplantı (30 gün)', `${o.toplanti} · ${Math.round((o.sure_dk || 0) / 60 * 10) / 10} sa`],
            ['Adı konmamış kişi', `${o.adsiz_kume} / ${o.kume} (${y(o.adsiz_kume, o.kume)})`],
            ['Sizi tanıdığı toplantı', `${o.sizi_tanidi} / ${o.toplanti}`],
            ['Müşterisi bulunamayan', `${o.diger}`],
            ['Doğrulanan alıntı', `${o.alinti_dogru} / ${o.alinti}`],
            ['Uzantıdan gelen adlar', `${o.uzanti_ad} / ${o.tarayici} tarayıcı toplantısı`],
            ['Toplantıda canlı öneri', `${o.canli_kart}`],
            ['Sizin düzeltmeleriniz', `${o.duzeltme}`]];
  };
  const TUR = {ad: 'Ad', ses: 'Ses', baslik: 'Toplantı adı', adim: 'Eksik adım', musteri: 'Müşteri', soz: 'Söz', uyari: 'Uyarı', geri: 'Geri alındı'};
  function icCiz(){
    const k = $q('#meetIc'); if (!DUR){ k.innerHTML = '<p class="hint">Durum alınamadı; birazdan yeniden deneyin.</p>'; return; }
    const S = DUR.saglik || [], o = DUR.olcu || {}, R = DUR.radar || {}, rp = DUR.rapor || {};
    const sirala = {hata: 0, uyari: 1, ok: 2};
    k.innerHTML = `
      <section class="mbol"><div class="mbas"><h5>Durum</h5><span class="mara">${DUR.calisiyor ? `<span class="spin"></span>${e(DUR.calisiyor)}` : ''}<button type="button" class="tiny" data-k="kontrol">Şimdi kontrol et</button></span></div>
        <ul class="msag">${[...S].sort((a, b) => sirala[a.durum] - sirala[b.durum]).map(s => `<li class="${s.durum}"><i></i><span><b>${e(s.ad)}</b> ${e(s.metin)}${s.cozum && s.durum !== 'ok' ? `<small>${e(s.cozum)}</small>` : ''}</span></li>`).join('')}</ul></section>
      ${rp.ozet ? `<section class="mbol"><h5>Bu haftanın değerlendirmesi <span class="pr-gri">${e(gunAd(rp.zaman))}</span></h5><p class="mozet">${e(rp.ozet)}</p>
        ${(DUR.dersler || []).length ? `<ul class="mders">${DUR.dersler.map(d => `<li>${e(d.ders)}</li>`).join('')}</ul>` : ''}</section>` : ''}
      <section class="mbol"><h5>Kendiliğinden yapılanlar</h5>${(DUR.olaylar || []).length ? `<ul class="molay">${DUR.olaylar.slice(0, 14).map((x, i) => `<li><span class="mt">${e(TUR[x.tur] || x.tur)}</span><span>${e(x.metin)}${x.temel ? ` <button type="button" class="textbtn" data-ac="${e(x.temel)}">Aç</button>` : ''}${x.geri && x.tur === 'ad' ? ` <button type="button" class="textbtn" data-geri="${i}">Geri al</button>` : ''}</span><em>${e(gunAd(x.zaman))}</em></li>`).join('')}</ul>` : '<p class="hint">Henüz yok. Eksik adımlar, adsız kişiler ve yanlış adlar düzeltildikçe burada görünür.</p>'}</section>
      <section class="mbol"><h5>Ölçüler <span class="pr-gri">son 30 gün</span></h5><dl class="molcu">${OLCU(o).map(([a, b]) => `<dt>${e(a)}</dt><dd>${e(b)}</dd>`).join('')}</dl></section>
      <section class="mbol"><h5>Öneriler</h5>${(DUR.oneriler || []).length ? DUR.oneriler.map(x => `<article class="moneri ${x.durum}"><div><b>${e(x.baslik)}</b><span class="mt">${x.buyukluk === 'buyuk' ? 'Büyük iş' : 'Küçük iş'} · ${x.nereden === 'radar' ? 'yenilik' : 'ölçüm'}</span></div><p>${e(x.neden)}</p>${x.nasil ? `<p class="mnasil">${e(x.nasil)}</p>` : ''}${x.kaynak ? `<a class="tiny" href="${e(x.kaynak)}" target="_blank" rel="noopener">Kaynak ↗</a>` : ''}
          <div class="mkarar">${x.durum === 'kabul' ? '<span class="mkabul">Yapılacaklara eklendi</span>' : `<button type="button" class="sbtn" data-oneri="${e(x.id)}" data-kabul="1">Yapalım</button><button type="button" class="tiny" data-oneri="${e(x.id)}" data-kabul="0">Gerek yok</button>`}</div></article>`).join('')
        : '<p class="hint">Bekleyen öneri yok.</p>'}</section>
      <section class="mbol"><div class="mbas"><h5>Yenilikler</h5><span class="mara"><button type="button" class="tiny" data-k="radar">Şimdi tara</button></span></div>
        <p class="hint">${R.son ? `Son tarama ${e(gunAd(R.son))}.` : 'Haftada bir taranır.'} Google Meet, Teams ve Zoom güncellemeleri, benzer uygulamalardaki yenilikler, yeni ses modelleri.</p>
        ${(R.uyarilar || []).length ? `<ul class="msag">${R.uyarilar.slice(0, 5).map(u => `<li class="uyari"><i></i><span><b>${e(u.baslik)}</b> ${e(u.neden || '')}${u.kaynak ? ` <a class="tiny" href="${e(u.kaynak)}" target="_blank" rel="noopener">↗</a>` : ''}</span></li>`).join('')}</ul>` : ''}
</section>
      <section class="mbol"><h5>Ayarlar</h5>${[['meet_gelisim', 'Kendiliğinden onar', 'Eksik adımları tamamlar, eski toplantılardaki adsız kişileri tanınan seslerle adlandırır, yanlış toplantı adlarını düzeltir', true],
        ['ekran_kareleri', 'Ekranda paylaşılanları kaydet', 'Toplantı penceresinde ekran değiştikçe küçük bir kare alır; sunumlar okunup toplantı sayfasında gösterilir', true],
        ['meet_davetler', 'E-posta davetlerinden takvim', 'Mail uygulamasındaki toplantı davetlerini okur; iş hesabınız Mail’e ekliyse iş toplantılarında hazırlık notu gelir', false]]
        .map(([a, ad, ac, vars]) => `<label class="mayar"><span><b>${ad}</b><small>${ac}</small></span><button type="button" class="tog" role="switch" data-ayar="${a}" aria-checked="${!!((DUR.ayar || {})[a] ?? vars)}" aria-label="${ad}"></button></label>`).join('')}</section>`;
    k.querySelector('[data-k="kontrol"]').onclick = async ev => { ev.target.disabled = true; try{ await j('/api/meet/kontrol', {}); bildir('Kontrol ediyorum; bitince burada görünür'); }catch(x){ bildir(x.message); } setTimeout(durumYukle, 4000); };
    k.querySelector('[data-k="radar"]').onclick = async ev => { ev.target.disabled = true; try{ await j('/api/meet/radar', {}); bildir('Yenilikleri tarıyorum; birkaç dakika sürer'); }catch(x){ bildir(x.message); } setTimeout(durumYukle, 4000); };
    $$q('[data-oneri]', k).forEach(b => b.onclick = async () => { await j('/api/meet/oneri/' + b.dataset.oneri, {kabul: b.dataset.kabul === '1'}); bildir(b.dataset.kabul === '1' ? 'Yapılacaklara eklendi' : 'Bir daha önermem'); durumYukle(); });
    $$q('[data-ac]', k).forEach(b => b.onclick = () => { dlg.close(); sonucGoster(b.dataset.ac, {ozetOncelikli: true}); });
    $$q('[data-geri]', k).forEach(b => b.onclick = async () => { const x = DUR.olaylar[+b.dataset.geri];
      try{ await j('/api/meet/geri-al', {temel: x.temel, degisim: Object.fromEntries(Object.entries(x.geri))}); bildir('Geri alındı; bu ad o toplantıya bir daha verilmez'); durumYukle(); }catch(err){ bildir(err.message); } });
    $$q('[data-ayar]', k).forEach(c => c.onclick = async ev => { ev.preventDefault(); const v = c.getAttribute('aria-checked') !== 'true'; c.setAttribute('aria-checked', v);   // 27 Ekim: checkbox'lı .tog açık/kapalı görünmüyordu
      try{ await j('/api/meet/ayar', {anahtar: c.dataset.ayar, deger: v}); bildir('Kaydedildi'); }catch(x){ bildir(x.message); c.setAttribute('aria-checked', !v); } });
    clearTimeout(zt); if (DUR.calisiyor) zt = setTimeout(durumYukle, 6000);
  }
  if (!MISAFIR){ durumYukle(); setInterval(() => { if (document.visibilityState === 'visible') durumYukle(); }, 120000); }

  function adsizEkle(temel, d){
    if (!d || !$q('.tkkim .spk')) return;
    const harita = Object.fromEntries((d.kisiler || []).map(x => [x.ad, x]));
    $$q('.tkkim .spk').forEach(sp => {
      const inp = $q('input', sp); const x = harita[inp?.dataset.eski || inp?.value]; if (!x || !x.adsiz) return;
      if (d.ornek && !$q('.mses', sp)){                           // ▶ adsız kişinin sesi
        const b = document.createElement('button'); b.type = 'button'; b.className = 'mses'; b.title = `Bu kişinin sesini dinleyin (${Math.round(x.sure / 60) || '<1'} dk konuştu), sonra adını yazın`; b.textContent = '▶';
        b.onclick = ev => { ev.stopPropagation(); if (ses){ ses.pause(); } ses = new Audio(`/api/meet/ses/${encodeURIComponent(temel)}/${encodeURIComponent(x.k)}.m4a`); ses.play().catch(() => bildir('Ses örneği alınamadı')); };
        sp.prepend(b);
      }
      // tek dokunuşla ad (27 Ekim): toplantıdaki adı verilmemiş katılımcılar; öneri varsa önde ve vurgulu
      if (MISAFIR || x.sure < 10 || sp.nextElementSibling?.classList.contains('madlar')) return;
      const oner = (d.oneri || {})[x.ad]; const L = [...new Set([oner, ...(d.adaylar || [])].filter(Boolean))].slice(0, 6); if (!L.length) return;
      const k = document.createElement('div'); k.className = 'madlar';
      k.innerHTML = `<span>${e(x.ad)} kim?</span>` + L.map(a => `<button type="button" class="${a === oner ? 'oner' : ''}" title="${a === oner ? 'Konuşmadaki ipuçlarına göre önerilen ad · ' : ''}Bu adı verir; ses öğrenilir, sonraki toplantılarda kendiliğinden tanınır">${e(a)}</button>`).join('');
      k.querySelectorAll('button').forEach(b => b.onclick = () => { inp.value = b.textContent; inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); k.remove(); });
      sp.after(k);
    });
    const ads = (d.kisiler || []).filter(x => x.adsiz && x.sure >= 30).length;
    $q('.tkkim')?.classList.toggle('adsizvar', !!ads);              // dar ekranda 'Kimler vardı' gizli; adsız kişi varsa görünsün
    if (ads && !$q('.tkkim .mipucu')){ const p = document.createElement('p'); p.className = 'mipucu'; p.textContent = `${ads} kişinin adı yok. ▶ ile dinleyin, aşağıdan seçin ya da adını yazın.`; p.title = 'Ses öğrenilir; sonraki ve eski toplantılarda kendiliğinden tanınır.'; $q('.tkkim h5')?.after(p); }
  }

  /* ---------------------------------------------------------------- 2) toplantı sayfası */
  let sonTemel = '', ses = null;
  let sayfaVeri = null;                                          // {temel, d}: toplantı başına bir kez alınır; düğmeler her yeniden çizimde eklenir
  async function sayfaKur(){
    const temel = (typeof state !== 'undefined' && state.aktifTemel) || ''; const ku = $q('#tKunye');
    if (!temel || !ku) return;
    if (sayfaVeri && sayfaVeri.temel === temel){ if (sayfaVeri.d) adsizEkle(temel, sayfaVeri.d); if (ku.dataset.meet === temel) return; }
    ku.dataset.meet = temel;
    if (!sayfaVeri || sayfaVeri.temel !== temel){
      sayfaVeri = {temel, d: null}; sonTemel = temel;
      let d; try{ d = await j('/api/meet/toplanti/' + encodeURIComponent(temel)); }catch(_){ sayfaVeri = null; return; }
      if (sonTemel !== temel) return;
      sayfaVeri.d = d;
    }
    const d = sayfaVeri.d; if (!d) return;
    adsizEkle(temel, d);
    // ekranda paylaşılanlar
    if ((d.ekran || []).length && !$q('#tEkran')){
      const z = sn => `${Math.floor(sn / 60)}:${String(sn % 60).padStart(2, '0')}`;
      const k = document.createElement('div'); k.className = 'ozet tekran'; k.id = 'tEkran'; k.dataset.sek = 'ozet';
      k.innerHTML = `<h4>Ekranda paylaşılanlar <span class="pr-gri">${d.ekran.length}</span></h4><div class="tekr${d.ekran.length > 8 ? ' kisa' : ''}">${d.ekran.map(x => `<figure><a href="/meet-ekran/${encodeURIComponent(temel)}/${x.kare}" target="_blank" rel="noopener" title="${e(x.yazi)}"><img src="/meet-ekran/${encodeURIComponent(temel)}/${x.kare}" alt="" loading="lazy"></a><figcaption><button type="button" class="zt" data-sn="${x.sn}">${z(x.sn)}</button></figcaption></figure>`).join('')}</div>`;
      ($q('#tOzetEk') || $q('#kisacaKutu'))?.after(k);
      if (d.ekran.length > 8){ const b = document.createElement('button'); b.type = 'button'; b.className = 'tiny tekr-tum'; b.textContent = `Hepsini göster (${d.ekran.length})`;
        b.onclick = () => { $q('.tekr', k).classList.remove('kisa'); b.remove(); }; k.append(b); }
      $$q('[data-sn]', k).forEach(b => b.onclick = () => gitSn(+b.dataset.sn));
    }
  }

  /* ---------------------------------------------------------------- 3) Başkalarından: hatırlat */
  function hatirlatEkle(){
    if (typeof SOZ === 'undefined' || SOZ.sek !== 'bekledigin') return;
    $$q('#bekIc .tsliste li, #tSoz .tsliste li').forEach(li => { if ($q('.mhat', li)) return; const c = $q('input[type=checkbox]', li); if (!c) return;
      const b = document.createElement('button'); b.type = 'button'; b.className = 'tiny mhat'; b.textContent = 'Hatırlat'; b.title = 'Nazik bir takip mesajı taslağı hazırlar; siz gönderirsiniz';
      b.onclick = async ev => { ev.stopPropagation(); b.disabled = true; b.textContent = 'Yazılıyor…';
        try{ const r = await j('/api/meet/hatirlat', {temel: c.dataset.t, k: +c.dataset.k, i: +c.dataset.i}); hatirlatPencere(r); }catch(x){ bildir(x.message); }
        b.disabled = false; b.textContent = 'Hatırlat'; };
      $q('.tsgun', li)?.before(b); });
  }
  function hatirlatPencere(r){
    let p = $q('#mHatDlg'); if (!p){ p = document.createElement('dialog'); p.id = 'mHatDlg'; p.className = 'sheet panel mdlg'; document.body.append(p); }
    p.innerHTML = `<div class="ktop"><h4>${e(r.kim)} için takip mesajı</h4><button type="button" class="tiny" data-k="kapat">Kapat</button></div>
      <p class="hint">${e(r.konu)} · gönderilmez; düzenleyip siz gönderirsiniz.</p><textarea class="mhatm" rows="6">${e(r.metin)}</textarea>
      <div class="mkarar"><button type="button" class="sbtn blue" data-k="kopyala">Kopyala</button><button type="button" class="sbtn" data-k="mail" title="${r.eposta ? e(r.eposta) : 'Alıcı adresi bulunamadı; taslakta siz yazarsınız'}">Mail’de taslak aç</button></div>`;
    p.onclick = async ev => { const k = ev.target.dataset?.k; const m = $q('.mhatm', p).value;
      if (ev.target === p || k === 'kapat') p.close();
      if (k === 'kopyala'){ try{ await navigator.clipboard.writeText(m); bildir('Kopyalandı'); }catch(_){ bildir('Kopyalanamadı'); } }
      if (k === 'mail'){ try{ await j('/api/meet/hatirlat/taslak', {metin: m, eposta: r.eposta, konu: r.konu}); bildir('Mail’de taslak açıldı'); p.close(); }catch(x){ bildir(x.message); } } };
    p.showModal();
  }
  // tek gözlemci, kare başına bir kez: başlık düğmesi, toplantı sayfası, hatırlat düğmeleri
  let bekliyor = false;
  new MutationObserver(() => { if (bekliyor) return; bekliyor = true; requestAnimationFrame(() => { bekliyor = false;
    const dene = (ad, f) => { try{ const r = f(); if (r && r.catch) r.catch(x => console.warn('meet_ek ' + ad, x)); }catch(x){ console.warn('meet_ek ' + ad, x); } };   // biri bozulursa ötekiler çalışsın
    if (!MISAFIR && ($q('#tBekBtn') && !$q('#meetDurumBtn') || $q('#tDurumSat') && !$q('#tDurumSat .mdlink'))) dene('düğme', dugmeCiz);
    if ($q('#tKunye')) dene('sayfa', sayfaKur);
    if (!MISAFIR) dene('hatırlat', hatirlatEkle); }); }).observe(document.body, {childList: true, subtree: true});

  /* ---------------------------------------------------------------- 4) Ayarlar → Davetler (Meet): kapalı grup, kişi başı Studio / Meet izni, kişi sınırı
     Davet listesi Studio ile ortak (sunucu/22_misafir.py + 23_misafir_meet.py). Davetli yalnız kendi toplantılarını görür; Drive, Asana, e-posta,
     takvim, tanınan sesler, müşteri listesi ve önceki toplantılarınız ona kapalı. */
  async function davetCiz(){
    const kutu = $q('#aySistem'); if (!kutu || MISAFIR) return;
    let d; try{ d = await j('/api/davetler'); }catch(_){ return; }
    let g = $q('#mtDavet'); if (!g){ g = document.createElement('div'); g.id = 'mtDavet'; const bas = kutu.previousElementSibling?.matches?.('h4, .ayh') ? kutu.previousElementSibling : kutu; bas.before(g); }
    const zaman = t => t ? new Date(t * 1000).toLocaleString(((window.DIL || {}).locale || 'tr-TR'), {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : 'henüz girmedi';
    const satir = (et, ic, act = '') => `<div class="row"><div class="l">${et}<small>${ic}</small></div>${act ? `<div class="mdv-act">${act}</div>` : ''}</div>`;
    const aktif = d.kisiler.filter(k => k.aktif).length, S = d.sinir || {};
    const urun = (k, u, ad) => `<button type="button" class="mdv-u" data-uk="${e(k.id)}" data-u="${u}" aria-pressed="${(k.urunler || ['studio']).includes(u)}">${ad}</button>`;
    g.innerHTML = `<h4 class="ayh">Davetler</h4>`
      + satir('Davet linkleri', d.tunel ? 'Açık. Her davetli yalnızca kendi toplantılarını görür; sizin verinize erişemez. Mac yeniden başlarsa linkler değişir; buradan yeniden kopyalayın.'
        : 'Kapalı. Yukarıdaki “Dışarıdan erişim”i açınca davet linkleri de çalışır.')
      + satir('Kişi sınırı', `${aktif} / ${S.kisi} kişi`, `<button class="sbtn" type="button" data-sn="-1" aria-label="Azalt">−</button><b class="mdv-n">${S.kisi}</b><button class="sbtn" type="button" data-sn="1" aria-label="Artır">+</button>`)
      + d.kisiler.map(k => satir(`${e(k.ad)}${k.aktif ? '' : ' <span class="mdv-dur">· durduruldu</span>'}`,
          `Bugün ${k.bugun}/${S.gunluk} kayıt · son giriş ${zaman(k.son_giris)}${k.anahtar ? ' · kendi Claude anahtarıyla' : ''}`,
          `${urun(k, 'meet', 'Meet')}${urun(k, 'studio', 'Studio')}${k.meet_link ? `<button class="sbtn" type="button" data-mk="${e(k.id)}">Meet linkini kopyala</button>` : (k.link ? `<button class="sbtn" type="button" data-sk="${e(k.id)}">Linki kopyala</button>` : '')}<button class="sbtn plain" type="button" data-dm="${e(k.id)}" aria-haspopup="menu">Diğer ▾</button>`)).join('')
      + (aktif < S.kisi ? satir('Yeni davet', `Kişi başı günde ${S.gunluk} kayıt, en çok ${Math.round((S.meet_en_uzun_sn || 7200) / 60)} dakika.`,
          '<input class="sel" id="mdvAd" placeholder="Adı" style="width:140px"><button class="sbtn blue" type="button" id="mdvEkle">Davet et</button>')
        : satir('Yeni davet', 'Sınır doldu; sınırı artırın ya da birini kaldırın.'));
    const post = (u, b) => j(u, b || {});
    $$q('[data-sn]', g).forEach(b => b.onclick = async () => { try{ await post('/api/davetler/sinir', {kisi: S.kisi + +b.dataset.sn}); davetCiz(); }catch(x){ bildir(x.message); } });
    const ekle = async () => { const ad = $q('#mdvAd', g).value.trim(); if (!ad) return;
      try{ const r = await post('/api/davetler/meet', {ad}); if (r.kisi?.meet_link) kopyala(r.kisi.meet_link, `${ad} için Meet linki kopyalandı; ona gönderin`); else bildir(`${ad} eklendi; davet linklerini açınca link oluşur`); davetCiz(); }catch(x){ bildir(x.message); } };
    $q('#mdvEkle', g)?.addEventListener('click', ekle); $q('#mdvAd', g)?.addEventListener('keydown', ev => { if (ev.key === 'Enter') ekle(); });
    $$q('[data-uk]', g).forEach(b => b.onclick = async () => { const k = d.kisiler.find(x => x.id === b.dataset.uk), u = new Set(k.urunler || ['studio']);
      u.has(b.dataset.u) ? u.delete(b.dataset.u) : u.add(b.dataset.u);
      try{ await post(`/api/davetler/${k.id}/urunler`, {meet: u.has('meet'), studio: u.has('studio')}); bildir(`${k.ad}: ${[...u].map(x => x === 'meet' ? 'Meet' : 'Studio').join(' ve ')} açık`); }catch(x){ bildir(x.message); } davetCiz(); });
    $$q('[data-mk]', g).forEach(b => b.onclick = () => { const k = d.kisiler.find(x => x.id === b.dataset.mk); kopyala(k.meet_link, `${k.ad} için Meet linki kopyalandı`); });
    $$q('[data-sk]', g).forEach(b => b.onclick = () => { const k = d.kisiler.find(x => x.id === b.dataset.sk); kopyala(k.link, `${k.ad} için link kopyalandı`); });
    $$q('[data-dm]', g).forEach(b => b.onclick = ev => { const k = d.kisiler.find(x => x.id === b.dataset.dm);
      popover(ev.currentTarget, [
        [k.aktif ? 'Durdur (link çalışmaz, kayıtları kalır)' : 'Yeniden aç', async () => { try{ await post(`/api/davetler/${k.id}`, {aktif: !k.aktif}); davetCiz(); }catch(x){ bildir(x.message); } }],
        ['Yeni link oluştur (eskisi çalışmaz)', async () => { await post(`/api/davetler/${k.id}`, {yenile: true}); bildir('Yeni link hazır; eskisi artık açılmaz'); davetCiz(); }],
        null, ['Kaldır', () => sheet(`${k.ad} kaldırılsın mı?`, 'Linki kalıcı olarak çalışmaz. Kayıtları bu Mac’te kalır ama hiçbir listede görünmez.', 'Kaldır', async () => { await fetch(`/api/davetler/${k.id}`, {method: 'DELETE'}); davetCiz(); })]]); });
  }
  /* ---------------------------------------------------------------- 5) Ayarlar → Telefonum (dışarıdan Meet): tek kullanımlık QR ile eşleştirme
     Davet linklerinin tüneli kullanılır; yalnız eşleştirilmiş telefon sahip olarak girer (sunucu/24_sahip_uzak.py). */
  async function telefonCiz(){
    const kutu = $q('#aySistem'); if (!kutu || MISAFIR || UZAK) return;
    let d; try{ d = await j('/api/sahip-cihaz'); }catch(_){ return; }
    let g = $q('#mtTelefon'); if (!g){ g = document.createElement('div'); g.id = 'mtTelefon'; const bas = kutu.previousElementSibling?.matches?.('h4, .ayh') ? kutu.previousElementSibling : kutu; ($q('#mtDavet') || bas).before(g); }
    const zaman = t => t ? new Date(t * 1000).toLocaleString(((window.DIL || {}).locale || 'tr-TR'), {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '';
    const satir = (et, ic, act = '') => `<div class="row"><div class="l">${et}<small>${ic}</small></div>${act ? `<div class="mdv-act">${act}</div>` : ''}</div>`;
    const tog = (id, on) => `<button class="tog" type="button" role="switch" id="${id}" aria-checked="${!!on}"></button>`;
    g.innerHTML = `<h4 class="ayh">Telefonum</h4>`
      + satir('Dışarıdan erişim', d.tunel ? 'Açık. Eşleştirdiğiniz telefon her yerden girer; adresi bilen başkası giremez. Davet linkleri de bununla çalışır.'
          : 'Kapalı. Açınca telefonunuzu bir kez eşleştirir, sonra her yerden girersiniz.', tog('mtfTunel', d.tunel))
      + (d.tunel ? satir('Telefonu eşleştir', 'QR’ı telefonun kamerasıyla okutun. Uygulama gibi kullanmak için: Paylaş → Ana Ekrana Ekle.',
          '<button class="sbtn blue" type="button" id="mtfEsles">QR göster</button>') + '<div id="mtfQR"></div>' : '')
      + d.cihazlar.map(x => satir(e(x.ad), `Eşleştirildi ${zaman(x.olusturma)} · son giriş ${zaman(x.son_giris)}`, `<button class="sbtn plain" type="button" data-cs="${e(x.id)}">Kaldır</button>`)).join('')
      + satir('Adres değişince e-postama gönder', `Mac yeniden başlarsa yeni giriş linki ${d.alici ? e(d.alici) + ' adresine' : 'e-postanıza'} gelir.`, tog('mtfEposta', d.eposta))
      + satir('Prizdeyken Mac uyumasın', 'Mac uyursa dışarıdan girilemez. Kapak kapalıyken yine uyur.', tog('mtfUyanik', d.uyanik));
    const post = (u, b) => j(u, b || {});
    $q('#mtfTunel', g).onclick = async ev => { const ac = ev.currentTarget.getAttribute('aria-checked') !== 'true'; ev.currentTarget.setAttribute('aria-checked', ac);
      try{ await post('/api/davetler/tunel', {ac}); bildir(ac ? 'Dış bağlantı açık' : 'Dış bağlantı kapalı'); }catch(x){ bildir(x.message); } telefonCiz(); davetCiz(); };
    $q('#mtfEsles', g)?.addEventListener('click', async () => { try{ const r = await post('/api/sahip-cihaz/esles', {ad: 'Telefon'});
        $q('#mtfQR', g).innerHTML = `<div class="mtf-qr">${r.qr}<p>Tek kullanımlık; ${new Date(r.bitis * 1000).toLocaleTimeString(((window.DIL || {}).locale || 'tr-TR'), {hour: '2-digit', minute: '2-digit'})}’e kadar geçerli.</p><button class="tiny" type="button" id="mtfKopya">Linki kopyala</button></div>`;
        $q('#mtfKopya', g).onclick = () => kopyala(r.link, 'Link kopyalandı; yalnız kendinize gönderin'); }catch(x){ bildir(x.message); } });
    $$q('[data-cs]', g).forEach(b => b.onclick = () => sheet('Bu telefon kaldırılsın mı?', 'Bu telefon artık dışarıdan Meet’e giremez. Yeniden eşleştirebilirsiniz.', 'Kaldır', async () => { await fetch('/api/sahip-cihaz/' + b.dataset.cs, {method: 'DELETE'}); telefonCiz(); }));
    $q('#mtfEposta', g).onclick = async ev => { const v = ev.currentTarget.getAttribute('aria-checked') !== 'true'; ev.currentTarget.setAttribute('aria-checked', v); await post('/api/sahip-cihaz/ayar', {eposta: v}); };
    $q('#mtfUyanik', g).onclick = async ev => { const v = ev.currentTarget.getAttribute('aria-checked') !== 'true'; ev.currentTarget.setAttribute('aria-checked', v);
      try{ const r = await post('/api/sahip-cihaz/ayar', {uyanik: v}); bildir(r.uyanik ? 'Prizdeyken Mac uyumayacak' : 'Mac her zamanki gibi uyur'); }catch(x){ bildir(x.message); ev.currentTarget.setAttribute('aria-checked', !v); } };
  }
  // 2026-10-29 sadeleştirme: Meet durumu ana sayfada yalnız sorun varken; her zaman buradan açılır
  function durumSatiri(){
    const kutu = $q('#aySistem'); if (!kutu || MISAFIR || $q('#mtDurum')) return;
    const g = document.createElement('div'); g.id = 'mtDurum';
    g.innerHTML = `<div class="row"><div class="l">Meet durumu ve gelişmiş ayarlar<small>Kayıt, uzantı ve takvim durumu; Meet’in kendiliğinden yaptıkları, öneriler, ekran kareleri</small></div><button class="sbtn" type="button">Aç</button></div>`;
    $q('button', g).onclick = ac;
    const bas = kutu.previousElementSibling?.matches?.('h4, .ayh') ? kutu.previousElementSibling : kutu; bas.before(g);
  }
  if (!MISAFIR && !UZAK && typeof sistemCiz === 'function'){ const _s = sistemCiz; sistemCiz = async function(){ const r = await _s(); try{ durumSatiri(); await davetCiz(); await telefonCiz(); }catch(x){ console.warn('Meet ayarları:', x); } return r; }; }   // eslint-disable-line no-global-assign

  /* ---------------------------------------------------------------- 6) Gelişiminiz (2026-10-27): ana sayfada haftalık konuşma payı + danışman
     notlarında tekrar eden dersler (/api/meet/gelisimim). Şirket ve kişi sayfalarında gösterilmez. */
  const ILER = {suruyor: 'sürüyor', azaliyor: 'azalıyor', yeni: 'yeni'};
  let gelSon = '', gelZ = null;
  const ayKisa = s => new Date(s + 'T12:00').toLocaleDateString(((window.DIL || {}).locale || 'tr-TR'), {day: 'numeric', month: 'short'});
  function gelGrafik(H){
    const W = 300, Hh = 112, ust = 16, alt = 18, ust_s = Math.max(30, ...H.map(h => Math.max(h.pay, h.beklenen))) * 1.15;
    const bw = Math.min(34, (W - 8) / H.length - 10), adim = (W - 8) / H.length;
    const y = v => ust + (Hh - ust - alt) * (1 - v / ust_s);
    return `<svg class="mgel-g" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Haftalık konuşma payı">` + H.map((h, i) => {
      const x = 4 + i * adim + (adim - bw) / 2, son = i === H.length - 1;
      const ipucu = `${ayKisa(h.bas)} haftası · %${h.pay} (eşit pay %${h.beklenen}) · ${h.toplanti} toplantı, ${h.dk} dk\n` + h.liste.map(t => `%${t.pay} · ${t.baslik}`).join('\n');
      return `<g><title>${e(ipucu)}</title><rect x="${x}" y="${y(h.pay)}" width="${bw}" height="${Math.max(2, y(0) - y(h.pay))}" rx="4" class="${son ? 'son' : ''}"/>`
        + `<line x1="${x - 3}" x2="${x + bw + 3}" y1="${y(h.beklenen)}" y2="${y(h.beklenen)}" class="bek"/>`
        + `<text x="${x + bw / 2}" y="${y(Math.max(h.pay, h.beklenen)) - 5}" class="d">%${h.pay}</text><text x="${x + bw / 2}" y="${Hh - 4}" class="t">${e(ayKisa(h.bas))}</text></g>`;
    }).join('') + '</svg>';
  }
  // Yeri: müşteri takibinin üstü (takip_ek.js kartını haftalık özetin hemen arkasına sonradan ekler; her çizimde yer yeniden kurulur)
  // 2026-10-29 sadeleştirme: toplantı listesinin altında (önce toplantılar)
  const gelYer = k => { const z = $q('#tizgara'); if (z && z.nextElementSibling !== k) z.after(k); };
  async function gelisimCiz(){
    if (MISAFIR) return;
    let k = $q('#tGelisim');
    const ana = !(typeof tSirket !== 'undefined' && tSirket) && !(typeof tKisi !== 'undefined' && tKisi);
    if (!ana){ k?.remove(); gelSon = ''; return; }
    let d; try{ d = await j('/api/meet/gelisimim'); }catch(_){ return; }
    const H = d.haftalar || [], T = d.temalar || [];
    if (!H.length && !T.length){ k?.remove(); return; }
    const imza = JSON.stringify([H, T, d.hazirlaniyor]); if (imza === gelSon && k){ gelYer(k); return; } gelSon = imza;
    if (!k){ k = document.createElement('section'); k.id = 'tGelisim'; k.className = 'mgel'; }
    gelYer(k);
    const tema = t => `<li><button type="button" class="mgel-t" aria-expanded="false"><b>${e(t.tema)}</b><small>${t.kaynaklar.length} toplantıda · ${e(ILER[t.ilerleme] || '')}</small></button>
      <p>${e(t.aciklama)}</p><ul class="mgel-k">${t.kaynaklar.map(x => `<li><a href="#t=${encodeURIComponent(x.temel)}">${e(ayKisa(x.tarih))} · ${e(x.ders.split(':')[0])}</a></li>`).join('')}</ul></li>`;
    k.innerHTML = `<div class="mgel-bas"><h2>Gelişiminiz</h2><small>${H.length ? `Son ${H.length} hafta` : ''}</small></div>
      <div class="mgel-ic">
        <div class="mgel-pay"><h5>Konuşma payınız</h5>${H.length ? gelGrafik(H) + `<p>${e(d.cumle)}</p><p class="mgel-not">Çizgi, toplantıdaki kişi sayısına göre eşit pay. Yalnız adınızla tanındığınız toplantılar sayılır.</p>`
          : '<p class="mgel-not">Adınızla tanındığınız toplantı olunca burada görünür.</p>'}</div>
        <div class="mgel-ders"><h5>Tekrar eden dersler</h5>${T.length ? `<ol>${T.map(tema).join('')}</ol>`
          : `<p class="mgel-not">${d.hazirlaniyor ? 'Danışman notlarınız gözden geçiriliyor…' : 'En az iki toplantıda tekrar eden bir ders olunca burada görünür.'}</p>`}</div>
      </div>`;
    $$q('.mgel-t', k).forEach(b => b.onclick = () => { const a = b.getAttribute('aria-expanded') !== 'true'; b.setAttribute('aria-expanded', a); b.closest('li').classList.toggle('acik', a); });
    clearTimeout(gelZ); if (d.hazirlaniyor) gelZ = setTimeout(() => gelisimCiz().catch(() => {}), 15000);
  }
  if (!MISAFIR && typeof izgaraCiz === 'function'){ const _iz = izgaraCiz; izgaraCiz = async function(...a){ const r = await _iz.apply(this, a); try{ await gelisimCiz(); }catch(_){} return r; }; }   // eslint-disable-line no-global-assign
  if (!MISAFIR) setTimeout(() => gelisimCiz().catch(() => {}), 2500);   // takip kartı çizildikten sonra yeri düzelsin

  /* ---------------------------------------------------------------- 7) Ana sayfa sekmeleri (2026-10-29; kullanıcı: "simplify = özellik kısmak değil,
     deneyimi kolaylaştırmak"). Hiçbir bölüm kaldırılmaz; ana sayfa üç sekmeye ayrılır: Toplantılar (sor kutusu, onay bekleyenler, Ghost satırı,
     toplantılar) · Müşteri takibi (takip_ek.js: müşteri notları + sektör haberleri) · Gelişiminiz. Sekme yalnız içeriği varken görünür; seçim hatırlanır. */
  const SEKME = [['toplanti', 'Toplantılar', ['#musteriOneri', '#tfilt', '#tSor', '#tGhost', '#tOnay', '#tizgara', '#tliste']],
                 ['musteri', 'Müşteri takibi', ['#takipKutu']], ['gelisim', 'Gelişiminiz', ['#tGelisim']]];
  let anaSek = (() => { try{ return sessionStorage.getItem('meetAnaSek') || 'toplanti'; }catch(_){ return 'toplanti'; } })();
  function sekmeCiz(){
    const sec = $q('#toplantiSec'); if (!sec || MISAFIR) return;
    const dolu = {toplanti: true, musteri: !!$q('#takipKutu')?.textContent.trim(), gelisim: !!$q('#tGelisim')};
    const gorunen = SEKME.filter(([k]) => dolu[k]);
    let bar = $q('#mAnaSek');
    if (gorunen.length < 2){ bar?.remove(); sec.removeAttribute('data-msek'); return; }
    if (!dolu[anaSek]) anaSek = 'toplanti';
    if (!bar){ bar = document.createElement('div'); bar.id = 'mAnaSek'; bar.className = 'manasek'; bar.setAttribute('role', 'tablist');
      bar.onclick = ev => { const b = ev.target.closest('button[data-k]'); if (!b) return; anaSek = b.dataset.k; try{ sessionStorage.setItem('meetAnaSek', anaSek); }catch(_){} sekmeCiz(); }; }
    const yer = $q('#haftalikKutu') || $q('#takipKutu') || $q('#tSor'); if (yer && bar.nextElementSibling !== yer) yer.before(bar);
    const say = {musteri: $$q('#takipKutu .tk-kart').length};
    const h = gorunen.map(([k, ad]) => `<button type="button" role="tab" data-k="${k}" aria-selected="${k === anaSek}">${ad}${say[k] ? `<span>${say[k]}</span>` : ''}</button>`).join('');
    if (bar.innerHTML !== h) bar.innerHTML = h;
    if (sec.dataset.msek !== anaSek) sec.dataset.msek = anaSek;
    SEKME.forEach(([k, , sec_]) => sec_.forEach(sel => { const el = $q(sel); if (el) el.toggleAttribute('data-msek-gizli', k !== anaSek); }));
  }
  if (!MISAFIR){ let zs = null; const sec = $q('#toplantiSec');
    if (sec) new MutationObserver(() => { clearTimeout(zs); zs = setTimeout(sekmeCiz, 150); }).observe(sec, {childList: true, subtree: true}); setTimeout(sekmeCiz, 1500); }
  /* ---------------------------------------------------------------- 8) Ayarlar sekmeleri (2026-10-29; aynı ilke: hiçbir ayar kalkmaz). Meet'te ayarlar
     tek uzun liste yerine altı sekmede: Genel (siz, dil, yapay zekâ) · Kayıt (kayıt nasıl başlar, takvim, sesler) · Notlar (toplantıdan sonra ne olur,
     nereye gider: Drive, Asana) · Müşteriler · Paylaşım (ağ, telefon, davetler) · Sistem. Satırlar yerinden taşınır; kimlikler değişmez. */
  const AYAR = [
    ['genel', 'Genel', [['Siz', ['#ayAdim', '#ayEpostalar', '#ayDil']], ['Yapay zekâ', ['#ayClaudeAct', '#ayClaudeKullanim', '#ayClaudeTop', '#ayOzet', '#ayOzetDili']]]],
    ['kayit', 'Kayıt', [['', ['#ayOto', '#ayKapi', '#ayAsistan', '#ayTelefon']], ['Kim, ne zaman', ['#ayTakvimAct', '#aySesler']]]],
    ['notlar', 'Notlar', [['Toplantıdan sonra', ['#ayNotlar', '#ayDanisman', '#ayGorev', '#ayOnBrif', '#ayOnBrifEp', '#ayHaftalik']],
                          ['Notlar nereye gider', ['#ayDriveAct', '#ayDriveKlasor', '#ayAsanaNot']]]],
    ['musteri', 'Müşteriler', [['', ['#ayMusteriler', '#ayUcret']]]],
    ['paylasim', 'Paylaşım', [['Bu ağdaki cihazlar', ['#ayAg', '#ayTelefonKopyala', '#ayPinAct', '#ayAdres']]]],
    ['sistem', 'Sistem', [['', ['#aySistem']]]]];
  let aySek = (() => { try{ return sessionStorage.getItem('meetAySek') || 'genel'; }catch(_){ return 'genel'; } })();
  function aySec(k){ const dlg = $q('#ayarlar'); if (!dlg) return; aySek = k; try{ sessionStorage.setItem('meetAySek', k); }catch(_){}
    $$q('#mAySek button', dlg).forEach(b => b.setAttribute('aria-selected', b.dataset.k === k));
    $$q('.maypane', dlg).forEach(p => p.hidden = p.dataset.ay !== k); }
  function ayKur(){
    const dlg = $q('#ayarlar'); if (!dlg || MISAFIR) return;
    if (!$q('#mAySek', dlg)){
      const bar = document.createElement('div'); bar.id = 'mAySek'; bar.className = 'manasek maysek'; bar.setAttribute('role', 'tablist');
      bar.innerHTML = AYAR.map(([k, ad]) => `<button type="button" role="tab" data-k="${k}">${ad}</button>`).join('');
      bar.onclick = ev => { const b = ev.target.closest('button[data-k]'); if (b) aySec(b.dataset.k); };
      const panes = AYAR.map(([k]) => { const p = document.createElement('div'); p.className = 'maypane'; p.dataset.ay = k; return p; });
      $$q(':scope > h4.ayh', dlg).forEach(h => h.classList.add('mayGizli'));       // eski grup başlıklarının yerini sekmeler alır
      const ilk = dlg.firstElementChild; ilk.after(bar); bar.after(...panes);
      AYAR.forEach(([, , gruplar], i) => gruplar.forEach(([bas, secler]) => {
        if (bas){ const h = document.createElement('h4'); h.className = 'ayh mayalt'; h.textContent = bas; panes[i].append(h); }
        secler.forEach(sel => { const el = $q(sel, dlg); const sat = el && (el.id === 'aySistem' ? el : el.closest('.row')); if (sat) panes[i].append(sat); }); }));
      dlg.addEventListener('focusin', ev => { const p = ev.target.closest?.('.maypane'); if (p && p.hidden) aySec(p.dataset.ay); });
    }
    // Davetler, Telefonum (Paylaşım) ve Meet durumu (Sistem) sonradan çizilir; yerlerine alınır
    const pay = $q('.maypane[data-ay="paylasim"]', dlg), sis = $q('.maypane[data-ay="sistem"]', dlg);
    ['#mtTelefon', '#mtDavet'].forEach(sel => { const g = $q(sel, dlg); if (g && g.parentElement !== pay) pay.append(g); });
    const d = $q('#mtDurum', dlg); if (d && sis.firstElementChild !== d) sis.prepend(d);
    const kay = $q('.maypane[data-ay="kayit"]', dlg);
    if (kay && !$q('#ayKayitDisi', dlg)){ const r = document.createElement('div'); r.className = 'row mkd'; r.id = 'ayKayitDisi'; kay.append(r); }
    kayitDisiCiz();
    aySec(aySek);
  }
  /* Kaydedilmeyen toplantılar (2026-10-29; kullanıcı: "kurs meetlerini kaydetmeye gerek yok, her hafta tekrar ediyor"). Liste kendiliğinden de
     büyür: "toplantıya benzemiyor" kartında Kaldır ya da aynı adlı kaydın iki ayrı günde toplantı olmaması. */
  async function kayitDisiCiz(){
    const r = $q('#ayKayitDisi'); if (!r) return;
    let L = []; try{ L = (await j('/api/kayit-disi')).liste || []; }catch(_){ return; }
    r.innerHTML = `<div class="l">Kaydedilmeyen toplantılar<small>Her hafta tekrar eden, toplantı olmayan görüşmeler (kurs, ders gibi). Adı bunlara uyan görüşmeler kaydedilmez.</small>
        ${L.length ? `<ul class="mkd-l">${L.map((x, i) => `<li><span><b>${e(x.ad)}</b>${x.otomatik ? '<small>kendiliğinden eklendi</small>' : ''}</span><button type="button" class="tiny" data-kd="${i}">Kaldır</button></li>`).join('')}</ul>` : ''}
        <span class="mkd-ekle"><input type="text" maxlength="60" placeholder="Toplantı adı, ör. Almanca kursu" aria-label="Kaydedilmeyecek toplantının adı"><button type="button" class="sbtn" data-kd="ekle">Ekle</button></span></div>`;
    r.onclick = async ev => { const b = ev.target.closest('[data-kd]'); if (!b) return;
      if (b.dataset.kd === 'ekle'){ const ad = $q('.mkd-ekle input', r).value.trim(); if (ad.length < 3) return; await j('/api/kayit-disi', {ekle: ad}); }
      else await j('/api/kayit-disi', {sil: +b.dataset.kd});
      kayitDisiCiz(); };
    $q('.mkd-ekle input', r).onkeydown = ev => { if (ev.key === 'Enter'){ ev.preventDefault(); $q('[data-kd="ekle"]', r).click(); } };
  }
  if (!MISAFIR && typeof ayarlarAc === 'function'){ const _a = ayarlarAc; ayarlarAc = async function(...x){ ayKur(); const r = await _a(...x); ayKur(); return r; }; }   // eslint-disable-line no-global-assign
  if (!MISAFIR && typeof sistemCiz === 'function'){ const _s2 = sistemCiz; sistemCiz = async function(...x){ const r = await _s2(...x); try{ ayKur(); }catch(_){} return r; }; }   // eslint-disable-line no-global-assign
  /* ---------------------------------------------------------------- 9) Başlarken (2026-10-29): yeni kullanıcıya ana sayfada kısa kurulum listesi.
     Otomatik kayıt, Chrome uzantısı, adınız, takvim (isteğe bağlı), ilk toplantı. Hepsi hazırsa görünmez; "Sonra" 7 gün gizler. Hiçbir şeyi kendisi
     değiştirmez: her adımın düğmesi ilgili ayarı açar. Denemek için: localStorage meetBaslarkenGoster = 1. */
  async function baslarkenCiz(){
    const sec = $q('#toplantiSec'); if (!sec || MISAFIR || UZAK) return;
    if (!$q('#tpGeri')?.classList.contains('hidden')) { $q('#mBaslarken')?.remove(); return; }       // şirket/kişi sayfası değil, ana sayfa
    let zorla = false, ertele = 0; try{ zorla = localStorage.getItem('meetBaslarkenGoster') === '1'; ertele = +localStorage.getItem('meetBaslarken') || 0; }catch(_){}
    if (!zorla && ertele > Date.now()) return;
    let d = {}, a = {}, L = [];
    try{ [d, a, L] = await Promise.all([j('/api/meet/durum'), j('/api/ayarlar'), j('/api/gecmis')]); }catch(_){ return; }
    const S = Object.fromEntries((d.saglik || []).map(x => [x.kod, x]));
    const toplanti = (Array.isArray(L) ? L : []).filter(x => x.toplanti).length;
    const adim = [
      {k: 'kayit', tamam: S.kaydedici?.durum === 'ok', ad: 'Otomatik kayıt', acik: S.kaydedici?.durum === 'ok' ? 'Toplantıya girince kayıt kendiliğinden başlar. Kaydettiğinizi toplantıdakilere söyleyin.' : (S.kaydedici?.metin || 'Toplantılar kendiliğinden kaydedilmez.'), dugme: 'Aç', ac: () => ayarGit('kayit', '#ayOto')},
      {k: 'uzanti', tamam: !!S.uzanti && S.uzanti.durum !== 'hata' && !/ses vermiyor|yok/.test(S.uzanti.metin || ''), ad: 'Chrome uzantısı', acik: 'Toplantıdaki kişilerin adları, canlı öneriler ve not alma için.', dugme: 'Nasıl?', ac: () => bildir(S.uzanti?.cozum || 'Chrome’da chrome://extensions sayfasını açın, Geliştirici modunu açın, “Paketlenmemiş öğe yükle” ile Meet klasöründeki uzanti klasörünü seçin.')},
      {k: 'ad', tamam: !!(a.benim_adim || '').trim(), ad: 'Adınız', acik: 'Notlarda size düşen işler ayrı görünür; sesiniz tanınır.', dugme: 'Yaz', ac: () => ayarGit('genel', '#ayAdim')},
      {k: 'takvim', tamam: S.takvim?.durum === 'ok', ad: 'Takvim', istege: true, acik: 'İsteğe bağlı. Toplantı adı ve önceki görüşmelerden hazırlık notu gelir.', dugme: 'Bağla', ac: () => ayarGit('kayit', '#ayTakvimAct')},
      {k: 'ilk', tamam: toplanti > 0, ad: 'İlk toplantınız', acik: 'Google Meet, Zoom ya da Teams’te bir görüşmeye girin; bitince notlar burada açılır.', dugme: '', ac: null}];
    const gerekli = adim.filter(x => !x.istege), hazir = adim.filter(x => x.tamam).length;
    if (!zorla && gerekli.every(x => x.tamam)){ $q('#mBaslarken')?.remove(); return; }
    let g = $q('#mBaslarken'); if (!g){ g = document.createElement('div'); g.id = 'mBaslarken'; g.className = 'mbz'; ($q('#tdurum') || $q('#tVurgu')).after(g); }
    g.innerHTML = `<div class="mbz-bas"><div><b>Başlarken</b><span>${hazir} / ${adim.length} hazır</span></div><button type="button" class="tiny" data-mb="sonra">Sonra</button></div>`
      + adim.map((x, i) => `<div class="mbz-s${x.tamam ? ' tamam' : ''}"><span class="mbz-i" aria-hidden="true">${x.tamam ? '✓' : i + 1}</span>
          <div class="mbz-m"><b>${e(x.ad)}</b><small>${e(x.acik)}</small></div>${!x.tamam && x.dugme ? `<button type="button" class="sbtn" data-mb="${x.k}">${e(x.dugme)}</button>` : ''}</div>`).join('');
    g.onclick = ev => { const b = ev.target.closest('[data-mb]'); if (!b) return;
      if (b.dataset.mb === 'sonra'){ try{ localStorage.setItem('meetBaslarken', String(Date.now() + 7 * 86400e3)); localStorage.removeItem('meetBaslarkenGoster'); }catch(_){} g.remove(); return; }
      adim.find(x => x.k === b.dataset.mb)?.ac?.(); };
  }
  async function ayarGit(sekme, sec){
    await ayarlarAc(); aySec(sekme);
    const el = $q(sec); if (el){ el.closest('.row')?.scrollIntoView({block: 'center'}); if (el.matches('input,textarea')) el.focus(); }
  }
  if (!MISAFIR && !UZAK){ setTimeout(baslarkenCiz, 1200);
    $q('#ayarlar')?.addEventListener('close', () => setTimeout(baslarkenCiz, 600)); }
})();

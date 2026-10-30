// content.js - Toplantı sayfasını izler: aramada mıyız, katılımcılar kim, şu an kim konuşuyor.
// 3.11: altyazı metnini konuşmacı ve zamanla toplar (Google Meet notları gibi). Sesi KAYDETMEZ; kaydı background.js (sekme sesi + mikrofon) yapar. Burası yalnızca sinyal üretir.
(() => {
  const host = location.hostname;
  const platform = host.includes('meet.google') ? 'meet' : host.includes('teams') ? 'teams' : host.includes('zoom') ? 'zoom' : 'web';
  const isimler = new Map();            // ad -> son görülme (ms)
  let aramada = false, kayitId = null, kayitBas = 0, sonKonusan = '', sonOlay = 0, olaylar = [];
  let zamanlayici = null, olu = false;
  // Uzantı yenilenince (chrome://extensions → yenile) bu sayfadaki eski betik geçersiz kalır ("Extension context invalidated");
  // hata üretmek yerine sessizce durur; sayfa yenilenince yeni betik devreye girer.
  function gonder(msg, cb){
    if (olu) return;
    try{
      if (!chrome.runtime?.id) throw new Error('context invalidated');
      const p = chrome.runtime.sendMessage(msg, cb ? cb : undefined);   // 16-20 Ekim: burada kendini çağırıyordu, uzantı ilk sinyalde susuyordu
      if (p && p.catch) p.catch(() => {});
    }catch(e){ olu = true; if (zamanlayici) clearInterval(zamanlayici); try{ gozlemci.disconnect(); }catch(_){} }
  }

  // Meet/Teams arayüz yazıları kişi adı değil (2026-10-24: "Zoom in", "Open in new window", "Enter Full Screen" katılımcı sanıldı); kisiler.py ARAYUZ ile aynı liste
  const ARAYUZ = /\b(sesini|kadraj|arka plan|efekt|sustur|kamera|mikrofon|katılımcı|sunum|ekran|paylaş|toplantı|görüşme|ayarlar|yakınlaştır|uzaklaştır|tam ekran|pencere|mute|unmute|camera|participants?|backgrounds?|effects?|reframe|present\w*|meeting|you|siz|sen|zoom|window|screen|full|open|close|pin|unpin|captions?|chat|more options|settings|leave|raise|hand|layout|tile|spotlight|host|remove|enter|exit|minimi[sz]e|maximi[sz]e|picture)\b/i;
  const temizAd = s => (s || '').replace(/\s+/g, ' ').replace(/\s*\((siz|you|sen)\)\s*$/i, '').trim();
  const adGibi = s => s && s.length >= 2 && s.length <= 40 && !/\d{3,}|http|:|\n/.test(s) && /^[\p{L}][\p{L}\s.'\-]*$/u.test(s);

  // Yalnızca GERÇEK arama ekranı (2026-10-20): eskiden herhangi bir "Leave/Ayrıl" düğmesi yetiyordu; Teams'in SOHBET sayfasında da "Leave" düğmeleri
  // olduğu için "(1) IK 18 | Microsoft Teams" sohbeti arama sanıldı ve YouTube/maç sesi toplantı diye kaydedildi.
  const gorunur = el => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0);
  const bul = q => [...document.querySelectorAll(q)].some(gorunur);
  let aramaIsaret = '';
  const meetKodu = () => /^\/[a-z]{3}-[a-z]{4}-[a-z]{3}/.test(location.pathname);
  function aramadaMi(){
    aramaIsaret = '';
    if (platform === 'meet'){
      if (!meetKodu()) return false;
      aramaIsaret = 'ayril'; if (bul('button[aria-label="Leave call" i], button[aria-label^="Leave call" i], button[aria-label*="görüşmeden ayrıl" i], button[aria-label*="aramadan ayrıl" i], button[aria-label*="toplantıdan ayrıl" i], button[aria-label*="anruf verlassen" i], [jsname="CQylAd"]')) return true;
      // 3.17 (2026-10-27): 26 Ekim'den beri hiçbir toplantıda "aramada" denmedi (düğme adı değişmiş olabilir); yedek işaretler: kırmızı kapatma
      // düğmesinin simgesi ve görüşmedeki kişi kutucukları (bekleme odasında yok; aynı gün katılımcılar bunlardan okundu)
      aramaIsaret = 'call_end'; if ([...document.querySelectorAll('button i, button span')].some(x => x.textContent.trim() === 'call_end' && gorunur(x))) return true;
      aramaIsaret = 'karo'; if ([...document.querySelectorAll('[data-participant-id]')].some(gorunur)) return true;
      // 3.23 (2026-10-30): bir Meet görüşmesinde yukarıdakilerin hiçbiri tutmadı (2 katılımcı görüldü, "aramada" hiç denmedi), kayıt gecikti.
      // Son çare: toplantı kodu var, giriş ekranı (Katıl düğmesi) yok ve görüşme denetimleri (kendi karo adı, toplantı adı, mikrofon düğmesi) ekranda.
      if (beklemedeMi()){ aramaIsaret = ''; return false; }
      aramaIsaret = 'denetim';
      if (!!document.querySelector('[data-self-name], [data-meeting-title]') || bul('[data-is-muted], button[aria-label*="microphone" i], button[aria-label*="mikrofon" i]')) return true;
      aramaIsaret = ''; return false;
    }
    if (platform === 'teams'){
      const kapat = bul('#hangup-button, [data-tid="hangup-main-btn"], [data-tid="hangup-button"], [data-tid="call-hangup"], button[aria-label^="Leave (" i], button[aria-label^="Ayrıl (" i], button[aria-label^="Hang up" i], button[aria-label^="Kapat (" i]');
      const mik = bul('#microphone-button, [data-tid="toggle-mute"], [data-tid="microphone-button"], button[aria-label^="Mute" i], button[aria-label^="Unmute" i], button[aria-label*="mikrofon" i]');
      return kapat && mik;
    }
    if (platform === 'zoom') return bul('#wc-footer .footer__leave-btn, .footer__leave-btn-container button, button[aria-label="Leave meeting" i], button[aria-label="Leave" i].footer__leave-btn');
    return false;
  }

  function katilimcilariTopla(){
    const simdi = Date.now();
    const adaylar = [];
    if (platform === 'meet'){
      document.querySelectorAll('[data-self-name], [data-participant-id]').forEach(el => {
        const self = el.getAttribute('data-self-name'); if (self) adaylar.push(self);
        if (self) return;                                   // kendi karomuzda ad zaten öznitelikte; alt yazılar düğme/uyarı metni ("Reframe", "Backgrounds and effects")
        el.querySelectorAll('span, div').forEach(x => { if (x.children.length === 0 && x.textContent.trim().split(/\s+/).length <= 4) adaylar.push(x.textContent); });
      });
      document.querySelectorAll('[role="list"] [role="listitem"], [aria-label*="atılımcı" i] [role="listitem"], [aria-label*="articipant" i] [role="listitem"]').forEach(li => {
        const t = li.querySelector('span, div'); if (t) adaylar.push(t.textContent);
      });
    } else if (platform === 'teams'){
      document.querySelectorAll('[data-tid*="roster" i] [data-tid*="name" i], [data-tid="participantsInCall"] span, [data-cid="calling-participant-stream"] [data-tid="participant-name"], [class*="displayName" i]').forEach(x => adaylar.push(x.textContent));
      // 2026 Teams web: katılımcı paneli öğeleri ve altyazıdaki konuşmacı adları (Zerg00s/Live-Captions-Saver, MIT, seçicileri)
      document.querySelectorAll('[data-tid^="participantsInCall-"] [id^="roster-avatar-img-"]').forEach(x => adaylar.push(x.textContent || x.getAttribute('aria-label') || ''));
      const kap = teamsAltyaziKutusu(); if (kap) kap.querySelectorAll('[data-tid="author"]').forEach(x => adaylar.push(x.innerText || x.textContent));
    } else if (platform === 'zoom'){
      document.querySelectorAll('.participants-item__display-name, .video-avatar__avatar-name, .participants-item-position span').forEach(x => adaylar.push(x.textContent));
    }
    // Meet düğme etiketlerinden adı ayıkla ("Pin X to your main screen", "More options for X", "X kişisini sabitle"...), düğme adlarını at
    const ayikla = s => { s = (s || '').replace(/\s+/g, ' ').trim();
      let m = /^(?:Pin|Unpin) (.+?) (?:to|from) your main screen$/i.exec(s) || /^More options for (.+)$/i.exec(s) || /^(.+?) (?:kişisini|adlı kişiyi) .*$/i.exec(s) || /^(.+?) için diğer seçenekler$/i.exec(s);
      return m ? m[1] : s; };
    const dugme = /^(mute|unmute|pin|unpin|more options|remove|sessize al|sesi aç|sabitle|kaldır|you|siz|sen|host|sunucu|presenting|sunuyor)$/i;
    adaylar.map(ayikla).map(temizAd).filter(a => adGibi(a) && !dugme.test(a) && !ARAYUZ.test(a) && !/\b(to your main screen|options for|kişisini|seçenekler)\b/i.test(a)).forEach(a => isimler.set(a, simdi));
    for (const [a, t] of isimler) if (simdi - t > 10 * 60 * 1000) isimler.delete(a);
    return [...isimler.keys()];
  }

  // Teams altyazı penceresi (2026 yeni tasarım ve önceki iki sürüm); her satır .fui-ChatMessageCompact: [data-tid=author] + [data-tid=closed-caption-text].
  // Sırayla denenir: virgüllü tek seçici araç çubuğundaki "Captions" düğmesini döndürebiliyor.
  function teamsAltyaziKutusu(){
    for (const q of ['[data-tid="closed-caption-renderer-wrapper"]', '[data-tid="closed-caption-v2-window-wrapper"]', '[data-tid="closed-captions-renderer"]']){
      const el = document.querySelector(q); if (el && el.querySelector('[data-tid="closed-caption-text"]')) return el;
    }
    const gevsek = [...document.querySelectorAll('[data-tid*="closed-caption"]')].find(el => el.querySelector('[data-tid="closed-caption-text"]'));
    return gevsek || null;
  }
  let teamsSonMetin = '';
  function teamsKonusan(){
    const kap = teamsAltyaziKutusu(); if (!kap) return '';
    const satirlar = kap.querySelectorAll('.fui-ChatMessageCompact, [data-tid="closed-caption-text"]');
    for (let i = satirlar.length - 1; i >= 0; i--){
      const sat = satirlar[i].classList.contains('fui-ChatMessageCompact') ? satirlar[i] : satirlar[i].closest('.fui-ChatMessageCompact') || satirlar[i].parentElement?.parentElement;
      const ad = temizAd(sat?.querySelector('[data-tid="author"]')?.innerText || '');
      const metin = (sat?.querySelector('[data-tid="closed-caption-text"]')?.innerText || '').trim();
      if (!ad || !metin || !adGibi(ad)) continue;
      isimler.set(ad, Date.now());
      const anahtar = ad + '|' + metin.slice(-40);
      if (anahtar === teamsSonMetin) return sonKonusan === ad ? ad : '';   // altyazı ilerlemiyorsa yeni olay yok
      teamsSonMetin = anahtar; return ad;
    }
    return '';
  }

  // Meet altyazı bölgesi: [role=region][aria-label=Captions|Altyazılar]; her satır = profil resmi + ad (resmin kardeşi)
  // + metin (resmin ebeveyninin kardeşi). Sınıf adına dayanmaz; açık kaynak Meet altyazı uzantılarının kullandığı desen.
  function altyaziKonusan(){
    if (platform === 'teams') return teamsKonusan();
    if (platform !== 'meet') return '';
    const bolge = document.querySelector('[role="region"][aria-label="Captions"], [role="region"][aria-label="Altyazılar"], [role="region"][aria-label*="aption" i], [role="region"][aria-label*="ltyaz" i]');
    if (!bolge) return '';
    const resimler = bolge.querySelectorAll('img');
    for (let i = resimler.length - 1; i >= 0; i--){
      const img = resimler[i]; const src = img.getAttribute('src') || '';
      if (!/^(https?:|data:)/.test(src)) continue;
      const ad = temizAd(img.nextElementSibling?.textContent || img.parentElement?.nextElementSibling?.querySelector?.('span, div')?.textContent || '');
      if (adGibi(ad)){ isimler.set(ad, Date.now()); return ad; }
    }
    return '';
  }


  // ---- Altyazı metni (3.11, 2026-10-25; Tactiq gibi): görünen her altyazı satırı konuşmacı adı ve mutlak zamanla kaydedilir. ----
  // Meet bir konuşmacının bloğunu büyüterek yazar (eski kısmı baştan kırpabilir); Teams her söz için ayrı satır açar. Her satır öğesi bir kayıt:
  // metin durunca (son satırsa 6 sn, değilse 1,5 sn) ya da satır kaybolunca yalnız henüz gönderilmemiş kısmı gider.
  function altyaziSatirlari(){
    const out = [];
    if (platform === 'teams'){
      const kap = teamsAltyaziKutusu(); if (!kap) return out;
      kap.querySelectorAll('.fui-ChatMessageCompact').forEach(el => {
        const ad = temizAd(el.querySelector('[data-tid="author"]')?.innerText || '');
        const metin = (el.querySelector('[data-tid="closed-caption-text"]')?.innerText || '').replace(/\s+/g, ' ').trim();
        if (metin) out.push({el, ad: adGibi(ad) ? ad : '', metin});
      });
      return out;
    }
    if (platform !== 'meet') return out;
    const bolge = document.querySelector('[role="region"][aria-label="Captions"], [role="region"][aria-label="Altyazılar"], [role="region"][aria-label*="aption" i], [role="region"][aria-label*="ltyaz" i]');
    if (!bolge) return out;
    bolge.querySelectorAll('img').forEach(img => {
      if (!/^(https?:|data:)/.test(img.getAttribute('src') || '')) return;
      const el = img.parentElement?.parentElement; if (!el) return;
      const ad = temizAd(img.nextElementSibling?.textContent || img.parentElement?.nextElementSibling?.querySelector?.('span, div')?.textContent || '');
      const metinEl = img.parentElement?.nextElementSibling;
      let metin = (metinEl?.innerText || '').replace(/\s+/g, ' ').trim();
      if (ad && metin.startsWith(ad)) metin = metin.slice(ad.length).trim();
      if (metin) out.push({el, ad: adGibi(ad) ? ad : '', metin});
    });
    return out;
  }
  const altyaziKayit = new WeakMap(); let altyaziAcik = [], altyaziGiden = [], sonAltyaziTara = 0;
  function farkMetin(gonderilen, metin){
    if (!gonderilen) return metin;
    if (metin.startsWith(gonderilen)) return metin.slice(gonderilen.length);
    const kuyruk = gonderilen.slice(-30); const i = metin.lastIndexOf(kuyruk);   // Meet baştan kırptıysa son gönderilen parçadan sonrası
    return i >= 0 ? metin.slice(i + kuyruk.length) : metin;
  }
  function altyaziTara(hepsi){
    const simdi = Date.now();
    const satirlar = aramada ? altyaziSatirlari() : [];
    satirlar.forEach((s, i) => {
      let r = altyaziKayit.get(s.el);
      if (!r){ r = {ad: s.ad, metin: s.metin, gonderilen: '', ekBas: simdi, son: simdi, gor: simdi, sonSatir: false}; altyaziKayit.set(s.el, r); altyaziAcik.push(r); }
      else if (s.metin !== r.metin){
        if (!s.metin.startsWith(r.metin.slice(0, 15)) && r.metin !== r.gonderilen){        // başı değişti (Meet baştan kırptı): kırpılan baş kaybolmasın, önce gönderilir
          const ek = farkMetin(r.gonderilen, r.metin).trim();
          if (ek.length > 1) altyaziGiden.push({ts: r.ekBas / 1000, son: r.son / 1000, ad: r.ad, metin: ek.slice(0, 2000)});
          r.gonderilen = r.metin;
        }
        if (r.metin === r.gonderilen) r.ekBas = simdi;
        r.metin = s.metin; r.son = simdi;
      }
      if (s.ad) r.ad = s.ad;
      r.gor = simdi; r.sonSatir = i === satirlar.length - 1;
    });
    altyaziAcik = altyaziAcik.filter(r => {
      const kayboldu = hepsi || simdi - r.gor > 2000;
      const durgun = simdi - r.son > (r.sonSatir ? 6000 : 1500);
      if ((kayboldu || durgun) && r.metin !== r.gonderilen){
        const ek = farkMetin(r.gonderilen, r.metin).trim();
        if (ek.length > 1) altyaziGiden.push({ts: r.ekBas / 1000, son: r.son / 1000, ad: r.ad, metin: ek.slice(0, 2000)});
        r.gonderilen = r.metin;
      }
      return !kayboldu;
    });
    if (altyaziGiden.length > 400) altyaziGiden = altyaziGiden.slice(-400);
  }
  function altyaziGonder(){
    if (!altyaziGiden.length) return;
    const giden = altyaziGiden.splice(0);
    gonder({tur: 'altyazi', satirlar: giden, platform, baslik: toplantiAdi()});
  }



  // ---- Toplantı sekmesinde gösterge ve öneriler (3.12, 2026-10-27) ----
  // Kullanıcı: "toplantı kayda alınıyor mu göremiyorum, strese giriyorum" ve "toplantı sırasında öneriler gelecekti, göremiyorum".
  // Sol üstte küçük hap: ● Kaydediliyor 14:32 (kırmızı), ses kopunca turuncu uyarı, kayıt yoksa "Kayıt yok". Canlı öneriler (fısıltı kartları)
  // hapın altında belirir; yeni kart 45 sn açık kalır, sonra hapa "1 öneri" olarak iner, hapa tıklayınca son kartlar açılır. Ekran paylaşılırken
  // (Sunmayı durdur / Stop presenting düğmesi görünürken) hiçbir şey gösterilmez: paylaşılan ekranda görünmesin. Gölge DOM: sayfanın stilleri karışmaz.
  let gosterge = null, gKok = null, gAcik = false, gGizli = false, gSonKart = 0, gGorulen = 0, gVeri = null;
  const sunuyor = () => [...document.querySelectorAll('button, [role="button"]')].some(b => /stop presenting|stop sharing|sunmayı durdur|sunumu durdur|paylaşımı durdur|präsentation beenden|freigabe beenden/i.test(b.getAttribute('aria-label') || b.innerText || ''));
  const sureYaz = sn => sn >= 3600 ? `${Math.floor(sn / 3600)}:${String(Math.floor(sn / 60) % 60).padStart(2, '0')}:${String(sn % 60).padStart(2, '0')}` : `${Math.floor(sn / 60)}:${String(sn % 60).padStart(2, '0')}`;
  const kac = t => String(t || '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  function kartHtml(k){
    if (k.tur === 'mentor') return `<div class="k m"><b>Öneri</b><p>${kac(k.gozlem)}</p>${k.yap ? `<p class="y">→ ${kac(k.yap)}</p>` : ''}${k.soyle ? `<p class="s">“${kac(k.soyle)}”</p>` : ''}</div>`;
    if (k.tur === 'oneri') return `<div class="k o"><b>Şöyle diyebilirsiniz</b>${k.durum ? `<p>${kac(k.durum)}</p>` : ''}<p class="s">“${kac(k.soyle)}”</p></div>`;
    return `<div class="k h"><b>Hatırlatma</b><p>${kac(k.metin)}</p></div>`;
  }
  function gostergeKur(){
    if (gosterge) return;
    gosterge = document.createElement('div'); gosterge.id = 'vh-meet-gosterge';
    gosterge.style.cssText = 'position:fixed;top:12px;left:12px;z-index:2147483647;pointer-events:none';
    gKok = gosterge.attachShadow({mode: 'open'});
    gKok.innerHTML = `<style>
      :host{all:initial}*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}
      .hap{pointer-events:auto;display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:999px;background:rgba(20,20,22,.88);color:#fff;font-size:13px;font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.35);backdrop-filter:blur(8px);font-variant-numeric:tabular-nums;user-select:none}
      .n{width:9px;height:9px;border-radius:50%;background:#ff3b30;box-shadow:0 0 0 0 rgba(255,59,48,.6);animation:p 1.8s infinite}
      .hap.uy .n{background:#ff9f0a;animation:none}.hap.yok .n{background:#8e8e93;animation:none}
      @keyframes p{0%{box-shadow:0 0 0 0 rgba(255,59,48,.55)}70%{box-shadow:0 0 0 7px rgba(255,59,48,0)}100%{box-shadow:0 0 0 0 rgba(255,59,48,0)}}
      .r{color:#ffd60a;font-weight:600}.x{opacity:.6;font-weight:400;margin-left:2px}
      .kl{pointer-events:auto;margin-top:8px;display:grid;gap:8px;width:330px;max-width:calc(100vw - 24px)}
      .k{background:rgba(255,255,255,.97);color:#1c1c1e;border-radius:14px;padding:11px 13px;box-shadow:0 8px 28px rgba(0,0,0,.28);border-left:4px solid #ff5f1f;font-size:13.5px;line-height:1.4}
      .k.h{border-left-color:#3b63e6}.k.o{border-left-color:#30a46c}
      .k b{display:block;font-size:11.5px;letter-spacing:.02em;color:#6e6e73;margin-bottom:3px}.k p{margin:2px 0}.k .y{font-weight:600}.k .s{font-style:italic;color:#3a3a3c}
      .alt{display:flex;justify-content:flex-end;gap:12px}.pan{pointer-events:auto;background:#FF5F1F;border:0;color:#fff;font-size:12px;font-weight:600;border-radius:999px;padding:4px 11px;cursor:pointer}
      .kap{pointer-events:auto;justify-self:end;background:none;border:0;color:#fff;font-size:12px;opacity:.75;cursor:pointer;padding:2px 4px;text-shadow:0 1px 3px rgba(0,0,0,.6)}
    </style><div class="hap"><span class="n"></span><span class="t">Meet</span></div><div class="kl"></div>`;
    gKok.querySelector('.hap').onclick = () => { gAcik = !gAcik; gGorulen = gSonKart; gostergeCiz(); };
    (document.body || document.documentElement).appendChild(gosterge);
  }
  function gostergeCiz(){
    if (!gosterge) return;
    const v = gVeri || {}; const hap = gKok.querySelector('.hap'), t = gKok.querySelector('.t'), kl = gKok.querySelector('.kl');
    gosterge.style.display = (!aramada || gGizli || sunuyor()) ? 'none' : 'block';
    hap.className = 'hap' + (!v.kayit ? ' yok' : v.sorun ? ' uy' : '');
    const kartlar = v.kartlar || [];
    const yeniler = kartlar.filter(k => (k.zaman || 0) > gGorulen);
    const taze = kartlar.filter(k => Date.now() / 1000 - (k.zaman || 0) < 45 && (k.zaman || 0) > gGorulen);
    if (!v.kayit) t.textContent = v.baglanti === false ? 'Kayıt uygulamasına ulaşılamıyor' : 'Kayıt başlamadı';
    else t.innerHTML = (v.sorun ? kac(v.sorun) + ' · ' : 'Kaydediliyor ') + sureYaz(v.sure || 0) + (v.altyazi_kapali && !v.sorun ? ' <span class="r">· altyazı kapalı</span>' : '') + (yeniler.length && !gAcik && !taze.length ? ` <span class="r">· ${yeniler.length} öneri</span>` : '');
    const goster = gAcik ? kartlar.slice(-3).reverse() : taze.slice(-1);
    kl.innerHTML = (goster.length ? goster.map(kartHtml).join('') : '') + (gAcik ? `${goster.length ? '' : '<div class="k"><p>Henüz öneri yok. Toplantı sürdükçe burada belirir.</p></div>'}<div class="alt"><button class="pan" type="button">Yan paneli aç</button><button class="kap" type="button">Kapat</button></div>` : '');
    const kap = kl.querySelector('.kap'); if (kap) kap.onclick = e => { e.stopPropagation(); gAcik = false; gGorulen = gSonKart; gostergeCiz(); };
    const pan = kl.querySelector('.pan'); if (pan) pan.onclick = e => { e.stopPropagation(); gonder({tur: 'panel_ac'}, r => { if (!r || !r.tamam) pan.textContent = 'Eklenti simgesine tıklayın'; }); };
  }
  function gostergeTazele(){
    if (!aramada){ if (gosterge) gosterge.style.display = 'none'; return; }
    gostergeKur();
    gonder({tur: 'kayit_durum'}, v => {
      gVeri = v || {kayit: false, baglanti: false};
      const k = gVeri.kartlar || []; if (k.length) gSonKart = Math.max(gSonKart, ...k.map(x => x.zaman || 0));
      if (!gGorulen && k.length) gGorulen = Math.min(...k.map(x => x.zaman || 0)) - 1;   // sayfa açılınca eski kartlar "yeni" sayılmasın
      gostergeCiz();
    });
  }
  setInterval(gostergeTazele, 5000); setTimeout(gostergeTazele, 1500);

  // Konuşan: altyazı satırlarındaki ad (Meet altyazıları adla gelir) ya da "konuşuyor" işaretli kutu.
  function konusanBul(muts){
    const simdiMs = Date.now();
    if (simdiMs - sonAltyaziBak > 400){ sonAltyaziBak = simdiMs; const altAd = altyaziKonusan(); if (altAd) return altAd; }
    const adlar = [...isimler.keys()]; if (!adlar.length) return '';
    for (const m of muts){
      let el = m.target.nodeType === 3 ? m.target.parentElement : m.target; if (!el) continue;
      for (let i = 0; i < 4 && el; i++, el = el.parentElement){
        const t = (el.textContent || '').trim(); if (!t || t.length > 600) continue;
        for (const a of adlar){
          if (t.startsWith(a) && t.length > a.length + 2) return a;      // "Ayşe  merhaba arkadaşlar" biçimi
        }
      }
    }
    // Konuşma göstergesi olan kutu (aria/sınıf adında speaking / konuşuyor)
    const sp = document.querySelector('[aria-label*="speaking" i], [aria-label*="konuşuyor" i], [class*="speaking" i]');
    if (sp){ const kutu = sp.closest('[data-participant-id], [data-self-name], [role="listitem"]') || sp.parentElement;
      const t = temizAd(kutu?.textContent || ''); for (const a of adlar) if (t.includes(a)) return a; }
    return '';
  }

  const gozlemci = new MutationObserver(muts => {
    if (!aramada) return;
    if (Date.now() - sonAltyaziTara > 500){ sonAltyaziTara = Date.now(); try{ altyaziTara(); }catch(e){} }
    const ad = konusanBul(muts); const simdi = Date.now();
    if (ad && (ad !== sonKonusan || simdi - sonOlay > 4000)){ sonKonusan = ad; sonOlay = simdi; olaylar.push({ts: simdi / 1000, t: kayitId ? (simdi - kayitBas) / 1000 : null, ad}); }
  });
  gozlemci.observe(document.body, {subtree: true, childList: true, characterData: true});

  const bekle = ms => new Promise(r => setTimeout(r, ms));
  // Teams: altyazıyı aç (yalnızca bu kişinin ekranında görünür). Yeni tasarımda tek "Captions" anahtarı (araç çubuğunda ya da Diğer menüsünde),
  // eski tasarımda Diğer → Dil ve konuşma → Canlı altyazıları aç. Açıkken tıklamaz (kapatmasın).
  async function teamsAltyaziAc(){
    if (teamsAltyaziKutusu()) return true;
    const acik = t => t.getAttribute('data-tid') === 'closed-captions-button-on' || t.getAttribute('aria-checked') === 'true' || t.getAttribute('aria-pressed') === 'true';
    const anahtar = () => document.querySelector('[id="closed-captions-button"][data-tid^="closed-captions-button-"]');
    let t = anahtar(); if (t){ if (!acik(t)) t.click(); return true; }
    const diger = document.querySelector('button[data-tid="more-button"], button[id="callingButtons-showMoreBtn"]'); if (!diger) return false;
    const actim = diger.getAttribute('aria-expanded') !== 'true'; if (actim){ diger.click(); await bekle(700); }
    t = anahtar();
    if (t){ if (!acik(t)) t.click(); }
    else { const dil = document.querySelector('div[id="LanguageSpeechMenuControl-id"]');
      if (dil){ dil.click(); await bekle(700); const ac = document.querySelector('div[id="closed-captions-button"]'); if (ac) ac.click(); } }
    await bekle(500);
    const hala = document.querySelector('button[data-tid="more-button"][aria-expanded="true"], button[id="callingButtons-showMoreBtn"][aria-expanded="true"]'); if (hala) hala.click();
    return !!teamsAltyaziKutusu();
  }
  function altyaziAc(){
    if (platform === 'teams'){ teamsAltyaziAc().then(ok => { if (!ok && aramada && altyaziDeneme++ < 4) setTimeout(altyaziAc, 15000); }); return; }
    if (platform !== 'meet') return;
    if (document.querySelector('[role="region"][aria-label="Captions"], [role="region"][aria-label="Altyazılar"]')) return;   // zaten açık
    const b = document.querySelector('button[aria-label="Turn on captions"], [role="button"][aria-label="Turn on captions"], button[aria-label="Altyazıları aç"], [role="button"][aria-label="Altyazıları aç"]')
      || [...document.querySelectorAll('button, [role="button"]')].find(x => /altyaz|caption|untertitel/i.test(x.getAttribute('aria-label') || '') && !/kapat|off|turn off|aus/i.test(x.getAttribute('aria-label') || '') && x.getAttribute('aria-pressed') !== 'true');
    if (b) b.click();
  }
  let sonAltyaziBak = 0, altyaziDeneme = 0;

  // Toplantı adı: Meet'te arayüzdeki ad (data-meeting-title); sekme başlığı yalnızca "Meet - X" / "X - Google Meet" biçimindeyse
  function toplantiAdi(){
    const el = document.querySelector('[data-meeting-title]'); const a = el && el.getAttribute('data-meeting-title');
    if (a && a.trim().length >= 2) return a.trim();
    const t = document.title || '';
    if (platform === 'meet' && !/^Meet - |- Google Meet$/.test(t)) return '';
    if (platform === 'teams' && !/Microsoft Teams/.test(t)) return '';
    return t;
  }
  // Okuma sağlığı (2026-10-24): site, Meet/Teams sayfa yapısı değişip altyazı ya da konuşmacı okunamaz hâle gelince bunu fark edip uyarır
  let aramaBas = 0;
  function tani(simdiArama, kat){
    const altyazi = platform === 'teams' ? !!teamsAltyaziKutusu() : platform === 'meet' ? !!document.querySelector('[role="region"][aria-label="Captions"], [role="region"][aria-label="Altyazılar"]') : null;
    const t = {aramada: simdiArama, isaret: aramaIsaret, sure: simdiArama && aramaBas ? Math.round((Date.now() - aramaBas) / 1000) : 0, altyazi, son_konusan: sonOlay ? Math.round((Date.now() - sonOlay) / 1000) : null, katilimci: kat.length, platform};
    // 3.24 (2026-10-30): iki gerçek Meet görüşmesinde (7 katılımcı görülürken) hiçbir "aramada" işareti tutmadı; bir dahaki görüşmede sayfanın neye benzediği
    // sunucuda görülsün diye kısa bir ipucu: görünür düğme adları ve Meet'in veri öznitelikleri (kişisel veri yok; yalnız arayüz yazıları).
    if (platform === 'meet' && meetKodu() && !simdiArama){
      try{
        const dug = [...document.querySelectorAll('button, [role="button"]')].filter(gorunur).map(x => (x.getAttribute('aria-label') || x.textContent || '').trim().slice(0, 40)).filter(Boolean);
        t.ipucu = {dugmeler: [...new Set(dug)].slice(0, 20), self: !!document.querySelector('[data-self-name]'), baslik: !!document.querySelector('[data-meeting-title]'),
                   karo: document.querySelectorAll('[data-participant-id]').length, karo_gorunur: [...document.querySelectorAll('[data-participant-id]')].filter(gorunur).length,
                   mik: !!document.querySelector('[data-is-muted]'), bekleme: beklemedeMi()};
      }catch(e){}
    }
    return t;
  }
  // 27 Ekim: bir toplantıda altyazı hiç açılmadı, ne konuşmacı adı ne altyazı metni geldi. Başta 4 deneme vardı; artık aramada iki dakikada bir yeniden denenir.
  let sonAltyaziDeneme = 0;
  function altyaziBekci(){
    if (!aramada || platform === 'zoom' || platform === 'web' || Date.now() - sonAltyaziDeneme < 120000) return;
    const acik = platform === 'teams' ? !!teamsAltyaziKutusu() : !!document.querySelector('[role="region"][aria-label="Captions"], [role="region"][aria-label="Altyazılar"], [role="region"][aria-label*="aption" i], [role="region"][aria-label*="ltyaz" i]');
    if (acik) return;
    sonAltyaziDeneme = Date.now(); altyaziDeneme = 0; altyaziAc();
  }
  // Giriş (bekleme) ekranı (2026-10-28; kullanıcı: "takvim bağlı olmasa da toplantı öncesi hazırlık notu bekleme odasında hazırlansın"): Meet'in
  // "Şimdi katıl / Katılma isteği gönder" ekranı, Teams'in "Join now" ekranı, Zoom web önizlemesi. Meet bu ekranda içerideki kişileri yazar
  // ("Ayşe ve Can bu görüşmede", "X, Y, and 3 others are in this call"); adlar site'ye gider, hazırlık notu girmeden hazırlanır.
  const KATIL = /^(join now|ask to join|join|şimdi katıl|katılma isteği gönder|katılma isteğinde bulun|katıl|jetzt teilnehmen|teilnahme anfragen|teilnehmen)$/i;
  function beklemedeMi(){
    const dugmeler = [...document.querySelectorAll('button, [role="button"]')].filter(gorunur);
    const katil = dugmeler.some(b => KATIL.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
    if (platform === 'meet') return /^\/[a-z]{3}-[a-z]{4}-[a-z]{3}/.test(location.pathname) && katil;
    if (platform === 'teams') return bul('[data-tid="prejoin-join-button"], #prejoin-join-button');   // sohbetteki toplantı mesajlarında da "Katıl" düğmesi var
    if (platform === 'zoom') return bul('#preview-join-button, .preview-join-button') || (katil && /\/wc\//.test(location.pathname));
    return false;
  }
  const ICERIDE = /\s+(?:is|are) in (?:this|the) call\.?$|\s+(?:bu )?(?:görüşmede|aramada|toplantıda)(?: bulunuyor| bekliyor)?\.?$|\s+(?:ist|sind) (?:in diesem|im) (?:anruf|gespräch)\.?$/i;
  function beklemeKisileri(){
    const out = [];
    const satirlar = (document.body?.innerText || '').split('\n').map(x => x.trim()).filter(x => x && x.length < 220 && ICERIDE.test(x));
    for (const s of satirlar){
      if (/no one else|kimse yok|başka kimse|niemand/i.test(s)) continue;
      s.replace(ICERIDE, '').split(/,\s*|\s+and\s+|\s+ve\s+|\s+und\s+/i).map(temizAd)
        .filter(a => a && !/^\d+\s*(others?|more|kişi|kişi daha|weitere?)/i.test(a) && adGibi(a) && !ARAYUZ.test(a)).forEach(a => out.includes(a) || out.push(a));
    }
    return out.slice(0, 12);
  }
  // Giriş ekranında küçük kart: hazırlık notu hazırsa ilk satırları + "Yan paneli aç" (yan panel kapalı olabilir; kullanıcı notu girmeden görsün)
  let bKart = null, bKok = null, bKapandi = false, bImza = '';
  function beklemeKarti(veri){
    const s = veri && veri.suren;
    if (!s || !s.metin || bKapandi){ if (bKart) bKart.style.display = 'none'; return; }
    if (!bKart){
      bKart = document.createElement('div'); bKart.id = 'vh-meet-hazirlik';
      bKart.style.cssText = 'position:fixed;top:12px;left:12px;z-index:2147483647';
      bKok = bKart.attachShadow({mode: 'open'});
      (document.body || document.documentElement).appendChild(bKart);
    }
    bKart.style.display = 'block';
    const imza = s.id + '|' + s.metin.length; if (imza === bImza) return; bImza = imza;
    const satir = s.metin.split('\n').map(x => x.replace(/^[#>*\-\s]+/, '').replace(/\*\*/g, '').trim()).filter(Boolean).slice(0, 7);
    bKok.innerHTML = `<style>:host{all:initial}*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}
      .k{width:340px;max-width:calc(100vw - 24px);background:rgba(255,255,255,.98);color:#1c1c1e;border-radius:16px;padding:13px 15px;box-shadow:0 10px 30px rgba(0,0,0,.3);border-left:4px solid #ff5f1f;font-size:13px;line-height:1.45}
      b{display:block;font-size:11.5px;color:#6e6e73;margin-bottom:2px}h3{margin:0 0 6px;font-size:14.5px}p{margin:3px 0}.k small{color:#6e6e73}
      .alt{display:flex;justify-content:flex-end;gap:10px;margin-top:8px}button{border:0;border-radius:999px;font-size:12px;font-weight:600;padding:5px 12px;cursor:pointer}
      .pan{background:#ff5f1f;color:#fff}.kap{background:none;color:#6e6e73}</style>
      <div class="k"><b>Hazırlık notu · Meet</b><h3>${kac(s.ad || 'Bu toplantı')}</h3>${(s.kisiler || []).length ? `<small>${kac(s.kisiler.slice(0, 5).join(', '))}</small>` : ''}
      ${satir.map(x => `<p>${kac(x)}</p>`).join('')}<div class="alt"><button class="kap" type="button">Kapat</button><button class="pan" type="button">Tamamını aç</button></div></div>`;
    bKok.querySelector('.kap').onclick = () => { bKapandi = true; bKart.style.display = 'none'; };
    bKok.querySelector('.pan').onclick = () => gonder({tur: 'panel_ac'}, r => { if (!r || !r.tamam) bKok.querySelector('.pan').textContent = 'Eklenti simgesine tıklayın'; });
  }
  async function nabiz(){
    let simdiArama = aramadaMi(); let bekleme = !simdiArama && beklemedeMi();
    let kat = bekleme ? beklemeKisileri() : katilimcilariTopla(); const toplanti_adi = toplantiAdi();
    // 3.24: toplantı kodu var, giriş ekranı değil ve ekranda en az iki katılımcı adı okunuyorsa görüşmedeyiz (düğme adları tutmasa da)
    if (!simdiArama && !bekleme && platform === 'meet' && meetKodu() && kat.filter(adGibi).length >= 2){ simdiArama = true; aramaIsaret = 'katilimci'; }
    if (bekleme) gonder({tur: 'brif'}, beklemeKarti); else if (bKart) bKart.style.display = 'none';
    if (simdiArama && !aramada){ aramada = true; aramaBas = Date.now(); altyaziDeneme = 0; gonder({tur: 'arama_basladi', platform, baslik: toplanti_adi, katilimcilar: kat}); setTimeout(altyaziAc, 4000); }
    if (!simdiArama && aramada){ try{ altyaziTara(true); }catch(e){} altyaziGonder(); aramada = false; aramaBas = 0; gonder({tur: 'arama_bitti'}); }
    gonder({tur: 'nabiz', aktif: simdiArama, bekleme, platform, baslik: toplanti_adi, katilimcilar: kat, tani: tani(simdiArama, kat)});
    if (simdiArama){ try{ altyaziTara(); }catch(e){} altyaziGonder(); if (aramaBas && Date.now() - aramaBas > 60000) altyaziBekci(); }
    if (simdiArama && (olaylar.length || kat.length)){ const giden = olaylar.splice(0); gonder({tur: 'olaylar', olaylar: giden, katilimcilar: kat, baslik: toplanti_adi}); }
  }
  chrome.runtime.onMessage.addListener(m => { if (m.tur === 'kayit_durumu'){ kayitId = m.id || null; kayitBas = m.bas || Date.now(); if (!kayitId) olaylar = []; } });
  zamanlayici = setInterval(nabiz, 5000); nabiz();
  window.addEventListener('beforeunload', () => { if (aramada){ try{ altyaziTara(true); }catch(e){} altyaziGonder(); gonder({tur: 'arama_bitti'}); } });
})();

/* dil.js — arayüz dili (2026-10-25; kullanıcı: "Studio İngilizce de kullanılabilmeli").
   Türkçe kaynak metin değişmez; İngilizce seçiliyse sayfadaki metin düğümleri, placeholder/title/aria-label/alt öznitelikleri ve sonradan
   eklenen her öğe static/dil/en.json sözlüğüyle çevrilir (exact: birebir; patterns: "${ad} eklendi" gibi kalıplar). Sunucudan gelen Türkçe
   durum/hata satırları da aynı yoldan çevrilir. Seçim: localStorage `dil` → yoksa tarayıcı dili (tr değilse en).
   Dışarıya: window.DIL = {dil, locale, t(str), ayarla(dil)}. */
(function(){
  const S = document.documentElement.dataset;
  let dil = 'tr';
  try{ dil = localStorage.getItem('dil') || ((navigator.language || 'tr').toLowerCase().startsWith('tr') ? 'tr' : 'en'); }catch(_){ dil = 'tr'; }
  if (S.dil) dil = S.dil;                                   // sunucu kullanıcı ayarını verdiyse (ayarlar.json `dil`) o kazanır
  const D = {dil, locale: dil === 'tr' ? 'tr-TR' : 'en-US', exact: {}, patterns: [], hazir: false};
  const onb = new Map();
  function cevir(s){
    if (D.dil === 'tr' || !D.hazir || !s) return s;
    const m = s.match(/^(\s*)([\s\S]*?)(\s*)$/); const ic = m[2]; if (!ic) return s;
    if (onb.has(ic)) return m[1] + onb.get(ic) + m[3];
    let r = D.exact[ic];
    if (r === undefined && ic.length < 400){
      for (const [rx, kars] of D.patterns){ const mm = rx.exec(ic); if (mm){ r = kars.replace(/\$(\d)/g, (_, i) => { const g = mm[+i] || ''; return D.exact[g.trim()] !== undefined ? g.replace(g.trim(), D.exact[g.trim()]) : g; }); break; } }
    }
    if (r === undefined && /^[^\n]{1,200}$/.test(ic) && /[.:!?]\s/.test(ic)){   // cümle cümle (toast, log: "Bitti. Dosya: x")
      const parcalar = ic.split(/(?<=[.:!?])\s+/); const c = parcalar.map(p => D.exact[p] !== undefined ? D.exact[p] : null);
      if (c.some(x => x !== null)) r = parcalar.map((p, i) => c[i] !== null ? c[i] : p).join(' ');
    }
    if (r === undefined && ic.includes(' · ')){                           // "Sesten çözüldü · Hızlı" gibi birleşik rozetler parça parça
      const parcalar = ic.split(' · '); const c = parcalar.map(x => cevir(x)); if (c.some((x, i) => x !== parcalar[i])) r = c.join(' · ');
    }
    if (r === undefined) r = ic;
    if (onb.size > 5000) onb.clear();
    onb.set(ic, r); return m[1] + r + m[3];
  }
  const OZ = ['placeholder', 'title', 'aria-label', 'alt', 'data-ad'];
  function dugum(n){
    try{
      if (n.nodeType === 3){ if (n.parentNode && !['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(n.parentNode.nodeName) && n.nodeValue.trim()){ const y = cevir(n.nodeValue); if (y !== n.nodeValue) n.nodeValue = y; } return; }
      if (n.nodeType !== 1) return;
      if (n.nodeName === 'SCRIPT' || n.nodeName === 'STYLE') return;
      for (const a of OZ){ if (n.hasAttribute(a)){ const v = n.getAttribute(a); const y = cevir(v); if (y !== v) n.setAttribute(a, y); } }
      if (n.nodeName === 'INPUT' && (n.type === 'button' || n.type === 'submit') && n.value){ const y = cevir(n.value); if (y !== n.value) n.value = y; }
    }catch(e){ D.hata = String(e); }
    if (n.nodeType === 1) for (const c of Array.from(n.childNodes)) dugum(c);
  }
  let bekleyen = null;
  function tumu(){ if (D.dil === 'tr' || !D.hazir) return; dugum(document.body); if (document.title){ const y = cevir(document.title); if (y !== document.title) document.title = y; } }
  function izle(){
    if (D.dil === 'tr') return;
    const mo = new MutationObserver(ms => {
      for (const m of ms){
        if (m.type === 'characterData') dugum(m.target);
        else if (m.type === 'attributes') dugum(m.target);
        else m.addedNodes.forEach(dugum);
      }
    });
    mo.observe(document.documentElement, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: OZ});
    const t0 = document.title; let son = t0;
    setInterval(() => { if (document.title !== son){ const y = cevir(document.title); if (y !== document.title) document.title = y; son = document.title; } }, 1500);
  }
  D.t = cevir; D.yenile = tumu;
  D.ayarla = function(yeni){ try{ localStorage.setItem('dil', yeni); }catch(_){ } fetch('/api/ayarlar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({dil: yeni})}).catch(() => {}).finally(() => location.reload()); };
  window.DIL = D;
  document.documentElement.lang = D.dil;
  if (D.dil !== 'tr'){
    document.documentElement.classList.add('dil-' + D.dil);
    fetch('/static/dil/' + D.dil + '.json?v=' + (S.dilv || '1')).then(r => r.json()).then(j => {
      D.exact = j.exact || {}; D.patterns = (j.patterns || []).filter(([rx]) => rx.replace(/\(\.\*\?\)|[\^$\\]/g, '').trim().length >= 3).map(([rx, k]) => { try{ return [new RegExp(rx), k]; }catch(_){ return null; } }).filter(Boolean); D.hazir = true;
      const basla = () => { izle(); tumu(); };
      if (document.body) basla(); else document.addEventListener('DOMContentLoaded', basla);
    }).catch(() => {});
  }
})();

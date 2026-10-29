/* sahip_uzak.js — Meet'e dışarıdan, eşleştirilmiş kendi telefonunuzla (2026-10-25). Yalnız tünel adresinden açılan sahip sayfasına sunucu ekler
   (sunucu/25_sahip_uzak.py); asıl sınırlar sunucudadır. Burada: yalnız Mac'te anlamı olan şeyler gizlenir (Finder, diğer ürünlere giden adresler,
   davetler ve telefon eşleştirme), sayfa adı Meet. */
(() => {
if (document.documentElement.dataset.uzak !== '1') return;
const css = document.createElement('style');
css.textContent = `.urunbtn,.urunler,#tGhost,#mtDavet,#mtTelefon,#stDavet,#dlFinder,[data-finder],.finder{display:none!important}`;
document.head.appendChild(css);
const _pop = popover;
popover = function(anchor, items, opts){   // eslint-disable-line no-global-assign
  return _pop(anchor, (items || []).filter(it => !it || !/Finder|Couple|Klasörü aç|Ghost/.test(String(it[0] || ''))), opts);
};
document.title = 'Meet';
})();

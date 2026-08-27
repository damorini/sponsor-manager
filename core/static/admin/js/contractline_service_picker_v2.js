/* Selettore servizi "a finestra" per le righe contratto.
 *
 * Accanto a ogni tendina Servizio delle righe compare il pulsante "Catalogo":
 * apre una finestra con TUTTI i servizi dell'evento del contratto (ricerca
 * testuale, raggruppati per categoria, con codice e prezzo). Cliccando una
 * riga il servizio viene selezionato nella tendina (select2) della riga.
 * Solo in MODIFICA (serve l'evento del contratto salvato).
 */
'use strict';
(function () {
  var m = window.location.pathname.match(/^(.*\/contracts\/contract\/[^/]+\/)change\/?$/);
  if (!m) return; // pagina "aggiungi": l'evento non e' ancora noto
  var ENDPOINT = m[1] + 'servizi-json/';
  var cache = null;

  function fmtPrezzo(v) {
    try {
      return '€ ' + Number(v).toLocaleString('it-IT', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    } catch (e) { return '€ ' + v; }
  }

  function caricaServizi(cb) {
    if (cache) { cb(cache); return; }
    fetch(ENDPOINT, {credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (data) { cache = data.services || []; cb(cache); })
      .catch(function () { alert('Impossibile caricare il catalogo servizi.'); });
  }

  // ---- stile (una volta sola) ----
  var css = document.createElement('style');
  css.textContent = [
    '.vt-svcpick-btn{margin-left:4px;padding:3px 8px;border:1px solid #9C4A1F;border-radius:6px;',
    '  background:#fff;color:#9C4A1F;cursor:pointer;font-size:11px;white-space:nowrap;vertical-align:middle;}',
    '.vt-svcpick-btn:hover{background:#9C4A1F;color:#fff;}',
    '.vt-svcpick-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;',
    '  display:flex;align-items:center;justify-content:center;}',
    '.vt-svcpick-box{background:#fff;color:#1a1612;border-radius:12px;max-width:760px;width:92%;',
    '  max-height:80vh;display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.35);}',
    '.vt-svcpick-head{padding:14px 18px;border-bottom:1px solid #e8e2d8;display:flex;gap:10px;align-items:center;}',
    '.vt-svcpick-head h3{margin:0;font-size:15px;flex:1;color:#1a1612;}',
    '.vt-svcpick-head input{flex:1;padding:7px 10px;border:1px solid #ccc;border-radius:8px;font-size:13px;',
    '  background:#fff;color:#1a1612;}',
    '.vt-svcpick-close{border:0;background:none;font-size:20px;cursor:pointer;color:#666;}',
    '.vt-svcpick-list{overflow-y:auto;padding:6px 0;}',
    '.vt-svcpick-cat{padding:8px 18px 4px;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#9C4A1F;font-weight:700;}',
    '.vt-svcpick-row{display:flex;gap:12px;align-items:baseline;padding:7px 18px;cursor:pointer;font-size:13px;}',
    '.vt-svcpick-row:hover{background:#f7f1e8;}',
    '.vt-svcpick-row .n{flex:1;color:#1a1612;}',
    '.vt-svcpick-row .c{color:#8a7f71;font-size:11px;}',
    '.vt-svcpick-row .p{font-variant-numeric:tabular-nums;white-space:nowrap;color:#1a1612;}',
    '.vt-svcpick-row.inactive .n{color:#999;text-decoration:line-through;}',
    '.vt-svcpick-empty{padding:18px;color:#8a7f71;font-size:13px;}'
  ].join('\n');
  document.head.appendChild(css);

  // ---- modale ----
  var overlay = null;

  function chiudi() {
    if (overlay) { overlay.remove(); overlay = null; }
    document.removeEventListener('keydown', onKey);
  }
  function onKey(e) { if (e.key === 'Escape') chiudi(); }

  function apri(selectEl) {
    caricaServizi(function (servizi) {
      chiudi();
      overlay = document.createElement('div');
      overlay.className = 'vt-svcpick-overlay';
      var box = document.createElement('div');
      box.className = 'vt-svcpick-box';
      var head = document.createElement('div');
      head.className = 'vt-svcpick-head';
      var h = document.createElement('h3');
      h.textContent = 'Servizi dell’evento';
      var input = document.createElement('input');
      input.type = 'text';
      input.placeholder = 'Cerca per nome o codice…';
      var x = document.createElement('button');
      x.type = 'button';
      x.className = 'vt-svcpick-close';
      x.innerHTML = '×';
      x.addEventListener('click', chiudi);
      head.appendChild(h); head.appendChild(input); head.appendChild(x);
      var list = document.createElement('div');
      list.className = 'vt-svcpick-list';
      box.appendChild(head); box.appendChild(list);
      overlay.appendChild(box);
      overlay.addEventListener('click', function (e) { if (e.target === overlay) chiudi(); });
      document.addEventListener('keydown', onKey);
      document.body.appendChild(overlay);

      function render(filtro) {
        list.innerHTML = '';
        var f = (filtro || '').toLowerCase();
        var perCat = {};
        servizi.forEach(function (s) {
          var testo = (s.name + ' ' + s.code).toLowerCase();
          if (f && testo.indexOf(f) === -1) return;
          var cat = s.category || 'Altro';
          (perCat[cat] = perCat[cat] || []).push(s);
        });
        var cats = Object.keys(perCat).sort();
        if (!cats.length) {
          var e = document.createElement('div');
          e.className = 'vt-svcpick-empty';
          e.textContent = 'Nessun servizio trovato.';
          list.appendChild(e);
          return;
        }
        cats.forEach(function (cat) {
          var hcat = document.createElement('div');
          hcat.className = 'vt-svcpick-cat';
          hcat.textContent = cat;
          list.appendChild(hcat);
          perCat[cat].forEach(function (s) {
            var row = document.createElement('div');
            row.className = 'vt-svcpick-row' + (s.active ? '' : ' inactive');
            var n = document.createElement('span'); n.className = 'n'; n.textContent = s.name;
            var c = document.createElement('span'); c.className = 'c'; c.textContent = s.code;
            var p = document.createElement('span'); p.className = 'p'; p.textContent = fmtPrezzo(s.price);
            row.appendChild(n); row.appendChild(c); row.appendChild(p);
            row.addEventListener('click', function () {
              var $ = window.django && window.django.jQuery;
              if ($) {
                var $sel = $(selectEl);
                if (!$sel.find('option[value="' + s.id + '"]').length) {
                  $sel.append(new Option(s.name, s.id, true, true));
                }
                $sel.val(s.id).trigger('change');
              } else {
                selectEl.value = s.id;
                selectEl.dispatchEvent(new Event('change', {bubbles: true}));
              }
              chiudi();
            });
            list.appendChild(row);
          });
        });
      }
      render('');
      input.addEventListener('input', function () { render(input.value); });
      setTimeout(function () { input.focus(); }, 50);
    });
  }

  // ---- pulsanti accanto alle tendine Servizio ----
  // Il click e' DELEGATO al documento: le righe nuove vengono clonate dal
  // template nascosto (__prefix__) e i listener per-pulsante andrebbero persi.
  function aggiungiPulsanti() {
    document.querySelectorAll('select[id^="id_lines-"][id$="-service"]').forEach(function (sel) {
      if (sel.id.indexOf('__prefix__') !== -1) return; // riga-template nascosta
      var cella = sel.closest('td') || sel.parentElement;
      if (!cella) return;
      // ricrea sempre il pulsante: i cloni portano con se' copie senza listener
      cella.querySelectorAll('.vt-svcpick-btn').forEach(function (b) { b.remove(); });
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'vt-svcpick-btn';
      btn.textContent = '📋 Catalogo';
      btn.title = 'Scegli il servizio da una finestra con tutto il catalogo dell’evento';
      var target = sel.nextElementSibling && sel.nextElementSibling.classList &&
                   sel.nextElementSibling.classList.contains('select2')
                   ? sel.nextElementSibling : sel;
      target.insertAdjacentElement('afterend', btn);
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.vt-svcpick-btn') : null;
    if (!btn) return;
    e.preventDefault();
    var cella = btn.closest('td') || btn.parentElement;
    var sel = cella && cella.querySelector('select[id^="id_lines-"][id$="-service"]');
    if (sel) apri(sel);
  });

  function avvia() {
    aggiungiPulsanti();
    var $ = window.django && window.django.jQuery;
    if ($) {
      $(document).on('formset:added', function () {
        setTimeout(aggiungiPulsanti, 0);
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', avvia);
  } else {
    avvia();
  }
})();

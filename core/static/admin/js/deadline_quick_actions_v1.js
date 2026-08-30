/* Azioni rapide sulle scadenze: '✓ Ricevuta' ed 'Esonera' a UN click.
 *
 * I pulsanti (class dq-btn, generati da _deadline_azioni_rapide_html in
 * contracts/admin.py) POSTano via fetch all'endpoint indicato in data-url,
 * col token CSRF preso dal form della pagina admin. Funziona sia nella
 * lista Scadenze sia nelle scadenze inline della scheda contratto. */
'use strict';
(function () {
  function csrf() {
    var i = document.querySelector('input[name=csrfmiddlewaretoken]');
    return i ? i.value : '';
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.dq-btn') : null;
    if (!btn) return;
    e.preventDefault();
    if (btn.dataset.confirm && !window.confirm(btn.dataset.confirm)) return;
    btn.disabled = true;
    btn.style.opacity = '.5';
    fetch(btn.dataset.url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf() },
      credentials: 'same-origin',
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      window.location.reload();
    }).catch(function () {
      alert('Operazione non riuscita: ricarica la pagina e riprova.');
      btn.disabled = false;
      btn.style.opacity = '';
    });
  });
})();

// Pulsante "Traduci IT->EN" per i campi bilingue dell'admin.
(function () {
  function getCookie(name) {
    var v = null;
    if (document.cookie) {
      document.cookie.split(';').forEach(function (c) {
        c = c.trim();
        if (c.indexOf(name + '=') === 0) v = decodeURIComponent(c.slice(name.length + 1));
      });
    }
    return v;
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.cr-translate-btn') : null;
    if (!btn) return;
    e.preventDefault();
    var src = document.getElementById(btn.getAttribute('data-src'));
    var dst = document.getElementById(btn.getAttribute('data-dst'));
    if (!src || !dst) return;
    var text = (src.value || '').trim();
    if (!text) { alert('Scrivi prima il testo in italiano.'); return; }
    var old = btn.textContent;
    btn.disabled = true; btn.textContent = 'Traduco...';
    fetch('/admin/cruscotto/traduci/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({
        text: text,
        source: btn.getAttribute('data-source'),
        target: btn.getAttribute('data-target')
      })
    })
    .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
    .then(function (res) {
      if (res.ok && res.d.translated) { dst.value = res.d.translated; }
      else { alert((res.d && res.d.error) || 'Traduzione non riuscita.'); }
    })
    .catch(function () { alert('Errore di rete nella traduzione.'); })
    .finally(function () { btn.disabled = false; btn.textContent = old; });
  });
})();

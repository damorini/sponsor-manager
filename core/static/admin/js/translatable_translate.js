// Pulsante "Traduci IT->EN" per i campi bilingue dell'admin.
// Compatibile con l'editor TinyMCE (corpo email): se l'editor esiste, legge e
// scrive li' dentro e traduce in HTML (mantiene la formattazione); altrimenti
// usa la casella di testo come prima.
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
  function editorFor(id) {
    return (window.tinymce && tinymce.get) ? tinymce.get(id) : null;
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.cr-translate-btn') : null;
    if (!btn) return;
    e.preventDefault();
    var srcId = btn.getAttribute('data-src');
    var dstId = btn.getAttribute('data-dst');
    var srcEd = editorFor(srcId);
    var dstEd = editorFor(dstId);
    var srcEl = document.getElementById(srcId);
    var dstEl = document.getElementById(dstId);
    var isHtml = !!srcEd;
    var text = srcEd ? srcEd.getContent() : (srcEl ? (srcEl.value || '') : '');
    text = (text || '').trim();
    if (!text) { alert('Scrivi prima il testo in italiano.'); return; }
    var old = btn.textContent;
    btn.disabled = true; btn.textContent = 'Traduco...';
    fetch('/admin/cruscotto/traduci/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({
        text: text,
        source: btn.getAttribute('data-source'),
        target: btn.getAttribute('data-target'),
        html: isHtml
      })
    })
    .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
    .then(function (res) {
      if (res.ok && res.d.translated) {
        if (dstEd) { dstEd.setContent(res.d.translated); }
        else if (dstEl) { dstEl.value = res.d.translated; }
      } else {
        alert((res.d && res.d.error) || 'Traduzione non riuscita.');
      }
    })
    .catch(function () { alert('Errore di rete nella traduzione.'); })
    .finally(function () { btn.disabled = false; btn.textContent = old; });
  });
})();

// Editor visuale (TinyMCE) per il corpo delle email.
// - Template email (textarea[data-wysiwyg]): editor + menu Segnaposto.
// - Composizione email singola (textarea[data-translate-inplace]): in piu',
//   pulsante "Traduci IT->EN" che traduce il testo dell'editor sul posto.
document.addEventListener('DOMContentLoaded', function () {
  if (typeof tinymce === 'undefined') { return; }

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

  var GROUPS = [
    { title: 'Contatto', items: [
      ['Nome e cognome', '{{ contact.full_name }}']
    ]},
    { title: 'Evento', items: [
      ['Nome evento', '{{ event_name }}'],
      ['Data inizio', '{{ event.start_date }}'],
      ['Data fine', '{{ event.end_date }}'],
      ['Luogo', '{{ event.location }}']
    ]},
    { title: 'Contratto', items: [
      ['Numero contratto', '{{ contract.contract_number }}'],
      ['Ragione sociale sponsor', '{{ sponsor.legal_name }}']
    ]},
    { title: 'Scadenza (solo email scadenze)', items: [
      ['Titolo scadenza', '{{ deadline.title }}'],
      ['Descrizione', '{{ deadline.description }}'],
      ['Data scadenza', '{{ deadline.due_date }}'],
      ['Giorni rimanenti', '{{ days_remaining }}'],
      ['Giorni di ritardo', '{{ days_overdue }}']
    ]},
    { title: 'Pagamento (solo conferme)', items: [
      ['Importo', '{{ payment.amount_gross }}'],
      ['Data pagamento', '{{ payment.completed_at }}'],
      ['Metodo', '{{ payment.get_payment_method_display }}']
    ]},
    { title: 'Segreteria e link', items: [
      ['Nome segreteria', '{{ org_name }}'],
      ['Email segreteria', '{{ org_email }}'],
      ['Telefono segreteria', '{{ org_phone }}'],
      ['Sito segreteria', '{{ org_website }}'],
      ['Link al portale', '{{ portal_url }}'],
      ['Link al checkout', '{{ checkout_url }}']
    ]}
  ];

  function addSegnaposto(editor) {
    editor.ui.registry.addMenuButton('segnaposto', {
      text: 'Segnaposto',
      tooltip: 'Inserisci un segnaposto al cursore',
      fetch: function (callback) {
        var items = GROUPS.map(function (g) {
          return {
            type: 'nestedmenuitem',
            text: g.title,
            getSubmenuItems: function () {
              return g.items.map(function (entry) {
                return {
                  type: 'menuitem',
                  text: entry[0],
                  onAction: function () { editor.insertContent(entry[1]); }
                };
              });
            }
          };
        });
        callback(items);
      }
    });
  }

  function addTraduci(editor) {
    editor.ui.registry.addButton('traducimail', {
      text: 'Traduci IT\u2192EN',
      tooltip: 'Traduci il testo in inglese',
      onAction: function () {
        var content = editor.getContent();
        if (!content || !content.replace(/<[^>]*>/g, '').trim()) {
          editor.notificationManager.open({ text: 'Scrivi prima il testo in italiano.', type: 'warning', timeout: 3000 });
          return;
        }
        editor.setProgressState(true);
        fetch('/admin/cruscotto/traduci/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ text: content, source: 'it', target: 'en', html: true })
        })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (res.ok && res.d.translated) {
            editor.setContent(res.d.translated);
            var langSel = document.getElementById('language');
            if (langSel) { langSel.value = 'en'; }
          } else {
            editor.notificationManager.open({ text: (res.d && res.d.error) || 'Traduzione non riuscita.', type: 'error', timeout: 4000 });
          }
        })
        .catch(function () { editor.notificationManager.open({ text: 'Errore di rete nella traduzione.', type: 'error', timeout: 4000 }); })
        .finally(function () { editor.setProgressState(false); });
      }
    });
  }

  var COMMON = {
    menubar: false,
    plugins: 'lists link code autoresize',
    toolbar_mode: 'wrap',
    min_height: 260,
    branding: false,
    promotion: false,
    license_key: 'gpl',
    entity_encoding: 'raw'
  };

  // 1) Template email: editor + Segnaposto (la traduzione la fa il pulsante esterno).
  tinymce.init(Object.assign({}, COMMON, {
    selector: 'textarea[data-wysiwyg]:not([data-translate-inplace])',
    toolbar: 'undo redo | bold italic underline | bullist numlist | link | segnaposto | removeformat | code',
    setup: function (editor) { addSegnaposto(editor); }
  }));

  // 2) Composizione email singola: editor + Segnaposto + Traduci IT->EN sul posto.
  tinymce.init(Object.assign({}, COMMON, {
    selector: 'textarea[data-translate-inplace]',
    toolbar: 'undo redo | bold italic underline | bullist numlist | link | segnaposto | traducimail | removeformat | code',
    setup: function (editor) { addSegnaposto(editor); addTraduci(editor); }
  }));
});

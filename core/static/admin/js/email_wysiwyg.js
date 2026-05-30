// Editor visuale (TinyMCE) sul corpo delle email: textarea[data-wysiwyg].
// Include un menu a tendina "Segnaposto" per inserire i campi dinamici
// al punto del cursore.
document.addEventListener('DOMContentLoaded', function () {
  if (typeof tinymce === 'undefined') { return; }

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

  tinymce.init({
    selector: 'textarea[data-wysiwyg]',
    menubar: false,
    plugins: 'lists link code autoresize',
    toolbar: 'undo redo | bold italic underline | bullist numlist | link | segnaposto | removeformat | code',
    toolbar_mode: 'wrap',
    min_height: 260,
    branding: false,
    promotion: false,
    license_key: 'gpl',
    entity_encoding: 'raw',
    setup: function (editor) {
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
  });
});

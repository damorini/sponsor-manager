// Editor visuale semplice (TinyMCE) per i campi testo con data-richtext.
// Pulsanti: grassetto, corsivo, sottolineato, elenchi, link.
document.addEventListener('DOMContentLoaded', function () {
  if (typeof tinymce === 'undefined') { return; }
  tinymce.init({
    selector: 'textarea[data-richtext]',
    menubar: false,
    plugins: 'lists link autoresize',
    toolbar: 'undo redo | bold italic underline | bullist numlist | link | removeformat | code',
    toolbar_mode: 'wrap',
    min_height: 200,
    branding: false,
    promotion: false,
    license_key: 'gpl',
    entity_encoding: 'raw'
  });
});

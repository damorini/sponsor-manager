// Editor visuale (TinyMCE) sul corpo delle email: textarea[data-wysiwyg].
document.addEventListener('DOMContentLoaded', function () {
  if (typeof tinymce === 'undefined') { return; }
  tinymce.init({
    selector: 'textarea[data-wysiwyg]',
    menubar: false,
    plugins: 'lists link code autoresize',
    toolbar: 'undo redo | bold italic underline | bullist numlist | link | removeformat | code',
    toolbar_mode: 'wrap',
    min_height: 260,
    branding: false,
    promotion: false,
    license_key: 'gpl',
    entity_encoding: 'raw'
  });
});

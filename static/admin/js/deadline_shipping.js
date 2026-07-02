(function () {
  'use strict';

  function toggleShipping() {
    var select = document.getElementById('id_submission_kind');
    if (!select) return;
    var row = document.querySelector('.field-shipping_instructions');
    if (!row) return;
    row.style.display = select.value === 'physical' ? '' : 'none';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var select = document.getElementById('id_submission_kind');
    if (!select) return;
    toggleShipping();
    select.addEventListener('change', toggleShipping);
  });
})();

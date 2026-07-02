(function () {
  'use strict';

  function findShippingRow() {
    // Prova diversi selettori per compatibilità con diverse versioni di Django admin
    return (
      document.querySelector('.field-shipping_instructions') ||
      document.querySelector('[class*="field-shipping_instructions"]') ||
      (function () {
        // Fallback: cerca per label
        var labels = document.querySelectorAll('label');
        for (var i = 0; i < labels.length; i++) {
          if (labels[i].textContent.trim().toLowerCase().includes('istruzioni')) {
            var row = labels[i].closest('.form-row') || labels[i].closest('div');
            if (row) return row;
          }
        }
        return null;
      })()
    );
  }

  function toggleShipping() {
    var select = document.getElementById('id_submission_kind');
    if (!select) return;
    var row = findShippingRow();
    if (!row) return;
    if (select.value === 'physical') {
      row.style.display = '';
      row.style.removeProperty('display');
    } else {
      row.style.display = 'none';
    }
  }

  function init() {
    var select = document.getElementById('id_submission_kind');
    if (!select) return;
    toggleShipping();
    select.addEventListener('change', toggleShipping);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  // Secondo tentativo dopo 500ms nel caso il DOM venga modificato da altri script
  setTimeout(init, 500);
})();

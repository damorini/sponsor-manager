'use strict';
// Righe contratto: la tendina "Variante" mostra solo le varianti del
// servizio scelto nella stessa riga. Ogni opzione variante porta
// data-service=<id servizio> (vedi _VariantSelectByService).
(function () {
    // resetIfInvalid: true solo quando l'utente cambia il servizio (azione
    // esplicita). Al caricamento NON azzeriamo mai una variante gia' scelta.
    function filterVariant(serviceSel, variantSel, resetIfInvalid) {
        var sid = serviceSel && serviceSel.value ? serviceSel.value : '';
        var cur = variantSel.value;
        Array.prototype.forEach.call(variantSel.options, function (op) {
            if (op.value === '') { op.hidden = false; op.disabled = false; return; }
            var match = sid !== '' && op.getAttribute('data-service') === sid;
            // L'opzione attualmente selezionata resta sempre visibile (no perdite).
            var keepVisible = match || op.value === cur;
            op.hidden = !keepVisible;
            op.disabled = !keepVisible;
        });
        if (resetIfInvalid && cur) {
            var curOpt = variantSel.querySelector('option[value="' + cur + '"]');
            var stillOk = curOpt && curOpt.getAttribute('data-service') === sid && sid !== '';
            if (!stillOk) { variantSel.value = ''; }
        }
    }
    function wire(variantSel) {
        if (variantSel.dataset.varwired) { return; }
        variantSel.dataset.varwired = '1';
        var row = variantSel.closest('tr') || variantSel.parentNode;
        // il campo servizio finisce con '-service' (la variante con '-service_variant')
        var serviceSel = row.querySelector("select[id$='-service']");
        if (!serviceSel) { return; }
        filterVariant(serviceSel, variantSel, false);
        serviceSel.addEventListener('change', function () {
            filterVariant(serviceSel, variantSel, true);
        });
    }
    function wireAll() {
        document.querySelectorAll("select[id$='-service_variant']").forEach(wire);
    }
    function init() {
        wireAll();
        // righe aggiunte con "Add another"
        document.addEventListener('formset:added', wireAll);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }
})();

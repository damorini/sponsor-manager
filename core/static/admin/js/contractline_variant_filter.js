'use strict';
// Righe contratto: la tendina "Variante" mostra solo le varianti del
// servizio scelto nella stessa riga. Ogni opzione variante porta
// data-service=<id servizio> (vedi _VariantSelectByService).
//
// IMPORTANTE: il campo Servizio è un Select2 (autocomplete). Select2 emette
// l'evento "change" tramite jQuery, che NON viene intercettato da un
// addEventListener nativo: per questo usiamo la delega di django.jQuery.
(function () {
    function filterVariant(serviceSel, variantSel, resetIfInvalid) {
        var sid = serviceSel && serviceSel.value ? serviceSel.value : '';
        var cur = variantSel.value;
        Array.prototype.forEach.call(variantSel.options, function (op) {
            if (op.value === '') { op.hidden = false; op.disabled = false; return; }
            var match = sid !== '' && op.getAttribute('data-service') === sid;
            // L'opzione selezionata resta sempre visibile (nessuna perdita).
            var keepVisible = match || op.value === cur;
            op.hidden = !keepVisible;
            op.disabled = !keepVisible;
        });
        if (resetIfInvalid && cur) {
            var curOpt = variantSel.querySelector('option[value="' + cur + '"]');
            var ok = curOpt && sid !== '' && curOpt.getAttribute('data-service') === sid;
            if (!ok) { variantSel.value = ''; }
        }
    }
    function variantInRow(serviceEl) {
        var row = serviceEl.closest('tr') || serviceEl.parentNode;
        return row ? row.querySelector("select[id$='-service_variant']") : null;
    }
    function applyInitial() {
        // Righe reali (esclude il template __prefix__): filtra in base al
        // servizio gia' selezionato, senza azzerare nulla.
        document.querySelectorAll("select[id*='lines-'][id$='-service']").forEach(function (s) {
            if (s.id.indexOf('__prefix__') !== -1) { return; }
            var v = variantInRow(s);
            if (v) { filterVariant(s, v, false); }
        });
    }
    function init($) {
        // Cambio servizio (anche via Select2): filtra le varianti della riga.
        $(document).on('change', "select[id*='lines-'][id$='-service']", function () {
            if (this.id.indexOf('__prefix__') !== -1) { return; }
            var v = variantInRow(this);
            if (v) { filterVariant(this, v, true); }
        });
        applyInitial();
        // Righe aggiunte con "Add another": applica il filtro iniziale.
        var onAdded = function () { applyInitial(); };
        $(document).on('formset:added', onAdded);
        document.addEventListener('formset:added', onAdded);
    }
    function boot() {
        var $ = (window.django && window.django.jQuery) ? window.django.jQuery : window.jQuery;
        if (!$) { setTimeout(boot, 100); return; }
        init($);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else { boot(); }
})();

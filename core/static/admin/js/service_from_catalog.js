'use strict';
// Form Servizio: scegliendo una voce dal Catalogo madre (#id_catalog_source)
// auto-compila codice, nome IT/EN, descrizione, prezzo, IVA, ecc.
(function () {
    function setText(id, val) {
        var el = document.getElementById(id);
        if (el) { el.value = (val == null ? '' : val); }
    }
    function setSelect(id, val) {
        var el = document.getElementById(id);
        if (!el || val == null || val === '') { return; }
        // imposta solo se esiste l'opzione corrispondente
        for (var i = 0; i < el.options.length; i++) {
            if (el.options[i].value === String(val)) { el.value = String(val); break; }
        }
    }
    function setCheck(id, val) {
        var el = document.getElementById(id);
        if (el) { el.checked = !!val; }
    }
    function fill(d) {
        setText('id_code', d.code);
        setText('id_name_0', d.name ? d.name.it : '');
        setText('id_name_1', d.name ? d.name.en : '');
        setText('id_description_0', d.description ? d.description.it : '');
        setText('id_description_1', d.description ? d.description.en : '');
        setText('id_base_price', d.base_price);
        setText('id_vat_rate', d.vat_rate);
        setText('id_max_quantity', d.max_quantity);
        setSelect('id_pricing_mode', d.pricing_mode);
        setSelect('id_accounting_category', d.accounting_category);
        setCheck('id_triggers_deadlines', d.triggers_deadlines);
        setCheck('id_is_self_purchasable', d.is_self_purchasable);
    }
    function init() {
        var sel = document.getElementById('id_catalog_source');
        if (!sel) { return; }
        sel.addEventListener('change', function () {
            var id = sel.value;
            if (!id) { return; }
            fetch('/admin/cruscotto/catalog-service/' + id + '/dati/',
                  { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) { if (d) { fill(d); } })
                .catch(function () {});
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }
})();

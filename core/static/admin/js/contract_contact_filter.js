'use strict';
// Filtra il firmatario per lo sponsor scelto SENZA ricreare la tendina:
// aggiunge il parametro 'sponsor' alla chiamata di ricerca (autocomplete).
// Cosi' la tendina resta quella di Django (larghezza corretta, nessun lampo).
(function () {
    function start($) {
        console.log('[filtro contatti v3] attivo - nessun reinit tendina');
        function fieldIs(data, name) {
            if (data && typeof data === 'object') { return data.field_name === name; }
            if (typeof data === 'string') {
                return new RegExp('(^|&)field_name=' + name + '(&|$)').test(data);
            }
            return false;
        }
        function valOf(sel) {
            const el = document.querySelector(sel);
            return el ? (el.value || '') : '';
        }
        function addParam(options, key, value) {
            if (!value) { return; }
            if (options.data && typeof options.data === 'object') {
                options.data[key] = value;
            } else if (typeof options.data === 'string'
                       && options.data.indexOf(key + '=') === -1) {
                options.data += '&' + key + '=' + encodeURIComponent(value);
            }
        }
        $.ajaxPrefilter(function (options) {
            if (!options.url || options.url.indexOf('autocomplete') === -1) { return; }
            // Firmatario: filtra per sponsor scelto.
            if (fieldIs(options.data, 'sponsor_signer_contact')) {
                addParam(options, 'sponsor', valOf('#id_sponsor'));
            }
            // Contratto principale (parent): solo contratti dello stesso sponsor
            // (e stesso evento). Il server limita gia' ai contratti PRINCIPALI.
            if (fieldIs(options.data, 'parent_contract')) {
                addParam(options, 'sponsor', valOf('#id_sponsor'));
                addParam(options, 'event', valOf('#id_event'));
            }
        });
        $(function () {
            // Cambiando sponsor, azzera i campi dipendenti.
            $('#id_sponsor').on('change', function () {
                ['#id_sponsor_signer_contact', '#id_parent_contract'].forEach(function (sel) {
                    const $c = $(sel);
                    if ($c.length) { $c.val(null).trigger('change'); }
                });
            });
        });
    }
    function waitJQ(n) {
        if (window.django && django.jQuery) { start(django.jQuery); return; }
        if (n <= 0) { return; }
        setTimeout(function () { waitJQ(n - 1); }, 100);
    }
    waitJQ(50);
})();

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
        $.ajaxPrefilter(function (options) {
            if (!options.url || options.url.indexOf('autocomplete') === -1) { return; }
            if (!fieldIs(options.data, 'sponsor_signer_contact')) { return; }
            const sp = valOf('#id_sponsor');
            if (!sp) { return; }
            if (options.data && typeof options.data === 'object') {
                options.data.sponsor = sp;
            } else if (typeof options.data === 'string' && options.data.indexOf('sponsor=') === -1) {
                options.data += '&sponsor=' + encodeURIComponent(sp);
            }
        });
        $(function () {
            $('#id_sponsor').on('change', function () {
                const $c = $('#id_sponsor_signer_contact');
                if ($c.length) { $c.val(null).trigger('change'); }
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

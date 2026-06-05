'use strict';
// Filtra stand / blocco / servizi per l'evento scelto SENZA ricreare le tendine:
// aggiunge il parametro 'event' alla chiamata di ricerca (autocomplete).
(function () {
    function start($) {
        console.log('[filtro evento v3] attivo');
        const DIPENDENTI = ['stand', 'stand_block', 'service'];
        function fieldName(data) {
            if (data && typeof data === 'object') { return data.field_name || ''; }
            if (typeof data === 'string') {
                const m = data.match(/(?:^|&)field_name=([^&]*)/);
                return m ? m[1] : '';
            }
            return '';
        }
        function valOf(sel) {
            const el = document.querySelector(sel);
            return el ? (el.value || '') : '';
        }
        $.ajaxPrefilter(function (options) {
            if (!options.url || options.url.indexOf('autocomplete') === -1) { return; }
            if (DIPENDENTI.indexOf(fieldName(options.data)) === -1) { return; }
            const ev = valOf('#id_event');
            if (!ev) { return; }
            if (options.data && typeof options.data === 'object') {
                options.data.event = ev;
            } else if (typeof options.data === 'string' && options.data.indexOf('event=') === -1) {
                options.data += '&event=' + encodeURIComponent(ev);
            }
        });
        $(function () {
            $('#id_event').on('change', function () {
                $('#id_stand, #id_stand_block').val(null).trigger('change');
                $('select[name$="-service"]').val(null).trigger('change');
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

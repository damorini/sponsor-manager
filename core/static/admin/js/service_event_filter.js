'use strict';
// Form Servizio: filtra l'autocomplete dei "Servizi inclusi" (campo 'child')
// sull'evento scelto nel form (#id_event), così anche durante la CREAZIONE di un
// nuovo servizio si vedono solo i servizi dello stesso congresso.
(function () {
    function start($) {
        function fieldName(data) {
            if (data && typeof data === 'object') { return data.field_name || ''; }
            if (typeof data === 'string') {
                const m = data.match(/(?:^|&)field_name=([^&]*)/);
                return m ? m[1] : '';
            }
            return '';
        }
        $.ajaxPrefilter(function (options) {
            if (!options.url || options.url.indexOf('autocomplete') === -1) { return; }
            if (fieldName(options.data) !== 'child') { return; }
            const evEl = document.querySelector('#id_event');
            const ev = evEl ? (evEl.value || '') : '';
            if (!ev) { return; }
            // se l'evento è già nell'URL (servizio già salvato) non duplico
            if (options.url.indexOf('event=') !== -1) { return; }
            if (options.data && typeof options.data === 'object') {
                if (!options.data.event) { options.data.event = ev; }
            } else if (typeof options.data === 'string' && options.data.indexOf('event=') === -1) {
                options.data += '&event=' + encodeURIComponent(ev);
            }
        });
        // se cambio evento, azzero gli inclusi già scelti (erano di un altro evento)
        $(function () {
            $('#id_event').on('change', function () {
                $('select[name$="-child"]').val(null).trigger('change');
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

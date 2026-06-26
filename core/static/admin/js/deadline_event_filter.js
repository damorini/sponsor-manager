'use strict';
// DeadlineTemplate admin: filtra l'autocomplete "service" in base all'evento scelto.
// Usa ajaxPrefilter per iniettare ?event=<id> in ogni chiamata autocomplete sul campo service.
(function () {
    function start($) {
        $.ajaxPrefilter(function (options) {
            if (!options.url || options.url.indexOf('autocomplete') === -1) { return; }
            var data = options.data;
            var fieldName = '';
            if (data && typeof data === 'object') {
                fieldName = data.field_name || '';
            } else if (typeof data === 'string') {
                var m = data.match(/(?:^|&)field_name=([^&]*)/);
                fieldName = m ? m[1] : '';
            }
            if (fieldName !== 'service') { return; }
            var evEl = document.querySelector('#id_event');
            var ev = evEl ? (evEl.value || '') : '';
            if (!ev) { return; }
            if (options.url.indexOf('event=') !== -1) { return; }
            if (data && typeof data === 'object') {
                if (!data.event) { data.event = ev; }
            } else if (typeof data === 'string' && data.indexOf('event=') === -1) {
                options.data += '&event=' + encodeURIComponent(ev);
            }
        });

        $(function () {
            $('#id_event').on('change', function () {
                // Cambio evento: azzera il servizio scelto (apparteneva all'evento precedente)
                var $svc = $('#id_service');
                $svc.val(null).trigger('change');
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

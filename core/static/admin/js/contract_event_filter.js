'use strict';
// Tendine dipendenti dall'evento nel contratto: inoltra l'evento scelto
// (#id_event) alle tendine autocomplete di stand/blocco/servizi.
{
    const $ = django.jQuery;
    const EVENT = '#id_event';
    const FISSI = ['#id_stand', '#id_stand_block'];

    function eventVal() {
        const el = document.querySelector(EVENT);
        return el ? (el.value || '') : '';
    }

    function rebind($el) {
        const el = $el[0];
        const url = el.getAttribute('data-ajax--url');
        if (!url) { return; }
        if ($el.data('select2')) { $el.select2('destroy'); }
        $el.select2({
            ajax: {
                url: url,
                dataType: 'json',
                delay: 250,
                data: function (params) {
                    return {
                        term: params.term,
                        page: params.page,
                        app_label: el.getAttribute('data-app-label'),
                        model_name: el.getAttribute('data-model-name'),
                        field_name: el.getAttribute('data-field-name'),
                        event: eventVal()
                    };
                },
                processResults: function (data, params) {
                    params.page = params.page || 1;
                    return {
                        results: data.results,
                        pagination: { more: (data.pagination || {}).more || false }
                    };
                },
                cache: true
            },
            theme: 'admin-autocomplete',
            allowClear: el.getAttribute('data-allow-clear') === 'true',
            placeholder: el.getAttribute('data-placeholder') || '',
            width: '100%',
            minimumInputLength: 0
        });
    }

    function rebindAll() {
        FISSI.forEach(function (sel) {
            const $el = $(sel);
            if ($el.length && $el[0].getAttribute('data-ajax--url')) { rebind($el); }
        });
        $('select[name$="-service"]').each(function () {
            if (this.getAttribute('data-ajax--url')) { rebind($(this)); }
        });
    }

    function svuotaDipendenti() {
        FISSI.forEach(function (sel) {
            const $el = $(sel);
            if ($el.length) { $el.val(null).trigger('change'); }
        });
        $('select[name$="-service"]').each(function () {
            $(this).val(null).trigger('change');
        });
    }

    $(function () {
        try { rebindAll(); } catch (e) { /* non bloccare il form */ }
        $(EVENT).on('change', svuotaDipendenti);
        $(document).on('formset:added', function () {
            try { rebindAll(); } catch (e) {}
        });
    });
}

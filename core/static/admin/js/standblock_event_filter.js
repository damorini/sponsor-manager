'use strict';
// Form Blocco stand: scegliendo l'evento, la casella "Stand del blocco"
// (FilteredSelectMultiple) mostra solo gli stand di quel congresso.
// Sfrutta il filtro testuale integrato di Django: l'etichetta di ogni stand
// contiene il nome dell'evento, quindi basta impostare il testo del filtro.
(function () {
    function eventText(ev) {
        if (!ev || !ev.value) return '';
        try { return (ev.options[ev.selectedIndex].text || '').trim(); }
        catch (e) { return ''; }
    }
    function applyFilter(ev, input) {
        input.value = eventText(ev);
        // Django lega il filtro all'evento 'keyup' del campo input.
        input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    function start() {
        var ev = document.getElementById('id_event');
        var input = document.getElementById('id_stands_input');
        // La casella viene costruita da SelectFilter dopo il load: riprova.
        if (!ev || !input) { return false; }
        ev.addEventListener('change', function () { applyFilter(ev, input); });
        if (ev.value) { applyFilter(ev, input); }
        return true;
    }
    function init() {
        if (start()) return;
        var tries = 0;
        var t = setInterval(function () {
            tries += 1;
            if (start() || tries > 40) { clearInterval(t); }
        }, 150);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }
})();

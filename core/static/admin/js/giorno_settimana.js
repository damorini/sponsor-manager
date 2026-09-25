/* Allestimento/disallestimento: aggiorna il "Giorno della settimana" della
   riga appena si sceglie la data (senza aspettare il salvataggio). */
(function () {
  var GIORNI = ['Domenica', 'Lunedì', 'Martedì', 'Mercoledì', 'Giovedì',
                'Venerdì', 'Sabato'];
  function giorno(valore) {
    var m = (valore || '').trim().match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})$/);
    var d;
    if (m) { d = new Date(+m[3], +m[2] - 1, +m[1]); }
    else if (/^\d{4}-\d{2}-\d{2}$/.test(valore)) { d = new Date(valore + 'T00:00'); }
    return d && !isNaN(d) ? GIORNI[d.getDay()] : '-';
  }
  function aggiorna(input) {
    var riga = input.closest('tr');
    if (!riga) { return; }
    var cella = riga.querySelector('td.field-giorno p, td.field-giorno');
    if (cella) { cella.textContent = giorno(input.value); }
  }
  document.addEventListener('change', function (e) {
    if (e.target.matches && e.target.matches('input[name^="setup_days-"][name$="-date"]')) {
      aggiorna(e.target);
    }
  });
  /* il calendarietto dell'admin non genera 'change': controllo periodico leggero */
  setInterval(function () {
    document.querySelectorAll('input[name^="setup_days-"][name$="-date"]').forEach(function (i) {
      if (i.dataset.ultimo !== i.value) { i.dataset.ultimo = i.value; aggiorna(i); }
    });
  }, 700);
})();

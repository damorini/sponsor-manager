"""Importa o aggiorna Contatti da un file Excel o CSV.

NON ha regole proprie: legge, analizza e scrive con lo stesso codice della
pagina "Importa rubrica" (sponsors/rubrica_import.py). Prima c'erano due
import con regole diverse — questo scriveva subito e pretendeva che
l'azienda esistesse, la pagina mostrava l'anteprima e creava l'azienda
mancante — e lo stesso file si comportava in due modi secondo da dove lo
caricavi. Chi tocca le regole deve toccare un solo posto.

Per l'uso normale conviene la pagina, che mostra l'anteprima riga per riga
e fa confermare. Questo comando serve per i file grossi e per i lanci da
terminale.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from sponsors.rubrica_import import analizza, applica, leggi_file

SIMBOLO = {'nuovo': '+', 'aggiorna': '~', 'errore': '!'}


class Command(BaseCommand):
    help = ("Importa o aggiorna Contatti da Excel/CSV con le stesse regole "
            "della pagina Importa rubrica (vedi template_contatti.xlsx).")

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True,
                            help="Percorso del file .xlsx o .csv.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Mostra cosa farebbe, senza scrivere nulla.")

    def handle(self, *args, **opts):
        percorso = Path(opts["file"]).expanduser()
        if not percorso.exists():
            raise CommandError(f"File non trovato: {percorso}")

        dry = opts["dry_run"]
        self.stdout.write(f"Lettura {percorso.name}"
                          + (" [ANTEPRIMA: non scrive]" if dry else ""))
        try:
            with open(percorso, "rb") as f:
                righe = leggi_file(f)
        except ValueError as e:
            # leggi_file alza ValueError con un messaggio gia' leggibile
            raise CommandError(str(e))

        analisi = analizza(righe)
        for r in analisi:
            segno = SIMBOLO.get(r.esito, '?')
            testo = f"  {r.numero:>4}: {segno} {r.cognome} {r.nome} <{r.email}>"
            if r.azienda:
                testo += f" @ {r.azienda}"
            if r.nuova_azienda:
                testo += " [azienda nuova]"
            riga_stile = self.style.ERROR if r.esito == 'errore' else None
            self.stdout.write(riga_stile(testo) if riga_stile else testo)
            for m in r.messaggi:
                self.stdout.write(f"        {m}")

        nuovi = sum(1 for r in analisi if r.esito == 'nuovo')
        aggiorna = sum(1 for r in analisi if r.esito == 'aggiorna')
        errori = sum(1 for r in analisi if r.esito == 'errore')

        if dry:
            self.stdout.write("")
            riepilogo = (f"[ANTEPRIMA] {nuovi} da creare, {aggiorna} da "
                         f"aggiornare, {errori} scartate. Nulla e' stato scritto.")
            self.stdout.write(self.style.WARNING(riepilogo)
                              if errori else self.style.SUCCESS(riepilogo))
            return

        esito = applica(righe)
        self.stdout.write("")
        riepilogo = (f"Fatto: {esito['creati']} creati, "
                     f"{esito['aggiornati']} aggiornati, "
                     f"{esito['aziende_create']} aziende create, "
                     f"{esito['scartati']} scartate.")
        self.stdout.write(self.style.WARNING(riepilogo)
                          if esito['scartati'] else self.style.SUCCESS(riepilogo))

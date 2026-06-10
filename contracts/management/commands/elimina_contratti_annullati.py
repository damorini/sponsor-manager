"""
Rimuove dalle liste i contratti ANNULLATI (status=cancelled).

Sicuro per default:
  - senza argomenti: ANTEPRIMA (non tocca nulla), elenca cosa verrebbe rimosso;
  - con --conferma: soft-delete (spariscono dalle liste ma sono RECUPERABILI
    con Contract.all_objects + .restore());
  - con --conferma --hard: cancellazione DEFINITIVA dal database.

Esempi:
    docker compose exec web python manage.py elimina_contratti_annullati
    docker compose exec web python manage.py elimina_contratti_annullati --conferma
    docker compose exec web python manage.py elimina_contratti_annullati --conferma --hard
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rimuove i contratti annullati (anteprima di default; --conferma per agire)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--conferma', action='store_true',
            help='Esegue davvero la rimozione (senza, è solo anteprima).')
        parser.add_argument(
            '--hard', action='store_true',
            help='Con --conferma: cancellazione DEFINITIVA (non recuperabile).')

    def handle(self, *args, **opts):
        from contracts.models import Contract, ContractStatus
        w = self.stdout.write

        qs = (Contract.objects
              .filter(status=ContractStatus.CANCELLED)
              .select_related('sponsor', 'event')
              .order_by('event__start_date', 'contract_number'))

        totale = qs.count()
        if not totale:
            w(self.style.SUCCESS('Nessun contratto annullato da rimuovere.'))
            return

        w(f'Contratti ANNULLATI trovati: {totale}')
        for c in qs:
            sp = c.sponsor.legal_name if c.sponsor_id else '(senza cliente)'
            try:
                ev = c.event.get_name() if c.event_id else '—'
            except Exception:
                ev = str(c.event) if c.event_id else '—'
            w(f'  - {c.contract_number} | {sp} | {ev}')

        if not opts['conferma']:
            w('')
            w(self.style.WARNING(
                'ANTEPRIMA: non ho rimosso nulla. Per procedere DAVVERO:'))
            w('  • reversibile (consigliato): aggiungi  --conferma')
            w('  • definitivo:                aggiungi  --conferma --hard')
            return

        hard = opts['hard']
        rimossi = errori = 0
        for c in list(qs):
            try:
                c.delete(hard=True) if hard else c.delete()
                rimossi += 1
            except Exception as e:
                errori += 1
                w(self.style.ERROR(f'  Errore su {c.contract_number}: {e}'))

        modo = 'cancellati DEFINITIVAMENTE' if hard else 'rimossi dalle liste (recuperabili)'
        w('')
        w(self.style.SUCCESS(f'{rimossi} contratti {modo}.'))
        if errori:
            w(self.style.ERROR(f'{errori} non rimossi per errori (vedi sopra).'))
        if not hard:
            w('Per recuperarne uno: Contract.all_objects.get(contract_number=...)'
              '.restore()')

"""
Diagnostica perché un servizio non genera scadenze (Deadline) alla firma.

Uso:
    python manage.py diagnosi_scadenze "EXPERT MEETING"

Stampa, per ogni Service che corrisponde al nome:
  - triggers_deadlines (la spunta "Genera scadenze")
  - i DeadlineTemplate associati (e se sono attivi)
  - i contratti che vendono quel servizio, il loro stato, e le Deadline esistenti
e prova a spiegare il motivo se la scadenza non risulta creata.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Diagnostica la generazione scadenze per un servizio (per nome)."

    def add_arguments(self, parser):
        parser.add_argument('nome', help='Pezzo del nome del servizio, es. "EXPERT MEETING"')

    def handle(self, *args, **opts):
        from catalog.models import Service
        from contracts.models import ContractStatus

        nome = opts['nome']
        w = self.stdout.write

        # Service (per-evento) è il modello a cui sono legate le scadenze.
        services = list(Service.objects.filter(name__icontains=nome))
        # name è un JSONField {it, en}: filtra anche lato Python per sicurezza.
        if not services:
            services = [
                s for s in Service.objects.all()
                if nome.lower() in str(s.name).lower()
            ]

        if not services:
            w(self.style.ERROR(
                f'Nessun Service (per-evento) col nome contenente "{nome}".'))
            w('  -> Forse l\'hai creato solo nel CATALOGO madre (CatalogService) '
              'e non come servizio dell\'evento. Le scadenze si configurano sul '
              'servizio DELL\'EVENTO (menu "Servizi"), non sulla voce di catalogo.')
            return

        for s in services:
            w('=' * 70)
            w(f'SERVICE  id={s.id}')
            w(f'  nome           : {s.name}')
            ev = getattr(s, 'event', None)
            w(f'  evento         : {ev}  (start_date={getattr(ev, "start_date", None)})')
            w(f'  triggers_deadlines (spunta "Genera scadenze") : {s.triggers_deadlines}')
            tpls = list(s.deadline_templates.all())
            w(f'  DeadlineTemplate associati : {len(tpls)}')
            for t in tpls:
                w(f'      - id={t.id} tipo={t.deadline_type!r} titolo={t.title!r} '
                  f'attivo={t.is_active} days_before_event={t.days_before_event} '
                  f'kind={getattr(t, "submission_kind", "?")}')

            # Diagnosi configurazione
            if not s.triggers_deadlines:
                w(self.style.WARNING(
                    '  ⚠ CAUSA PROBABILE: "Genera scadenze" è DISATTIVATO sul servizio. '
                    'Senza questa spunta, _generate_deadlines salta il servizio.'))
            if not tpls:
                w(self.style.WARNING(
                    '  ⚠ Nessun DeadlineTemplate: niente da generare.'))
            elif not any(t.is_active for t in tpls):
                w(self.style.WARNING(
                    '  ⚠ I template esistono ma sono tutti is_active=False: '
                    'vengono ignorati.'))

            # Contratti che vendono questo servizio
            lines = s.contract_lines.select_related('contract', 'contract__sponsor').all()
            w(f'  Contratti che vendono questo servizio : {lines.count()}')
            for ln in lines:
                c = ln.contract
                dls = list(c.deadlines.filter(contract_line=ln))
                w(f'      contratto {c.contract_number} '
                  f'[{c.get_status_display()}] sponsor={c.sponsor} '
                  f'-> Deadline su questa riga: {len(dls)}')
                for d in dls:
                    w(f'           · {d.deadline_type!r} {d.title!r} stato={d.status} due={d.due_date}')
                if c.status not in [ContractStatus.SIGNED, ContractStatus.ACTIVE,
                                    ContractStatus.COMPLETED] and not dls:
                    w(self.style.WARNING(
                        f'        ⚠ Il contratto NON è firmato (stato={c.get_status_display()}): '
                        'le scadenze si generano solo alla FIRMA (mark_as_signed), '
                        'non alla semplice prenotazione/attesa pagamento.'))

        w('=' * 70)
        w('Fine diagnosi. Se "Genera scadenze"=True, c\'è almeno un template '
          'attivo, e il contratto è FIRMATO ma non ci sono Deadline, mandami '
          'questo output: indica un bug da indagare.')

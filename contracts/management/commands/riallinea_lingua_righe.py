"""
Riallinea gli snapshot delle righe (nome/descrizione servizio, etichetta
stand) alla LINGUA del contratto, per i preventivi NON confermati
(DRAFT / SENT / PENDING_PAYMENT).

Serve a riparare i preventivi creati quando lo snapshot veniva salvato
nella lingua dell'operatore (italiano) invece che in quella del contratto.
I nomi personalizzati a mano non vengono toccati; i contratti firmati
non vengono toccati.

Uso:
    python manage.py riallinea_lingua_righe --dry-run   # solo report
    python manage.py riallinea_lingua_righe             # applica
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Ri-traduce gli snapshot delle righe dei preventivi non "
            "confermati nella lingua del contratto")

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Mostra i cambi senza scrivere nulla')

    def handle(self, *args, **options):
        from contracts.models import Contract, ContractStatus

        dry = options['dry_run']
        contratti = (Contract.objects.filter(status__in=[
            ContractStatus.DRAFT, ContractStatus.SENT,
            ContractStatus.PENDING_PAYMENT,
        ]).select_related('event', 'sponsor').order_by('contract_number'))

        tot_cambi = 0
        for c in contratti:
            cambi = c._riallinea_snapshot_lingua(apply=not dry)
            if not cambi:
                continue
            tot_cambi += len(cambi)
            self.stdout.write(self.style.WARNING(
                f"{c.contract_number} [{c.language}] {c.sponsor.legal_name}:"))
            for _pk, campo, vecchio, nuovo in cambi:
                self.stdout.write(f"  {campo}: {vecchio!r} -> {nuovo!r}")

        esito = 'da applicare (dry-run)' if dry else 'applicati'
        self.stdout.write(self.style.SUCCESS(
            f"{tot_cambi} cambi {esito} su {contratti.count()} preventivi esaminati."))

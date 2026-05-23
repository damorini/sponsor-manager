"""
Ripara i service_name_snapshot / service_description_snapshot corrotti
nelle ContractLine.

Il bug in cart.py salvava il dizionario delle traduzioni grezzo
(es. "{'en': 'LED Spotlight'}") invece della stringa tradotta.
Questo comando individua quei valori e li sostituisce con la stringa
corretta, presa dal Service collegato tramite translated().

USO:
  python manage.py fix_snapshot_json --dry-run   # mostra cosa farebbe
  python manage.py fix_snapshot_json             # applica le correzioni
"""

import ast
from django.core.management.base import BaseCommand
from django.db import transaction

from contracts.models import ContractLine


def looks_corrupted(value):
    """
    True se la stringa sembra un dict Python serializzato
    (es. "{'en': '...'}") invece di un nome normale.
    """
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    return s.startswith("{") and s.endswith("}") and ("'" in s or '"' in s)


def extract_clean(value, fallback=""):
    """
    Prova a interpretare la stringa corrotta come dict e ne estrae
    una traduzione sensata (it -> en -> prima disponibile).
    Se fallisce, ritorna il fallback.
    """
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return fallback
    if not isinstance(parsed, dict) or not parsed:
        return fallback
    for lang in ('it', 'en'):
        if parsed.get(lang):
            return parsed[lang]
    return next(iter(parsed.values()), fallback)


class Command(BaseCommand):
    help = "Ripara gli snapshot JSON corrotti nelle ContractLine."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Mostra le modifiche senza salvarle.",
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        righe = ContractLine.objects.select_related('service').all()

        da_correggere = []
        for line in righe:
            nome_corrotto = looks_corrupted(line.service_name_snapshot)
            desc_corrotta = looks_corrupted(line.service_description_snapshot)
            if nome_corrotto or desc_corrotta:
                da_correggere.append((line, nome_corrotto, desc_corrotta))

        if not da_correggere:
            self.stdout.write(self.style.SUCCESS(
                "Nessuno snapshot corrotto trovato. Tutto a posto."
            ))
            return

        self.stdout.write(
            f"Trovate {len(da_correggere)} righe con snapshot corrotti.\n"
        )

        for line, nome_corrotto, desc_corrotta in da_correggere:
            self.stdout.write(f"  ContractLine id={line.pk} (contratto {line.contract_id})")

            if nome_corrotto:
                # Preferisci il dato vivo dal Service; se manca, estrai dalla stringa
                if line.service_id:
                    nuovo = line.service.translated('name') or extract_clean(line.service_name_snapshot)
                else:
                    nuovo = extract_clean(line.service_name_snapshot)
                self.stdout.write(
                    f"    nome:  {line.service_name_snapshot!r}  ->  {nuovo!r}"
                )
                line.service_name_snapshot = nuovo

            if desc_corrotta:
                if line.service_id:
                    nuova = line.service.translated('description') or extract_clean(line.service_description_snapshot)
                else:
                    nuova = extract_clean(line.service_description_snapshot)
                self.stdout.write(
                    f"    desc:  {line.service_description_snapshot!r}  ->  {nuova!r}"
                )
                line.service_description_snapshot = nuova

        if dry:
            self.stdout.write(self.style.WARNING(
                "\n[DRY-RUN] Nessuna modifica salvata. "
                "Rilancia senza --dry-run per applicare."
            ))
            return

        # Salvataggio: usa update() mirato per NON ri-triggerare la logica
        # di save() (che ricalcolerebbe i totali inutilmente).
        with transaction.atomic():
            for line, _, _ in da_correggere:
                ContractLine.objects.filter(pk=line.pk).update(
                    service_name_snapshot=line.service_name_snapshot,
                    service_description_snapshot=line.service_description_snapshot,
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nCorrette {len(da_correggere)} righe. Fatto."
        ))

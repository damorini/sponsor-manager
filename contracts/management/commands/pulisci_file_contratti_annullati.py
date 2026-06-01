# -*- coding: utf-8 -*-
"""Comando una-tantum: rimuove (soft-delete) i file inviati dal cliente per le
scadenze dei contratti ANNULLATI. Utile per ripulire i contratti gia annullati
prima dell'introduzione della cancellazione automatica. Rilanciabile senza danni."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from contracts.models import Contract, Deadline, ContractStatus
from shared.models import Document


class Command(BaseCommand):
    help = "Rimuove i file inviati per le scadenze dei contratti annullati."

    def handle(self, *args, **options):
        dl_ct = ContentType.objects.get_for_model(Deadline)
        annullati = Contract.objects.filter(status=ContractStatus.CANCELLED)
        tot_file = 0
        tot_contratti = 0
        for c in annullati:
            ids = list(c.deadlines.values_list("id", flat=True))
            if not ids:
                continue
            n = Document.objects.filter(
                content_type=dl_ct, object_id__in=ids, deleted_at__isnull=True,
            ).update(deleted_at=timezone.now())
            if n:
                tot_file += n
                tot_contratti += 1
        self.stdout.write(self.style.SUCCESS(
            "Contratti annullati ripuliti: %d - file rimossi: %d" % (tot_contratti, tot_file)
        ))

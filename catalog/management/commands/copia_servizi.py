"""Copia i servizi (e i loro DeadlineTemplate) da un evento a un altro."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Service, DeadlineTemplate
from events.models import Event


def _trova_evento(rif):
    """Trova un evento per slug, id o nome (parziale)."""
    ev = Event.objects.filter(slug=rif).first()
    if ev:
        return ev
    if str(rif).isdigit():
        ev = Event.objects.filter(pk=int(rif)).first()
        if ev:
            return ev
    ev = Event.objects.filter(slug__icontains=rif).first()
    if ev:
        return ev
    return None


class Command(BaseCommand):
    help = "Copia tutti i servizi (e i DeadlineTemplate) da un evento a un altro."

    def add_arguments(self, parser):
        parser.add_argument('--da', required=True, help="Evento sorgente (slug, id o parte dello slug)")
        parser.add_argument('--a', required=True, help="Evento destinazione (slug, id o parte dello slug)")
        parser.add_argument('--dry-run', action='store_true',
                            help="Mostra cosa farebbe senza salvare nulla")

    def handle(self, *args, **opts):
        sorgente = _trova_evento(opts['da'])
        destinazione = _trova_evento(opts['a'])
        if not sorgente:
            raise CommandError(f"Evento sorgente non trovato: {opts['da']!r}")
        if not destinazione:
            raise CommandError(f"Evento destinazione non trovato: {opts['a']!r}")
        if sorgente.pk == destinazione.pk:
            raise CommandError("Sorgente e destinazione sono lo stesso evento.")

        dry = opts['dry_run']
        self.stdout.write(f"Copia servizi da '{sorgente.slug}' a '{destinazione.slug}'"
                          + (" [DRY-RUN]" if dry else ""))

        servizi = list(Service.objects.filter(event=sorgente).order_by('display_order', 'code'))
        if not servizi:
            self.stdout.write(self.style.WARNING("Nessun servizio nell'evento sorgente."))
            return

        codici_dest = set(Service.objects.filter(event=destinazione).values_list('code', flat=True))

        copiati = 0
        saltati = 0
        dl_copiati = 0

        for s in servizi:
            if s.code in codici_dest:
                self.stdout.write(f"  - salto '{s.code}' (gia' presente nel destinatario)")
                saltati += 1
                continue

            self.stdout.write(f"  + copio '{s.code}'")
            copiati += 1
            if dry:
                # conta i deadline template che copierebbe
                dl_copiati += DeadlineTemplate.objects.filter(service=s).count()
                continue

            with transaction.atomic():
                nuovo = Service(
                    event=destinazione,
                    code=s.code,
                    name=s.name,
                    description=s.description,
                    category=s.category,
                    accounting_category=s.accounting_category,
                    pricing_mode=s.pricing_mode,
                    base_price=s.base_price,
                    pricing_tiers=s.pricing_tiers,
                    is_active=s.is_active,
                    max_quantity=s.max_quantity,
                    total_available=s.total_available,
                    triggers_deadlines=s.triggers_deadlines,
                    is_self_purchasable=s.is_self_purchasable,
                    self_purchase_cutoff_days=s.self_purchase_cutoff_days,
                    vat_rate=s.vat_rate,
                    vat_exemption_article=s.vat_exemption_article,
                    display_order=s.display_order,
                )
                nuovo.save()

                # copia i DeadlineTemplate collegati
                for dt in DeadlineTemplate.objects.filter(service=s):
                    DeadlineTemplate.objects.create(
                        service=nuovo,
                        deadline_type=dt.deadline_type,
                        title=dt.title,
                        description=dt.description,
                        days_before_event=dt.days_before_event,
                        notify_roles=dt.notify_roles,
                        reminder_days_before=dt.reminder_days_before,
                        is_active=dt.is_active,
                        display_order=dt.display_order,
                    )
                    dl_copiati += 1

        msg = (f"Fatto: {copiati} servizi copiati, {saltati} saltati, "
               f"{dl_copiati} deadline template copiati.")
        if dry:
            msg = "[DRY-RUN] " + msg + " (nessun salvataggio)"
        self.stdout.write(self.style.SUCCESS(msg))
        if not dry and copiati:
            self.stdout.write(self.style.WARNING(
                "Ricorda: i PREZZI sono per-evento. Controlla/aggiorna i base_price "
                "dei servizi copiati nel nuovo evento."))

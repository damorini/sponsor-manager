"""
Management command per invitare contatti al portale.

Uso:
    # Invita un singolo contact per ID
    python manage.py invite_sponsor --contact-id <uuid>
    
    # Invita tutti i contatti is_primary di uno sponsor
    python manage.py invite_sponsor --sponsor-id <uuid>
    
    # Dry-run (mostra cosa farebbe senza eseguire)
    python manage.py invite_sponsor --sponsor-id <uuid> --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from portal.services.invitation import invite_contact_to_portal
from sponsors.models import Contact, Sponsor


class Command(BaseCommand):
    help = "Invita uno o più contatti al portale sponsor."

    def add_arguments(self, parser):
        parser.add_argument(
            '--contact-id', type=str,
            help='UUID di un singolo Contact da invitare',
        )
        parser.add_argument(
            '--sponsor-id', type=str,
            help='UUID di uno Sponsor: invita tutti i suoi contatti is_primary',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Mostra cosa farebbe senza eseguire',
        )
        parser.add_argument(
            '--no-email', action='store_true',
            help='Non manda email (solo crea User)',
        )

    def handle(self, *args, **options):
        contact_id = options.get('contact_id')
        sponsor_id = options.get('sponsor_id')
        dry_run = options.get('dry_run', False)
        no_email = options.get('no_email', False)

        if not contact_id and not sponsor_id:
            raise CommandError("Specifica --contact-id o --sponsor-id")

        # Determina contatti da invitare
        if contact_id:
            try:
                contacts = [Contact.objects.get(id=contact_id)]
            except Contact.DoesNotExist:
                raise CommandError(f"Contact {contact_id} non trovato")
        else:
            try:
                sponsor = Sponsor.objects.get(id=sponsor_id)
            except Sponsor.DoesNotExist:
                raise CommandError(f"Sponsor {sponsor_id} non trovato")
            contacts = sponsor.contacts.filter(is_primary=True, email__gt='')

        if not contacts:
            self.stdout.write(self.style.WARNING(
                "Nessun contact da invitare (verifica is_primary e email)"
            ))
            return

        # Esegui
        for contact in contacts:
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Inviterei: {contact.full_name} ({contact.email}) "
                    f"di {contact.sponsor.legal_name}"
                )
                continue

            try:
                user, temp_password, was_created = invite_contact_to_portal(
                    contact, send_email=not no_email,
                )
                action = "creato" if was_created else "aggiornato"
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Account {action}: {contact.email}"
                ))
                if no_email:
                    # Stampa la password se non si è mandata l'email
                    self.stdout.write(f"  Password temp: {temp_password}")
                else:
                    self.stdout.write(f"  Email inviata a {contact.email}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"✗ Errore per {contact.email}: {e}"
                ))

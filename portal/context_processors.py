"""
Context processor: aggiunge variabili globali a tutti i template del portale.

Da registrare in TEMPLATES → context_processors:
    'portal.context_processors.branding',
"""
from django.conf import settings


def branding(request):
    """Aggiunge variabili di branding e supporto a ogni template."""
    return {
        'organizer_name': getattr(
            settings, 'ORGANIZER_DISPLAY_NAME',
            getattr(settings, 'DEFAULT_ORGANIZER_LEGAL_NAME', 'Sponsor Manager')
        ),
        'organizer_address': getattr(settings, 'ORGANIZER_ADDRESS', ''),
        'support_email': getattr(settings, 'SUPPORT_EMAIL', ''),
        'brand_logo_url': getattr(settings, 'BRAND_LOGO_URL', ''),
        'brand_primary_color': getattr(settings, 'BRAND_PRIMARY_COLOR', '#1d6534'),
        'bank_holder': getattr(settings, 'BANK_TRANSFER_HOLDER', ''),
        'bank_name': getattr(settings, 'BANK_TRANSFER_BANK', ''),
        'bank_iban': getattr(settings, 'BANK_TRANSFER_IBAN', ''),
        'bank_bic': getattr(settings, 'BANK_TRANSFER_BIC', ''),
    }


def _active_contact(request):
    """Contatto dell'AZIENDA ATTIVA (rispetta la scelta multi-azienda in sessione)."""
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'is_sponsor', False):
            from portal.views.dashboard import get_active_contact
            return get_active_contact(request)
    except Exception:
        pass
    return None


def cart_count(request):
    """Numero di articoli nel carrello (righe dei contratti ADDON draft del cliente)."""
    contact = _active_contact(request)
    sponsor = getattr(contact, 'sponsor', None) if contact else None

    count = 0
    try:
        if sponsor:
            from contracts.models import Contract, ContractKind, ContractStatus
            carts = Contract.objects.filter(
                sponsor=sponsor,
                contract_kind=ContractKind.ADDON,
                status=ContractStatus.DRAFT,
            )
            for c in carts:
                count += c.lines.count()
    except Exception:
        count = 0

    # Servizi acquistabili: serve per mostrare "Acquista servizi" nel menu
    # su TUTTE le pagine del portale (prima era calcolato solo in dashboard).
    has_purchasable = False
    try:
        if sponsor:
            from contracts.models import Contract
            from catalog.models import Service
            from events.models import EventStatus
            eventi_ids = list(
                Contract.objects.filter(sponsor=sponsor)
                .exclude(event__status=EventStatus.ARCHIVED)
                .values_list('event_id', flat=True)
            )
            has_purchasable = Service.objects.filter(
                event_id__in=eventi_ids,
                is_active=True,
                is_self_purchasable=True,
            ).exists()
    except Exception:
        has_purchasable = False

    # Messaggi portale non letti (per il badge nel menu)
    unread_messages = 0
    try:
        if sponsor:
            from sponsors.models import PortalMessage, MessageSender
            unread_messages = PortalMessage.objects.filter(
                sponsor=sponsor, is_active=True, read_at__isnull=True,
                sender=MessageSender.OPERATOR, archived_at__isnull=True,
            ).count()
    except Exception:
        unread_messages = 0

    # Anagrafica incompleta: promemoria persistente (banner in base.html).
    anagrafica_da_completare = []
    try:
        if sponsor:
            anagrafica_da_completare = sponsor.campi_anagrafica_mancanti()
    except Exception:
        anagrafica_da_completare = []

    # Multi-azienda: quante aziende gestisce questo login (per 'Cambia azienda' nel menu)
    aziende_count = 0
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'is_sponsor', False):
            from portal.views.dashboard import user_contacts_qs
            aziende_count = user_contacts_qs(user).count()
    except Exception:
        aziende_count = 0

    return {
        'cart_count': count,
        'has_purchasable_services': has_purchasable,
        'unread_messages': unread_messages,
        'anagrafica_da_completare': anagrafica_da_completare,
        'aziende_count': aziende_count,
        # Contatto/sponsor dell'azienda ATTIVA (multi-azienda): da usare nei
        # template al posto di user.contact_profile (che è solo il primo contatto).
        'active_contact': contact,
        'active_sponsor': sponsor,
    }

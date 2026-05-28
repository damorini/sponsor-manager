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
        'brand_primary_color': getattr(settings, 'BRAND_PRIMARY_COLOR', '#1f4e79'),
    }


def cart_count(request):
    """Numero di articoli nel carrello (righe dei contratti ADDON draft del cliente)."""
    count = 0
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            contact = getattr(user, 'contact_profile', None)
            sponsor = getattr(contact, 'sponsor', None) if contact else None
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
    return {'cart_count': count}

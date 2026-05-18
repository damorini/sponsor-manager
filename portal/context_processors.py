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

"""
Footer email: logo (fallback al brand statico se non caricato), indirizzo
compattato su una riga, email di contatto = primo indirizzo della segreteria.
"""
import pytest

from contracts.services.email_sender import build_common_context


@pytest.mark.django_db
def test_footer_context(settings):
    from core.models import OrganizerSettings
    o = OrganizerSettings.load()
    o.name = 'VALET CONFERENCE'
    o.address = 'Valet Srl\r\nVia Dei Fornaciai, 29/b\r\n40129 Bologna  |  ITALY'
    o.email = 'congresso@valet.it; comunicazione@valet.it'
    o.website = 'www.valet.it'
    o.logo = None
    o.save()
    settings.SITE_URL = 'https://x.it'

    ctx = build_common_context()

    # Logo: fallback al brand statico (nessun upload in OrganizerSettings)
    assert ctx['org_logo_url'].startswith('https://x.it')
    assert ctx['org_logo_url'].endswith('branding/valet_logo.png')
    # Indirizzo su UNA riga, niente a-capo, whitespace normalizzato
    compact = ctx['org_address_compact']
    assert '\n' not in compact and '\r' not in compact
    assert 'Via Dei Fornaciai, 29/b · 40129 Bologna | ITALY' in compact
    # Email di contatto = PRIMO indirizzo (congresso), mai info
    assert ctx['support_email'] == 'congresso@valet.it'
    assert ctx['org_email'] == 'congresso@valet.it'

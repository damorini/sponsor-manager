"""
Navigazione portale cliente:
- la card evento nella dashboard porta a "I miei documenti" (portal:contracts_list),
  non alla pagina servizi dell'evento;
- la pagina servizi dell'evento espone comunque un link diretto "I miei documenti →".
"""
import re
import pytest
from decimal import Decimal
from datetime import date

from django.urls import reverse
from django.utils import timezone


def _setup_sponsor_with_event(name_it='NavTest Congresso'):
    from django.contrib.auth import get_user_model
    from core.models import OrganizerSettings
    from sponsors.models import Sponsor, Contact, ContactRole
    from users.models import UserRole
    from events.models import Event
    from contracts.models import Contract, ContractStatus, ContractKind

    User = get_user_model()
    user = User.objects.create_user(
        username='nav_sp', email='nav@test.it', password='x', is_active=True)
    user.role = UserRole.SPONSOR
    user.save()
    sponsor = Sponsor.objects.create(
        legal_name='Nav Sponsor S.r.l.', vat_number='12345678901',
        sdi_code='ABCDEFG', pec_email='pec@pec.it', address_street='Via Test 1',
        address_city='Bologna', address_zip='40100', address_province='BO',
        address_country='IT', website='https://x.it', business_description='Test',
    )
    ver = OrganizerSettings.load().privacy_policy_version or '1.0'
    Contact.objects.create(
        portal_user=user, sponsor=sponsor, full_name='Nav Contact',
        email='c@test.it', phone='+390000', roles=[ContactRole.OPERATIONAL],
        privacy_accepted_at=timezone.now(), privacy_policy_version=ver)
    event = Event.objects.create(
        name={'it': name_it, 'en': name_it}, code='NAV1',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2))
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='NAV1-26-001',
        total=Decimal('1000.00'), deposit_percent=Decimal('30'))
    return user, sponsor, event, contract


@pytest.mark.django_db
def test_dashboard_event_card_links_to_my_documents(client):
    user, sponsor, event, contract = _setup_sponsor_with_event()
    client.force_login(user)

    resp = client.get(reverse('portal:dashboard'))
    assert resp.status_code == 200
    html = resp.content.decode()

    docs_url = reverse('portal:contracts_list')
    # La card evento e' l'anchor con la classe distintiva "group bg-white rounded-xl".
    m = re.search(r'<a href="([^"]+)"\s+class="group bg-white rounded-xl[^"]*">(.*?)</a>',
                  html, re.S)
    assert m, "card evento non trovata nella dashboard"
    href, inner = m.group(1), m.group(2)
    assert 'NavTest Congresso' in inner, "la card non contiene il nome evento"
    assert href == docs_url, f"la card evento deve puntare a I miei documenti, non a {href}"


@pytest.mark.django_db
def test_event_page_has_direct_my_documents_link(client):
    user, sponsor, event, contract = _setup_sponsor_with_event()
    client.force_login(user)

    resp = client.get(reverse('portal:event_dashboard', args=[event.id]))
    assert resp.status_code == 200
    html = resp.content.decode()
    # Link diretto aggiunto nella barra in alto (versione con freccia, distinta
    # dalla voce di menu "I miei documenti" senza freccia).
    assert 'I miei documenti →' in html
    assert reverse('portal:contracts_list') in html


@pytest.mark.django_db
def test_quote_pdf_footer_has_logo(tmp_path, settings):
    """Senza logo caricato in OrganizerSettings, il footer del preventivo usa il
    logo brand statico (fallback): il PDF deve contenere un'immagine."""
    settings.MEDIA_ROOT = str(tmp_path)
    from core.models import OrganizerSettings
    org = OrganizerSettings.load()
    assert not org.logo, "il test presuppone nessun logo caricato (deve scattare il fallback)"

    user, sponsor, event, contract = _setup_sponsor_with_event(name_it='Logo Ev')
    from contracts.services.pdf_generator import generate_quote_pdf_html
    doc = generate_quote_pdf_html(contract)
    assert doc is not None

    from pathlib import Path
    pdf_path = (Path(settings.MEDIA_ROOT) / 'documents' / 'contracts' / str(contract.id)
                / f"preventivo_{contract.contract_number}_{event.id}.pdf")
    assert pdf_path.exists(), "PDF preventivo non generato"
    data = pdf_path.read_bytes()
    n_img = data.count(b'/Subtype /Image') + data.count(b'/Subtype/Image')
    assert n_img >= 1, "logo mancante nel footer del preventivo (nessuna immagine nel PDF)"

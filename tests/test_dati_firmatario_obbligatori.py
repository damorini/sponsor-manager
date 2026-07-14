"""Regressione: il contratto MAIN non-ECM stampa i dati anagrafici del
firmatario (nato il/a, residenza, documento, CF) - senza, non si genera e
la conferma dal portale viene bloccata con un messaggio chiaro."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from contracts.services.pdf_generator import generate_sponsor_contract_pdf
from events.models import Event, EventType
from sponsors.models import Contact, ContactRole


def _completa_anagrafica(sponsor):
    sponsor.sdi_code = 'ABCDEFG'
    sponsor.pec_email = 'pec@test.it'
    sponsor.address_street = 'Via Roma 1'
    sponsor.address_city = 'Bologna'
    sponsor.address_zip = '40100'
    sponsor.address_province = 'BO'
    sponsor.website = 'https://test.it'
    sponsor.business_description = 'Distributore'
    sponsor.save()


@pytest.fixture
def contratto_firmatario_incompleto(db, user_sponsor, sponsor):
    """Firmatario SENZA i dati anagrafici (solo is_signer=True)."""
    from django.utils import timezone
    from core.models import OrganizerSettings
    _completa_anagrafica(sponsor)
    Contact.objects.create(
        portal_user=user_sponsor, sponsor=sponsor,
        full_name='Mario Rossi', email='mario@test.it',
        roles=[ContactRole.OPERATIONAL], is_signer=True,
        privacy_accepted_at=timezone.now(),
        privacy_policy_version=OrganizerSettings.load().privacy_policy_version or '1.0',
    )
    event = Event.objects.create(
        name={'it': 'Evento Dati Mancanti', 'en': 'Missing Data Event'},
        code='DM', event_type=EventType.NON_ECM,
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.MAIN, status=ContractStatus.SENT,
        contract_number='DM-26-001',
    )
    service = Service.objects.create(
        event=event, code='SRV1', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('100'), vat_rate=Decimal('22'),
    )
    ContractLine.objects.create(
        contract=contract, service=service, quantity=1,
        unit_price=Decimal('100'), vat_rate=Decimal('22'),
    )
    return contract


def test_dati_firmatario_mancanti_elenca_i_campi_vuoti(sponsor):
    c = Contact.objects.create(sponsor=sponsor, full_name='Vuoto', is_signer=True)
    mancanti = c.dati_firmatario_mancanti()
    assert 'Codice Fiscale' in mancanti
    assert 'Data di nascita' in mancanti
    assert len(mancanti) == len(Contact.FIRMATARIO_CAMPI_OBBLIGATORI)


def test_dati_firmatario_completi_nessun_mancante(sponsor, dati_firmatario_completi):
    c = Contact.objects.create(
        sponsor=sponsor, full_name='Completo', is_signer=True,
        **dati_firmatario_completi,
    )
    assert c.dati_firmatario_mancanti() == []


@pytest.mark.django_db
def test_generazione_contratto_bloccata_senza_dati_firmatario(contratto_firmatario_incompleto):
    with pytest.raises(ValueError, match='dati anagrafici'):
        generate_sponsor_contract_pdf(contratto_firmatario_incompleto)


@pytest.mark.django_db
def test_conferma_portale_bloccata_senza_dati_firmatario(client, user_sponsor, contratto_firmatario_incompleto):
    client.force_login(user_sponsor)
    resp = client.post(
        reverse('portal:quote_confirm', args=[contratto_firmatario_incompleto.id]),
        follow=True,
    )
    contratto_firmatario_incompleto.refresh_from_db()
    # bloccato: il contratto NON passa a SIGNED
    assert contratto_firmatario_incompleto.status == ContractStatus.SENT
    testo = resp.content.decode()
    assert 'dati anagrafici' in testo

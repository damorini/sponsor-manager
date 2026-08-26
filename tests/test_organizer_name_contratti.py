"""Ragione sociale organizzatore nei PDF contrattuali.

Il campo Event.organizer_legal_name, se compilato, sostituisce il nome
VALET nei documenti (domanda di ammissione, contratto sponsor); se vuoto
resta la dicitura standard VALET (fallback nel tag Jinja dei template).
"""
from datetime import date
from decimal import Decimal

import pytest

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from contracts.services.pdf_generator import (
    generate_admission_request_pdf,
    generate_sponsor_contract_pdf,
)
from events.models import Event, EventType
from sponsors.models import Contact


def _leggi_pdf(doc):
    from pathlib import Path
    from django.conf import settings
    from pypdf import PdfReader
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1)
    return ' '.join((p.extract_text() or '') for p in
                    PdfReader(str(Path(settings.MEDIA_ROOT) / rel)).pages)


def _contratto(sponsor, dati_firmatario, organizer='', code='ORG', num='ORG-26-001'):
    Contact.objects.create(
        sponsor=sponsor, full_name='Firmatario Org', email=f'firm_{code}@test.it',
        is_signer=True, **dati_firmatario,
    )
    event = Event.objects.create(
        name={'it': f'Ev Organizer {code}', 'en': f'Ev Organizer {code}'},
        code=code, event_type=EventType.NON_ECM,
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
        organizer_legal_name=organizer,
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number=num,
    )
    servizio = Service.objects.create(
        event=event, code='SRV', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('500.00'),
    )
    ContractLine.objects.create(
        contract=contract, service=servizio, quantity=1,
        unit_price=Decimal('500.00'),
    )
    return contract


@pytest.mark.django_db
def test_domanda_campo_vuoto_usa_valet(sponsor, dati_firmatario_completi):
    contract = _contratto(sponsor, dati_firmatario_completi, organizer='',
                          code='ORGV', num='ORGV-26-001')
    doc = generate_admission_request_pdf(contract)
    testo = _leggi_pdf(doc)
    assert 'VALET' in testo


@pytest.mark.django_db
def test_domanda_campo_compilato_sostituisce_valet(sponsor, dati_firmatario_completi):
    contract = _contratto(sponsor, dati_firmatario_completi,
                          organizer='ACME CONGRESSI S.P.A.',
                          code='ORGA', num='ORGA-26-001')
    doc = generate_admission_request_pdf(contract)
    testo = _leggi_pdf(doc)
    assert 'ACME CONGRESSI S.P.A.' in testo
    assert 'VALET Società Responsabilità Limitata' not in testo


@pytest.mark.django_db
def test_contratto_sponsor_usa_organizzatore_evento(sponsor, dati_firmatario_completi):
    contract = _contratto(sponsor, dati_firmatario_completi,
                          organizer='ACME CONGRESSI S.P.A.',
                          code='ORGC', num='ORGC-26-001')
    doc = generate_sponsor_contract_pdf(contract)
    testo = _leggi_pdf(doc)
    assert 'ACME CONGRESSI S.P.A.' in testo

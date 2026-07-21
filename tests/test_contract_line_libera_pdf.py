"""Regressione: il PDF del contratto/domanda si genera correttamente anche
quando il contratto include una riga LIBERA (senza servizio a catalogo) -
non deve andare in errore nel raggruppamento per categoria contabile."""
from datetime import date
from decimal import Decimal

import pytest

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from contracts.services.pdf_generator import generate_admission_request_pdf
from events.models import Event, EventType
from sponsors.models import Contact


@pytest.mark.django_db
def test_pdf_domanda_con_riga_libera(sponsor, dati_firmatario_completi):
    Contact.objects.create(
        sponsor=sponsor, full_name='Firmatario Test', email='firmatario@test.it',
        is_signer=True, **dati_firmatario_completi,
    )
    event = Event.objects.create(
        name={'it': 'Ev Riga Libera PDF', 'en': 'Ev Riga Libera PDF'}, code='RLP',
        event_type=EventType.NON_ECM,
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RLP-26-001',
    )
    servizio = Service.objects.create(
        event=event, code='STAND', name={'it': 'Stand', 'en': 'Stand'},
        base_price=Decimal('500.00'),
    )
    ContractLine.objects.create(
        contract=contract, service=servizio, quantity=1, unit_price=Decimal('500.00'),
    )
    ContractLine.objects.create(
        contract=contract, service=None,
        custom_description='Interprete per conferenza stampa',
        quantity=1, unit_price=Decimal('250.00'),
    )

    doc = generate_admission_request_pdf(contract)
    assert doc is not None
    assert doc.mime_type == 'application/pdf'

    from pypdf import PdfReader
    from pathlib import Path
    from django.conf import settings
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1)
    testo = ' '.join((p.extract_text() or '') for p in
                      PdfReader(str(Path(settings.MEDIA_ROOT) / rel)).pages)
    assert 'Interprete per conferenza stampa' in testo

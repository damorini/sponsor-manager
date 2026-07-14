"""
Generazione del PDF del contratto (docxtpl + LibreOffice).

generate_contract_pdf(contract): rende il template DOCX (ecm/non_ecm, IT/EN) e
lo converte in PDF, registrandolo come Document. Salta i contratti ADDON.
"""
import pytest
from decimal import Decimal
from pathlib import Path
from datetime import date
from django.conf import settings

from sponsors.models import Contact
from events.models import Event
from catalog.models import Service
from contracts.models import Contract, ContractLine, ContractKind, ContractStatus
from contracts.services.pdf_generator import generate_contract_pdf


@pytest.fixture
def signed_contract(db, sponsor, dati_firmatario_completi):
    Contact.objects.create(
        sponsor=sponsor, full_name='Mario Rossi',
        email='mario@test.it', is_signer=True,
        **dati_firmatario_completi,
    )
    event = Event.objects.create(
        name={'it': 'Pdf Event', 'en': 'Pdf Event'},
        code='PDF',
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
    )
    service = Service.objects.create(
        event=event, name={'it': 'Stand', 'en': 'Booth'},
        base_price=Decimal('800.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT,
        contract_number='PDF-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)
    return contract


@pytest.mark.django_db
def test_contract_pdf_generated(signed_contract):
    doc = generate_contract_pdf(signed_contract)

    assert doc is not None
    assert doc.mime_type == 'application/pdf'
    assert doc.file_size_bytes and doc.file_size_bytes > 1000
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
    disk_path = Path(settings.MEDIA_ROOT) / rel
    assert disk_path.exists()
    assert disk_path.read_bytes()[:4] == b'%PDF'


@pytest.mark.django_db
def test_contract_pdf_skipped_for_addon(sponsor):
    event = Event.objects.create(
        name={'it': 'Pdf Event 2', 'en': 'Pdf Event 2'},
        code='PDF2', start_date=date(2026, 11, 1), end_date=date(2026, 11, 2),
    )
    addon = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.ADDON,
        status=ContractStatus.DRAFT,
        contract_number='PDF2-26-001',
    )
    assert generate_contract_pdf(addon) is None

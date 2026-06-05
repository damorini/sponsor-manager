"""
End-to-end del PDF preventivo grafico (HTML -> PDF via WeasyPrint).

contracts/services/pdf_generator.py: generate_quote_pdf_html(contract) rende
il template quote_pdf.html e produce un Document(document_type='quote').
Richiede WeasyPrint (+ librerie di sistema pango/cairo).
"""
import pytest
from decimal import Decimal
from pathlib import Path
from datetime import date
from django.conf import settings

from events.models import Event
from catalog.models import Service
from contracts.models import Contract, ContractLine, ContractKind, ContractStatus
from contracts.services.pdf_generator import generate_quote_pdf_html


@pytest.mark.django_db
def test_generate_quote_pdf_html(sponsor):
    event = Event.objects.create(
        name={'it': 'Q Event', 'en': 'Q Event'},
        code='QP',
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
    )
    service = Service.objects.create(
        event=event,
        name={'it': 'Servizio X', 'en': 'Service X'},
        base_price=Decimal('100.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor,
        event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT,
        contract_number='QP-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)

    doc = generate_quote_pdf_html(contract)

    assert doc.document_type == 'quote'
    assert doc.mime_type == 'application/pdf'
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
    disk_path = Path(settings.MEDIA_ROOT) / rel
    assert disk_path.exists(), f"PDF preventivo mancante: {disk_path}"
    assert disk_path.read_bytes()[:4] == b'%PDF'

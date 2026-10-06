"""Il numero del preventivo compare in alto a destra, sotto l'header."""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from django.conf import settings

from catalog.models import Service
from contracts.models import Contract, ContractLine, ContractKind, ContractStatus
from contracts.services.pdf_generator import generate_quote_pdf_html
from events.models import Event


def _pdf(contract):
    from pypdf import PdfReader
    doc = generate_quote_pdf_html(contract)
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
    reader = PdfReader(str(Path(settings.MEDIA_ROOT) / rel))
    return reader.pages[0].extract_text() or ''


@pytest.mark.django_db
def test_numero_preventivo_in_testa(sponsor):
    event = Event.objects.create(
        name={'it': 'Q Event', 'en': 'Q Event'}, code='QN',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2))
    service = Service.objects.create(
        event=event, name={'it': 'Servizio X', 'en': 'Service X'},
        base_price=Decimal('100.00'))
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='QN-26-007')
    ContractLine.objects.create(contract=contract, service=service, quantity=1)

    testo = _pdf(contract)
    assert 'Preventivo n. QN-26-007' in testo
    # sta in testa, prima dell'introduzione al cliente
    assert testo.index('Preventivo n. QN-26-007') < testo.index('Spett.le')


def test_numero_preventivo_nel_template():
    html = open(Path(settings.BASE_DIR) / 'contracts/templates/quote_pdf.html',
                encoding='utf-8').read()
    barra = html.index('<div class="brandbar"></div>')
    numero = html.index('{{ t.quote_no }} {{ contract.contract_number }}')
    assert barra < numero < html.index('<p class="eyebrow">')

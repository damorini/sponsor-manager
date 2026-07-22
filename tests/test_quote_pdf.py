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


def _testo_pdf(disk_path):
    from pypdf import PdfReader
    return ' '.join((p.extract_text() or '') for p in PdfReader(str(disk_path)).pages)


@pytest.mark.django_db
def test_quote_con_iva_mostra_la_riga_iva(sponsor):
    event = Event.objects.create(
        name={'it': 'Q Event IVA', 'en': 'Q Event VAT'}, code='QPI',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    service = Service.objects.create(
        event=event, name={'it': 'Servizio X', 'en': 'Service X'},
        base_price=Decimal('100.00'), vat_rate=Decimal('22.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='QPI-26-001',
        vat_applicable=True,
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)

    doc = generate_quote_pdf_html(contract)
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
    testo = _testo_pdf(Path(settings.MEDIA_ROOT) / rel)
    assert 'IVA' in testo


@pytest.mark.django_db
def test_quote_senza_iva_non_mostra_la_riga_iva(sponsor):
    """Regressione: se sul contratto l'IVA non e' flaggata (vat_applicable=False),
    il preventivo NON deve mostrare affatto la riga IVA (prima usciva comunque,
    con importo 0 - ora la riga sparisce del tutto)."""
    event = Event.objects.create(
        name={'it': 'Q Event Esente', 'en': 'Q Event Exempt'}, code='QPN',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    service = Service.objects.create(
        event=event, name={'it': 'Servizio Y', 'en': 'Service Y'},
        base_price=Decimal('100.00'), vat_rate=Decimal('22.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='QPN-26-001',
        vat_applicable=False, vat_exemption_reason='Esente art. 10 DPR 633/72',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)
    contract.refresh_from_db()
    assert contract.vat_amount == Decimal('0.00')

    doc = generate_quote_pdf_html(contract)
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
    testo = _testo_pdf(Path(settings.MEDIA_ROOT) / rel)
    # la tabella dei totali va da "Subtotale" a "Totale": non deve contenere
    # "IVA" in mezzo (l'intestazione di colonna "Totale (IVA escl.)" resta,
    # e' un'indicazione generica sui prezzi, non l'importo IVA del preventivo).
    inizio = testo.index('Subtotale')
    fine = testo.index('Totale', inizio)
    tabella_totali = testo[inizio:fine]
    assert 'IVA' not in tabella_totali, tabella_totali

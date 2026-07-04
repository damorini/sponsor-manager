"""
Le fatture proforma generate compaiono in "Export fatture" (InvoiceExport).

- Pagamento unico -> 1 riga export_type=full con importi e link al PDF.
- Acconto+saldo   -> 2 righe (deposit/1 e balance/2).
- Rigenerare la proforma NON duplica le righe (upsert) e non tocca lo
  stato di righe gia' lavorate.
"""
import pytest
from datetime import date
from decimal import Decimal

from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services.pdf_generator import generate_proforma_pdf
from events.models import Event
from shared.models import InvoiceExport, InvoiceExportStatus, InvoiceExportType


@pytest.fixture
def contratto(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Ev Proforma', 'en': 'Ev Proforma'}, code='PRF',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PRF-26-001',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'),
    )


@pytest.mark.django_db
def test_pagamento_unico_crea_riga_export(contratto):
    docs = generate_proforma_pdf(contratto)
    assert len(docs) == 1
    exports = InvoiceExport.objects.filter(contract=contratto)
    assert exports.count() == 1
    ie = exports.get()
    assert ie.export_type == InvoiceExportType.FULL
    assert ie.installment_number is None
    assert ie.amount_subtotal == Decimal('1000.00')
    assert ie.amount_vat == Decimal('220.00')
    assert ie.amount_total == Decimal('1220.00')
    assert ie.export_file_url == docs[0].storage_url
    assert ie.status == InvoiceExportStatus.PENDING_EXPORT


@pytest.mark.django_db
def test_acconto_saldo_crea_due_righe(contratto):
    contratto.deposit_percent = Decimal('30')
    contratto.save(update_fields=['deposit_percent'])
    docs = generate_proforma_pdf(contratto)
    assert len(docs) == 2
    acconto = InvoiceExport.objects.get(
        contract=contratto, export_type=InvoiceExportType.DEPOSIT)
    saldo = InvoiceExport.objects.get(
        contract=contratto, export_type=InvoiceExportType.BALANCE)
    assert acconto.installment_number == 1
    assert saldo.installment_number == 2
    assert acconto.amount_subtotal == Decimal('300.00')
    assert acconto.amount_total == contratto.deposit_amount
    assert saldo.amount_total == contratto.balance_amount


@pytest.mark.django_db
def test_rigenerazione_non_duplica(contratto):
    generate_proforma_pdf(contratto)
    generate_proforma_pdf(contratto)
    assert InvoiceExport.objects.filter(contract=contratto).count() == 1


@pytest.mark.django_db
def test_rigenerazione_non_tocca_stato_lavorato(contratto):
    generate_proforma_pdf(contratto)
    ie = InvoiceExport.objects.get(contract=contratto)
    ie.status = InvoiceExportStatus.INVOICED
    ie.external_invoice_number = 'FT-2026-99'
    ie.save(update_fields=['status', 'external_invoice_number'])
    generate_proforma_pdf(contratto)
    ie.refresh_from_db()
    assert ie.status == InvoiceExportStatus.INVOICED
    assert ie.external_invoice_number == 'FT-2026-99'

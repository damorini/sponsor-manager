"""
InvoiceExport: lo snapshot dati fiscali si compila da solo dallo sponsor del
contratto (prima dava IntegrityError perché era obbligatorio e non valorizzato).
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from contracts.models import Contract, ContractKind, ContractStatus
from shared.models import InvoiceExport


@pytest.fixture
def contratto(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Ev Fattura', 'en': 'Ev Fattura'}, code='INV',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='INV-26-001',
    )


@pytest.mark.django_db
def test_snapshot_si_autocompila(contratto, sponsor):
    ie = InvoiceExport.objects.create(
        contract=contratto,
        amount_subtotal=Decimal('1000.00'),
        amount_vat=Decimal('220.00'),
        amount_total=Decimal('1220.00'),
    )
    ie.refresh_from_db()
    assert ie.fiscal_data_snapshot, "lo snapshot non deve essere vuoto"
    assert ie.fiscal_data_snapshot['legal_name'] == sponsor.legal_name
    assert ie.fiscal_data_snapshot['vat_number'] == sponsor.vat_number


@pytest.mark.django_db
def test_snapshot_esplicito_non_sovrascritto(contratto):
    custom = {'legal_name': 'CONGELATO SPA', 'vat_number': '00000000000'}
    ie = InvoiceExport.objects.create(
        contract=contratto, fiscal_data_snapshot=custom,
        amount_subtotal=Decimal('10.00'), amount_vat=Decimal('0.00'),
        amount_total=Decimal('10.00'),
    )
    ie.refresh_from_db()
    assert ie.fiscal_data_snapshot == custom

"""
Importo acconto manuale (Contract.deposit_amount_override): per i casi in cui
la percentuale a due decimali non arriva al centesimo (es. acconto versato
sull'imponibile: 350 su 2.135 IVA inclusa). Se vuoto vale il calcolo solito.
"""
from datetime import date
from decimal import Decimal

import pytest

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event


@pytest.fixture
def contratto(db, sponsor):
    ev = Event.objects.create(
        name={'it': 'Ev Acc', 'en': 'Ev Acc'}, code='ACC',
        start_date=date(2030, 11, 28), end_date=date(2030, 11, 28))
    c = Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='ACC-26-001',
        deposit_percent=Decimal('20'))
    Contract.objects.filter(pk=c.pk).update(total=Decimal('2135.00'))
    c.refresh_from_db()
    return c


def test_senza_importo_manuale_vale_la_percentuale(contratto):
    assert contratto.deposit_amount == Decimal('427.00')
    assert contratto.balance_amount == Decimal('1708.00')


def test_importo_manuale_vince_sulla_percentuale(contratto):
    contratto.deposit_amount_override = Decimal('350.00')
    contratto.save()
    contratto.refresh_from_db()
    assert contratto.deposit_amount == Decimal('350.00')
    assert contratto.balance_amount == Decimal('1785.00')


def test_senza_percentuale_niente_acconto_anche_con_importo(contratto):
    contratto.deposit_percent = None
    contratto.deposit_amount_override = Decimal('350.00')
    contratto.save()
    assert contratto.deposit_amount == Decimal('0.00')
    assert contratto.balance_amount == Decimal('2135.00')


def test_portale_pagamenti_usa_importo_manuale(contratto):
    from contracts.models import Deadline
    from portal.views.dashboard import build_payment_items
    contratto.deposit_amount_override = Decimal('350.00')
    contratto.save()
    Deadline.objects.create(contract=contratto, deadline_type='pagamento_acconto',
                            title='Acconto', due_date=date(2030, 9, 23))
    Deadline.objects.create(contract=contratto, deadline_type='pagamento_saldo',
                            title='Saldo', due_date=date(2030, 10, 31))
    items, da_pagare = build_payment_items(contratto.sponsor, date(2030, 9, 1))
    assert sorted(i['amount'] for i in items) == [Decimal('350.00'), Decimal('1785.00')]
    assert da_pagare == Decimal('2135.00')

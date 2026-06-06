"""
Prezzo del blocco stand:
- se NON imposto block_price -> somma dei prezzi degli stand inclusi;
- se imposto block_price -> vale quello (anche se diverso dalla somma).
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from venues.models import Stand, StandBlock, StandStatus


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Block Event', 'en': 'Block Event'},
        code='BK', start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )


def _stand(evento, code, price, block=None):
    return Stand.objects.create(
        event=evento, code=code, base_price=Decimal(price),
        status=StandStatus.AVAILABLE, stand_block=block,
    )


@pytest.mark.django_db
def test_prezzo_blocco_e_somma_stand_se_non_impostato(evento):
    block = StandBlock.objects.create(event=evento, code='BL-1')
    _stand(evento, 'A-1', '1000.00', block=block)
    _stand(evento, 'A-2', '1500.00', block=block)
    assert block.price_is_computed is True
    assert block.stands_price_sum == Decimal('2500.00')
    assert block.effective_price == Decimal('2500.00')


@pytest.mark.django_db
def test_prezzo_blocco_manuale_ha_priorita(evento):
    block = StandBlock.objects.create(
        event=evento, code='BL-2', block_price=Decimal('1800.00'))
    _stand(evento, 'B-1', '1000.00', block=block)
    _stand(evento, 'B-2', '1500.00', block=block)
    assert block.price_is_computed is False
    # somma sarebbe 2500, ma il prezzo a mano vince
    assert block.stands_price_sum == Decimal('2500.00')
    assert block.effective_price == Decimal('1800.00')


@pytest.mark.django_db
def test_blocco_senza_stand_somma_zero(evento):
    block = StandBlock.objects.create(event=evento, code='BL-3')
    assert block.effective_price == Decimal('0.00')


@pytest.mark.django_db
def test_stand_line_usa_prezzo_effettivo_del_blocco(evento, sponsor):
    from contracts.models import Contract, ContractKind, ContractStatus
    from contracts.services.stand_line import _stand_price_and_label
    block = StandBlock.objects.create(event=evento, code='BL-4')
    _stand(evento, 'C-1', '1200.00', block=block)
    _stand(evento, 'C-2', '800.00', block=block)
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, stand_block=block,
        contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT,
        contract_number='BK-26-001',
    )
    prezzo, label, marker = _stand_price_and_label(contract)
    assert prezzo == Decimal('2000.00')
    assert marker == f'block:{block.code}'

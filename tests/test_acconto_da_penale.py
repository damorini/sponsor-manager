"""Un preventivo nuovo prende come acconto la penale di cancellazione
dell'evento; si puo' cambiare, e 0 vuol dire pagamento unico."""
from datetime import date
from decimal import Decimal

import pytest


def _evento(penale):
    from events.models import Event
    return Event.objects.create(name={'it': 'Ev'}, code=f'ACC{penale}',
                                start_date=date(2027, 2, 25), end_date=date(2027, 2, 27),
                                cancellation_penalty_percent=penale)


@pytest.mark.django_db
def test_acconto_uguale_alla_penale(sponsor):
    from contracts.models import Contract, ContractKind
    c = Contract.objects.create(sponsor=sponsor, event=_evento(40), language='it',
                                contract_kind=ContractKind.MAIN, status='draft')
    assert c.deposit_percent == Decimal('40')
    assert c.has_deposit


@pytest.mark.django_db
def test_acconto_scelto_resta(sponsor):
    from contracts.models import Contract, ContractKind
    ev = _evento(40)
    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN, status='draft',
                                deposit_percent=Decimal('0'))
    assert c.deposit_percent == Decimal('0') and not c.has_deposit
    c.deposit_percent = None
    c.save()
    c.refresh_from_db()
    assert c.deposit_percent is None  # svuotato dopo: pagamento unico


@pytest.mark.django_db
def test_addon_senza_acconto(sponsor):
    from contracts.models import Contract, ContractKind
    c = Contract.objects.create(sponsor=sponsor, event=_evento(40), language='it',
                                contract_kind=ContractKind.ADDON, status='draft')
    assert c.deposit_percent is None

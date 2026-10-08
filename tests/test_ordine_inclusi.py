"""I servizi inclusi di un pacchetto hanno un Ordine: le righe incluse del
preventivo nascono in quell'ordine, e un incluso nuovo senza ordine va in fondo."""
from datetime import date
from decimal import Decimal

import pytest


@pytest.mark.django_db
def test_righe_incluse_seguono_l_ordine(sponsor):
    from catalog.models import Service, ServiceInclusion
    from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
    from contracts.services.pdf_generator import _posizione_inclusi
    from events.models import Event

    ev = Event.objects.create(name={'it': 'Ev'}, code='ORD',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))

    def servizio(code, prezzo='0'):
        return Service.objects.create(event=ev, code=code, name={'it': code},
                                      base_price=Decimal(prezzo), is_active=True)

    corso = servizio('CORSO', '1000')
    iscr, full, std = servizio('ISCR'), servizio('FULL'), servizio('STD')
    ServiceInclusion.objects.create(parent=corso, child=iscr, quantity=10, display_order=3)
    ServiceInclusion.objects.create(parent=corso, child=full, quantity=2, display_order=1)
    ServiceInclusion.objects.create(parent=corso, child=std, quantity=5, display_order=2)

    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.DRAFT)
    ContractLine.objects.create(contract=c, service=corso, quantity=1)

    incluse = [l for l in c.lines.all() if '[incluso:' in (l.notes or '')]
    assert [l.service.code for l in incluse] == ['FULL', 'STD', 'ISCR']

    pos = _posizione_inclusi(incluse)
    assert sorted(incluse, key=lambda l: pos[id(l)]) == incluse


@pytest.mark.django_db
def test_incluso_senza_ordine_va_in_fondo():
    from catalog.models import Service, ServiceInclusion
    from events.models import Event

    ev = Event.objects.create(name={'it': 'Ev'}, code='ORD2',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    pad, a, b = (Service.objects.create(event=ev, code=c, name={'it': c},
                                        base_price=Decimal('0')) for c in ('PAD', 'A', 'B'))
    ServiceInclusion.objects.create(parent=pad, child=a, display_order=7)
    nuovo = ServiceInclusion.objects.create(parent=pad, child=b)

    assert nuovo.display_order == 8
    assert [i.child.code for i in pad.inclusions.all()] == ['A', 'B']

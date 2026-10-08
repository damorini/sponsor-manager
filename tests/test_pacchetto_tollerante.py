"""Blocco con stand di tipologie diverse e pacchetti col codice scritto a mano
con spazi: gli inclusi vengono comunque sommati."""
from datetime import date
from decimal import Decimal

import pytest


@pytest.mark.django_db
def test_blocco_regular_a_e_b_con_codici_con_spazi(sponsor):
    from catalog.models import Service, ServiceInclusion
    from contracts.models import Contract, ContractKind, ContractStatus
    from events.models import Event
    from venues.models import Stand, StandBlock

    ev = Event.objects.create(name={'it': 'Ev'}, code='PKT',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))

    def servizio(code, nome):
        return Service.objects.create(event=ev, code=code, name={'it': nome},
                                      base_price=Decimal('0'), is_active=True)

    iscr = servizio('ISCR', 'Iscrizioni')
    full = servizio('FULL', 'Badge Full')
    a = servizio('SPAZIO_ESPOSITIVO_STAND_REGULAR - A', 'Regular A')
    b = servizio('SPAZIO_ESPOSITIVO_STAND_REGULAR - B', 'Regular B')
    ServiceInclusion.objects.create(parent=a, child=iscr, quantity=2)
    ServiceInclusion.objects.create(parent=a, child=full, quantity=2)
    ServiceInclusion.objects.create(parent=b, child=full, quantity=1)

    blocco = StandBlock.objects.create(event=ev, code='BLK')
    # salvare gli stand crea (vuoti) i pacchetti '..._REGULAR_A/_B': non
    # devono prendere il posto di quelli compilati
    for code, tipo, prezzo in (('1', 'Stand Regular -A', '8700'),
                               ('2', 'Stand Regular -B', '6240')):
        Stand.objects.create(event=ev, code=code, stand_type=tipo, stand_block=blocco,
                             width_meters=Decimal('3'), depth_meters=Decimal('2'),
                             base_price=Decimal(prezzo))

    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.DRAFT, stand_block=blocco)
    qta = {l.service.code: l.quantity for l in c.lines.all()}
    assert qta.get('ISCR') == 2, qta
    assert qta.get('FULL') == 3, qta

"""Servizi inclusi nell'ordine della lista del pacchetto dello stand."""
from datetime import date
from decimal import Decimal

import pytest

from catalog.models import Service, ServiceInclusion
from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services.pdf_generator import _righe_valorizzate_prima
from contracts.services.stand_line import get_or_create_stand_service
from events.models import Event
from venues.models import Stand


@pytest.fixture
def contratto(db, sponsor):
    ev = Event.objects.create(name={'it': 'Ev Ordine'}, code='ORD',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    pac = get_or_create_stand_service(ev, 'Main')
    # ordine voluto nella lista del pacchetto: C, A, B (non alfabetico)
    for codice, qta in (('ISCRIZIONI', 5), ('BADGE_DELEGATE', 2), ('BADGE_FULL', 3)):
        figlio = Service.objects.create(event=ev, code=codice, name={'it': codice},
                                        base_price=Decimal('10'))
        ServiceInclusion.objects.create(parent=pac, child=figlio, quantity=qta)
    st = Stand.objects.create(event=ev, code='1-A', stand_type='Main', base_price=Decimal('1000'))
    return Contract.objects.create(sponsor=sponsor, event=ev, stand=st, language='it',
                                   contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT)


def test_ordine_come_lista_pacchetto(contratto):
    from contracts.services.stand_line import genera_riga_da_stand
    if not contratto.lines.filter(notes__contains='stand:').exists():
        genera_riga_da_stand(contratto)
    righe = _righe_valorizzate_prima(contratto.lines.all())
    codici = [r.service.code for r in righe]
    assert codici[0].startswith('SPAZIO_ESPOSITIVO')
    assert codici[1:] == ['ISCRIZIONI', 'BADGE_DELEGATE', 'BADGE_FULL']
    # stessa cosa anche se le righe arrivano mescolate
    mescolate = list(reversed(list(contratto.lines.all())))
    assert [r.service.code for r in _righe_valorizzate_prima(mescolate)] == codici

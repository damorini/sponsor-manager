"""Mail PASS: porta di accesso sotto lo stand; per un blocco nome del blocco e
numeri degli stand."""
import re
from datetime import date
from decimal import Decimal

import pytest
from django.core import mail

from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services import pass_allestimento as pa
from events.models import Event
from venues.models import Stand, StandBlock


@pytest.fixture
def evento(db):
    return Event.objects.create(name={'it': 'Ev Pass Blocco'}, code='PSB',
                                start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))


def _testo(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def test_stand_con_porta_sotto(evento, sponsor, contact):
    st = Stand.objects.create(event=evento, code='1-A', base_price=Decimal('1'),
                              access_door='3')
    c = Contract.objects.create(sponsor=sponsor, event=evento, stand=st,
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SIGNED, contract_number='PSB-1')
    pa.invia(c)
    t = _testo(mail.outbox[0].alternatives[0][0])
    i_stand = t.index('Stand n. 1-A')
    i_porta = t.index('Porta di accesso al padiglione 3')
    i_contr = t.index('Contratto n. PSB-1')
    assert i_stand < i_porta < i_contr


def test_blocco_nome_e_stand(evento, sponsor, contact):
    b = StandBlock.objects.create(event=evento, code='SELTEC')
    for codice in ('29-A', '30-A'):
        Stand.objects.create(event=evento, code=codice, base_price=Decimal('1'),
                             stand_block=b, access_door='5')
    c = Contract.objects.create(sponsor=sponsor, event=evento, stand_block=b,
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SIGNED, contract_number='PSB-2')
    pa.invia(c)
    t = _testo(mail.outbox[0].alternatives[0][0])
    assert 'Blocco SELTEC' in t
    assert 'Stand del blocco n° 29-A e 30-A' in t
    assert 'Porta di accesso al padiglione 5' in t
    assert 'NUMERO DELLO STAND: 29-A e 30-A (Blocco SELTEC)' in t


def test_pdf_allegato_e_testi(evento, sponsor, contact):
    st = Stand.objects.create(event=evento, code='2-B', base_price=Decimal('1'))
    c = Contract.objects.create(sponsor=sponsor, event=evento, stand=st,
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SIGNED, contract_number='PSB-3')
    pa.invia(c)
    m = mail.outbox[0]
    nomi = [a[0] for a in m.attachments]
    assert nomi == ['PASS_allestimento_PSB-3.pdf']
    assert m.attachments[0][1][:4] == b'%PDF'
    t = _testo(m.alternatives[0][0])
    assert 'Accesso per allestimento e disallestimento' in t
    assert 'Tutti i lavori di allestimento e disallestimento dovranno essere terminati' in t
    assert "da inoltrare all'eventuale allestitore" in t

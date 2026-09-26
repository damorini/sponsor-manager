"""PASS: referente evidenziato, testi giustificati, indicazioni in cornice,
frase sull'allegato solo nella mail."""
from datetime import date
from decimal import Decimal

import pytest

from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services import pass_allestimento as pa
from events.models import Event
from venues.models import Stand


@pytest.fixture
def contratto(db, sponsor, contact):
    ev = Event.objects.create(
        name={'it': 'Ev Layout'}, code='LAY',
        start_date=date(2027, 2, 25), end_date=date(2027, 2, 27),
        referente_sponsor='Referente per informazioni SPONSOR:\nElisa Fantini Tel. 333',
        regole_montaggio='REGOLE PER IL MONTAGGIO:\nPrima riga.\n\nSeconda parte.',
        magazzino_ritiro='Ritiro entro lunedì.')
    st = Stand.objects.create(event=ev, code='1-A', base_price=Decimal('1'),
                              caratteristiche='Finiture bianche')
    return Contract.objects.create(sponsor=sponsor, event=ev, stand=st,
                                   contract_kind=ContractKind.MAIN,
                                   status=ContractStatus.SIGNED, contract_number='LAY-1')


def test_mail(contratto):
    _o, html = pa.anteprima(contratto)
    assert 'Elisa Fantini Tel. 333' in html and '#1d4ed8' in html
    assert '<strong>REGOLE PER IL MONTAGGIO:</strong><br>Prima riga.</p>' in html
    assert 'text-align:justify' in html
    assert 'background-color:#fdf8e8' in html and 'Finiture bianche' in html
    assert 'In allegato trovate questo PASS' in html


def test_pdf_senza_frase_allegato(contratto):
    _o, html = pa.anteprima(contratto, per_pdf=True)
    assert 'In allegato trovate questo PASS' not in html
    nome, dati = pa.pdf(contratto)
    assert dati[:4] == b'%PDF'

"""Preventivo: misure dello stand, superficie totale del blocco."""
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event
from venues.models import Stand, StandBlock


@pytest.fixture
def evento(db):
    return Event.objects.create(name={'it': 'Ev Misure'}, code='MIS',
                                start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))


def _html(contract, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    catturato = {}

    class Finto:
        def __init__(self, string, base_url=None):
            catturato['html'] = string

        def write_pdf(self):
            return b'%PDF-1.4'

    from contracts.services.pdf_generator import generate_quote_pdf_html
    with mock.patch('weasyprint.HTML', Finto):
        generate_quote_pdf_html(contract)
    return catturato['html']


def test_stand(evento, sponsor, settings, tmp_path):
    st = Stand.objects.create(event=evento, code='1-A', base_price=Decimal('1000'),
                              width_meters=Decimal('6'), depth_meters=Decimal('4'))
    c = Contract.objects.create(sponsor=sponsor, event=evento, stand=st, language='it',
                                contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT)
    html = _html(c, settings, tmp_path)
    assert 'Misure: 6 × 4 m (24 m²)' in html


def test_blocco(evento, sponsor, settings, tmp_path):
    b = StandBlock.objects.create(event=evento, code='BL')
    for code in ('2-A', '2-B'):
        Stand.objects.create(event=evento, code=code, base_price=Decimal('1000'), stand_block=b,
                             width_meters=Decimal('6'), depth_meters=Decimal('4'))
    c = Contract.objects.create(sponsor=sponsor, event=evento, stand_block=b, language='it',
                                contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT)
    html = _html(c, settings, tmp_path)
    assert 'Superficie totale: 48 m²' in html
    assert 'Misure:' not in html

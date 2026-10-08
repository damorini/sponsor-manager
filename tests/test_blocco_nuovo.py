"""Blocco stand nuovo: la doppia lista mostra gli stand disponibili senza
blocco; in modifica quelli dell'evento piu' quelli gia' nel blocco."""
from datetime import date
from decimal import Decimal

import pytest

from events.models import Event
from venues.admin import StandBlockForm
from venues.models import Stand, StandBlock, StandStatus


@pytest.fixture
def evento(db):
    return Event.objects.create(name={'it': 'Ev Blocchi'}, code='BLK',
                                start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))


def test_nuovo_blocco_mostra_gli_stand_disponibili(evento):
    libero = Stand.objects.create(event=evento, code='1-A', base_price=Decimal('1'))
    Stand.objects.create(event=evento, code='1-B', base_price=Decimal('1'),
                         status=StandStatus.ASSIGNED)
    scelti = list(StandBlockForm().fields['stands'].queryset)
    assert scelti == [libero]


def test_blocco_esistente(evento):
    b = StandBlock.objects.create(event=evento, code='BL1')
    dentro = Stand.objects.create(event=evento, code='2-A', base_price=Decimal('1'),
                                  stand_block=b)
    libero = Stand.objects.create(event=evento, code='2-B', base_price=Decimal('1'))
    form = StandBlockForm(instance=b)
    assert set(form.fields['stands'].queryset) == {dentro, libero}
    assert list(form.fields['stands'].initial) == [dentro]

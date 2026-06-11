"""
Gli spazi/stand vanno ordinati in modo NUMERICO (1, 2, 3, ... 10, 11),
non lessicografico (1, 10, 11, 2). Codice = CharField, quindi serve
ordinare per (lunghezza, codice).
"""
import pytest
from datetime import date


@pytest.mark.django_db
def test_stand_numeric_ordering():
    from events.models import Event
    from venues.models import Stand

    ev = Event.objects.create(
        name={'it': 'O', 'en': 'O'}, code='ORD',
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    for c in ['1', '10', '2', '11', '3', '20', '9']:
        Stand.objects.create(event=ev, code=c)

    codes = list(Stand.objects.filter(event=ev).values_list('code', flat=True))
    assert codes == ['1', '2', '3', '9', '10', '11', '20']


@pytest.mark.django_db
def test_standblock_numeric_ordering():
    from events.models import Event
    from venues.models import StandBlock

    ev = Event.objects.create(
        name={'it': 'B', 'en': 'B'}, code='ORDB',
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    for c in ['1', '10', '2', '3']:
        StandBlock.objects.create(event=ev, code=c)

    codes = list(StandBlock.objects.filter(event=ev).values_list('code', flat=True))
    assert codes == ['1', '2', '3', '10']

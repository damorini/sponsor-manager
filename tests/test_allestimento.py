"""Evento: giorni di allestimento/disallestimento con orari, gestiti dalla
scheda dell'evento; il giorno della settimana si ricava dalla data."""
from datetime import date, time

import pytest
from django.core.exceptions import ValidationError

from events.models import Event, EventSetupDay, SetupKind


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Allest'}, code='ALL',
        start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))


def test_giorno_della_settimana(evento):
    g = EventSetupDay.objects.create(
        event=evento, kind=SetupKind.ALLESTIMENTO, date=date(2027, 2, 24),
        start_time=time(8), end_time=time(20))
    assert g.giorno_settimana == 'Mercoledì'
    assert 'Allestimento Mercoledì 24/02/2027 08:00-20:00' == str(g)


def test_fine_prima_di_inizio_non_valida(evento):
    g = EventSetupDay(event=evento, date=date(2027, 2, 27),
                      start_time=time(18), end_time=time(14))
    with pytest.raises(ValidationError):
        g.full_clean()


def test_piu_giorni_in_ordine(evento):
    EventSetupDay.objects.create(event=evento, kind=SetupKind.DISALLESTIMENTO,
                                 date=date(2027, 2, 27), start_time=time(14),
                                 end_time=time(22))
    EventSetupDay.objects.create(event=evento, date=date(2027, 2, 24),
                                 start_time=time(8), end_time=time(20))
    EventSetupDay.objects.create(event=evento, date=date(2027, 2, 25),
                                 start_time=time(7), end_time=time(9))
    tipi = [g.kind for g in evento.setup_days.all()]
    assert tipi == ['allestimento', 'allestimento', 'disallestimento']


def test_tabellina_nella_scheda_evento(client, evento):
    from django.contrib.auth import get_user_model
    admin = get_user_model().objects.create_superuser(
        username='regia', email='regia@test.it', password='AdminPass123!')
    client.force_login(admin)
    html = client.get(f'/admin/events/event/{evento.pk}/change/').content.decode()
    assert 'Allestimento e disallestimento' in html
    assert 'setup_days-TOTAL_FORMS' in html
    assert 'giorno_settimana.js' in html

"""Regressione 27/08: salvare uno Stand con i campi bilingui (descrizione
preventivo / note sponsor) TUTTI VUOTI dava errore 500.

- TranslatableJSONField.to_python ritornava None (colonna NOT NULL -> crash);
- required_languages=[] veniva trasformato in ['it'] dall'`or`, chiedendo
  l'italiano anche sui campi facoltativi.
"""
from datetime import date
from decimal import Decimal

import pytest

from events.models import Event
from venues.admin import StandAdminForm
from venues.models import Stand


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Widget Vuoto', 'en': 'Ev Widget Vuoto'}, code='TWV',
        start_date=date(2027, 3, 1), end_date=date(2027, 3, 2),
    )


def _dati_base(evento, **extra):
    dati = {
        'event': str(evento.pk),
        'code': 'W-01',
        'status': 'available',
        'base_price': '1000.00',
        # campi bilingui: sottocampi _0 (it) e _1 (en) del MultiWidget
        'quote_description_0': '', 'quote_description_1': '',
        'sponsor_notes_0': '', 'sponsor_notes_1': '',
        'notes': '',
        'stand_type': '',
    }
    dati.update(extra)
    return dati


@pytest.mark.django_db
def test_stand_salva_con_campi_bilingui_vuoti(evento):
    form = StandAdminForm(data=_dati_base(evento))
    assert form.is_valid(), form.errors
    # mai None: la colonna e' NOT NULL con default dict
    assert form.cleaned_data['quote_description'] == {}
    assert form.cleaned_data['sponsor_notes'] == {}
    stand = form.save()
    stand.refresh_from_db()
    assert stand.quote_description == {}
    assert stand.sponsor_notes == {}


@pytest.mark.django_db
def test_stand_salva_nota_sponsor_compilata(evento):
    form = StandAdminForm(data=_dati_base(
        evento, sponsor_notes_0='Grafiche in PDF 300 dpi'))
    assert form.is_valid(), form.errors
    stand = form.save()
    stand.refresh_from_db()
    assert stand.sponsor_notes.get('it') == 'Grafiche in PDF 300 dpi'

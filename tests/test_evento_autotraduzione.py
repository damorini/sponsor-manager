"""Regressione 30/08: nome e descrizione dell'EVENTO non si auto-traducevano
(il modello non dichiarava TRANSLATABLE_FIELDS, il segnale lo saltava).
Servizi e stand funzionavano; gli eventi restavano con l'inglese vuoto."""
from datetime import date

import pytest

from events.models import Event


@pytest.mark.django_db
def test_evento_autotraduce_nome_e_descrizione(monkeypatch, settings):
    settings.AUTO_TRANSLATE_ON_SAVE = True
    monkeypatch.setattr('core.translation.translate_text',
                        lambda text, **kw: f'EN::{text}')
    ev = Event.objects.create(
        name={'it': 'Congresso di prova'},
        description={'it': 'Descrizione di prova'},
        code='AUTOTR', slug='autotr-2027',
        start_date=date(2027, 5, 1), end_date=date(2027, 5, 2))
    ev.refresh_from_db()
    assert ev.name.get('en') == 'EN::Congresso di prova'
    assert ev.description.get('en') == 'EN::Descrizione di prova'


@pytest.mark.django_db
def test_inglese_scritto_a_mano_non_sovrascritto(monkeypatch, settings):
    settings.AUTO_TRANSLATE_ON_SAVE = True
    monkeypatch.setattr('core.translation.translate_text',
                        lambda text, **kw: 'MACCHINA')
    ev = Event.objects.create(
        name={'it': 'Congresso', 'en': 'Handmade Congress'},
        code='AUTOTR2', slug='autotr2-2027',
        start_date=date(2027, 5, 1), end_date=date(2027, 5, 2))
    ev.refresh_from_db()
    assert ev.name.get('en') == 'Handmade Congress'

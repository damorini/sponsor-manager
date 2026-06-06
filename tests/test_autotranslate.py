"""
Auto-traduzione IT->EN al salvataggio dei modelli traducibili (TranslatableMixin).

Al salvataggio (admin o import da Excel), se manca la versione inglese di un campo
traducibile ma c'è quella italiana, viene compilata via DeepL. Qui DeepL è MOCKATO
(i test non devono chiamare la rete). Vedi core/signals.py + core/translatable.py.
"""
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch

from events.models import Event
from catalog.models import Service


def _event(code):
    return Event.objects.create(
        name={'it': 'Evento', 'en': 'Event'}, code=code,
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 2),
    )


@pytest.mark.django_db
class TestAutoTranslate:
    def test_fills_en_from_it_on_save(self, settings):
        settings.AUTO_TRANSLATE_ON_SAVE = True
        ev = _event('AT1')
        with patch('core.translation.translate_text', return_value='Padded chair') as m:
            s = Service.objects.create(event=ev, name={'it': 'Sedia imbottita'},
                                       base_price=Decimal('10.00'))
        s.refresh_from_db()
        assert s.name.get('en') == 'Padded chair'
        assert m.called

    def test_does_not_overwrite_existing_en(self, settings):
        settings.AUTO_TRANSLATE_ON_SAVE = True
        ev = _event('AT2')
        with patch('core.translation.translate_text', return_value='AUTO') as m:
            s = Service.objects.create(event=ev, name={'it': 'Sedia', 'en': 'Manual EN'},
                                       base_price=Decimal('10.00'))
        s.refresh_from_db()
        assert s.name.get('en') == 'Manual EN'
        assert not m.called

    def test_flag_off_skips_translation(self, settings):
        settings.AUTO_TRANSLATE_ON_SAVE = False
        ev = _event('AT3')
        with patch('core.translation.translate_text', return_value='X') as m:
            s = Service.objects.create(event=ev, name={'it': 'Sedia'},
                                       base_price=Decimal('10.00'))
        s.refresh_from_db()
        assert not m.called
        assert not (s.name or {}).get('en')

    def test_stand_quote_description_autofilled(self, settings):
        """La descrizione stand (ora bilingue) si auto-traduce al salvataggio/import."""
        from venues.models import Stand
        settings.AUTO_TRANSLATE_ON_SAVE = True
        ev = _event('AT4')
        with patch('core.translation.translate_text', return_value='Rectangular booth') as m:
            st = Stand.objects.create(event=ev, code='S1', base_price=Decimal('100.00'),
                                      quote_description={'it': 'Stand rettangolare'})
        st.refresh_from_db()
        assert st.quote_description.get('en') == 'Rectangular booth'
        assert m.called

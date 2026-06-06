"""
Le varianti servizio auto-traducono 'label' (IT) -> 'label_en' (EN) al salvataggio
se l'inglese è vuoto (campi CharField separati, gestiti da un signal dedicato).
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from catalog.models import Service, ServiceVariant


@pytest.fixture
def service(db):
    event = Event.objects.create(
        name={'it': 'Ev', 'en': 'Ev'}, code='EVV',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Service.objects.create(
        event=event, code='SV', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
    )


@pytest.mark.django_db
def test_label_en_si_autocompila(settings, monkeypatch, service):
    settings.AUTO_TRANSLATE_ON_SAVE = True
    import core.translation as tr
    monkeypatch.setattr(tr, 'translate_text',
                        lambda text, source='it', target='en', html=False: 'EN:' + text)

    v = ServiceVariant.objects.create(
        service=service, label='Sedia rossa', base_price=Decimal('10.00'))
    v.refresh_from_db()
    assert v.label_en == 'EN:Sedia rossa'


@pytest.mark.django_db
def test_label_en_manuale_non_sovrascritto(settings, monkeypatch, service):
    settings.AUTO_TRANSLATE_ON_SAVE = True
    import core.translation as tr
    monkeypatch.setattr(tr, 'translate_text',
                        lambda text, source='it', target='en', html=False: 'EN:' + text)

    v = ServiceVariant.objects.create(
        service=service, label='Sedia blu', label_en='Blue chair',
        base_price=Decimal('10.00'))
    v.refresh_from_db()
    assert v.label_en == 'Blue chair'  # non sovrascrive l'inglese inserito a mano

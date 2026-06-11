"""
Lista gestita delle tipologie di stand (StandType) + menu a tendina sullo Stand:
- il menu mostra le tipologie gestite (attive) PIU' eventuali valori liberi già
  usati; le inattive sono escluse;
- il campo resta libero (testo), quindi un valore su misura per congresso si può
  comunque digitare e salvare.
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from venues.models import Stand, StandStatus, StandType


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'TL', 'en': 'TL'}, code='TL',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )


@pytest.mark.django_db
def test_standtype_str_e_ordine():
    StandType.objects.create(name='stand', display_order=2)
    StandType.objects.create(name='desk', display_order=1)
    assert str(StandType.objects.get(name='stand')) == 'stand'
    # ordina per display_order, poi nome
    assert list(StandType.objects.values_list('name', flat=True)) == ['desk', 'stand']


@pytest.mark.django_db
def test_menu_tipologia_usa_lista_gestita_piu_valori_liberi(evento):
    from venues.admin import StandAdminForm
    StandType.objects.create(name='premium', display_order=0)
    StandType.objects.create(name='nascosta', is_active=False)
    # un valore libero già usato su uno stand, NON presente nella lista gestita
    Stand.objects.create(
        event=evento, code='Z-1', base_price=Decimal('100.00'),
        status=StandStatus.AVAILABLE, stand_type='su misura',
    )
    opzioni = StandAdminForm().fields['stand_type'].widget.options
    assert 'premium' in opzioni       # dalla lista gestita
    assert 'su misura' in opzioni     # valore libero già usato resta disponibile
    assert 'nascosta' not in opzioni  # tipologia inattiva esclusa


@pytest.mark.django_db
def test_tipologia_libera_si_salva(evento):
    # il campo resta testo libero: una tipologia non in lista si salva lo stesso
    s = Stand.objects.create(
        event=evento, code='Z-2', base_price=Decimal('100.00'),
        status=StandStatus.AVAILABLE, stand_type='isola tripla',
    )
    s.refresh_from_db()
    assert s.stand_type == 'isola tripla'

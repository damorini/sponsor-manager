"""
Uno stand scelto in un contratto sparisce SUBITO dalla tendina degli spazi
del contratto successivo, anche se il primo e' solo una bozza non inviata.
Ricompare soltanto quando l'opzione scade (o il contratto viene annullato,
cestinato o spostato su un altro stand). Prima la bozza senza opzione non
teneva lo stand: la tendina lo riproponeva e l'errore "gia' impegnato"
arrivava solo al salvataggio.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event
from venues.models import Stand, StandBlock, StandStatus


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        username='regia', email='regia@test.it', password='AdminPass123!')


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Tendina', 'en': 'Ev Tendina'}, code='TND',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )


@pytest.fixture
def stand_a(evento):
    return Stand.objects.create(event=evento, code='T-01', base_price=Decimal('1000.00'))


@pytest.fixture
def stand_b(evento):
    return Stand.objects.create(event=evento, code='T-02', base_price=Decimal('1000.00'))


def _bozza(sponsor, evento, **kw):
    return Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, **kw)


def _tendina(client, field_name='stand'):
    resp = client.get('/admin/autocomplete/', {
        'app_label': 'contracts', 'model_name': 'contract',
        'field_name': field_name, 'term': 'T-'})
    assert resp.status_code == 200
    return {r['id'] for r in json.loads(resp.content)['results']}


@pytest.mark.django_db
def test_bozza_senza_opzione_toglie_lo_stand_dalla_tendina(
        client, admin_user, sponsor, evento, stand_a, stand_b):
    client.force_login(admin_user)
    assert str(stand_a.pk) in _tendina(client)

    _bozza(sponsor, evento, stand=stand_a)

    ids = _tendina(client)
    assert str(stand_a.pk) not in ids
    assert str(stand_b.pk) in ids
    stand_a.refresh_from_db()
    assert stand_a.status == StandStatus.RESERVED


@pytest.mark.django_db
def test_bozza_con_opzione_attiva_toglie_lo_stand(
        client, admin_user, sponsor, evento, stand_a):
    client.force_login(admin_user)
    _bozza(sponsor, evento, stand=stand_a,
           option_until=date.today() + timedelta(days=5))
    assert str(stand_a.pk) not in _tendina(client)


@pytest.mark.django_db
def test_opzione_scaduta_lo_stand_ricompare(
        client, admin_user, sponsor, evento, stand_a):
    from contracts.tasks.scheduled import libera_spazi_opzione_scaduta
    client.force_login(admin_user)
    c = _bozza(sponsor, evento, stand=stand_a,
               option_until=date.today() + timedelta(days=5))
    # passa il tempo: l'opzione e' scaduta ieri
    Contract.objects.filter(pk=c.pk).update(
        option_until=date.today() - timedelta(days=1))

    # la tendina lo ripropone subito, senza aspettare il ricalcolo notturno
    assert str(stand_a.pk) in _tendina(client)

    stand_a.refresh_from_db()
    assert stand_a.status == StandStatus.RESERVED
    assert libera_spazi_opzione_scaduta() == 1
    stand_a.refresh_from_db()
    assert stand_a.status == StandStatus.AVAILABLE


@pytest.mark.django_db
def test_opzione_scade_oggi_lo_stand_resta_tenuto(
        client, admin_user, sponsor, evento, stand_a):
    client.force_login(admin_user)
    _bozza(sponsor, evento, stand=stand_a, option_until=date.today())
    assert str(stand_a.pk) not in _tendina(client)


@pytest.mark.django_db
def test_secondo_contratto_sullo_stesso_stand_bloccato(sponsor, evento, stand_a):
    _bozza(sponsor, evento, stand=stand_a)
    secondo = Contract(sponsor=sponsor, event=evento,
                       contract_kind=ContractKind.MAIN,
                       status=ContractStatus.DRAFT, stand=stand_a)
    with pytest.raises(ValidationError) as err:
        secondo.clean()
    assert 'stand' in err.value.message_dict


@pytest.mark.django_db
def test_cambio_stand_libera_quello_di_prima(
        client, admin_user, sponsor, evento, stand_a, stand_b):
    client.force_login(admin_user)
    c = _bozza(sponsor, evento, stand=stand_a)
    c.stand = stand_b
    c.save()

    ids = _tendina(client)
    assert str(stand_a.pk) in ids
    assert str(stand_b.pk) not in ids
    stand_a.refresh_from_db()
    assert stand_a.status == StandStatus.AVAILABLE


@pytest.mark.django_db
def test_bozza_cestinata_libera_lo_stand(
        client, admin_user, sponsor, evento, stand_a):
    client.force_login(admin_user)
    c = _bozza(sponsor, evento, stand=stand_a)
    c.delete()
    assert str(stand_a.pk) in _tendina(client)


@pytest.mark.django_db
def test_blocco_in_bozza_sparisce_dalla_tendina_blocchi(
        client, admin_user, sponsor, evento):
    client.force_login(admin_user)
    blocco = StandBlock.objects.create(event=evento, code='T-BLK',
                                       block_price=Decimal('2000.00'))
    altro = StandBlock.objects.create(event=evento, code='T-BLK2',
                                      block_price=Decimal('2000.00'))
    _bozza(sponsor, evento, stand_block=blocco)
    ids = _tendina(client, 'stand_block')
    assert str(blocco.pk) not in ids
    assert str(altro.pk) in ids

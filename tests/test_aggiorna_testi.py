"""Pulsante «Aggiorna i testi dei servizi»: le righe del preventivo prendono
i testi attuali dei servizi e dello stand, senza toccare prezzi e quantita'."""
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def admin_client_testi(db, client):
    from django.contrib.auth import get_user_model
    utente = get_user_model().objects.create_superuser(
        username='boss_testi', email='boss.testi@test.it', password='AdminPass123!')
    client.force_login(utente)
    return client


def _preventivo(sponsor, stato='draft'):
    from catalog.models import Service
    from contracts.models import Contract, ContractKind, ContractLine
    from events.models import Event
    from venues.models import Stand

    ev = Event.objects.create(name={'it': 'Ev'}, code='TXT',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    stand = Stand.objects.create(event=ev, code='1-A', stand_type='Main XL',
                                 width_meters=Decimal('6'), depth_meters=Decimal('4'),
                                 base_price=Decimal('1000'),
                                 quote_description={'it': 'Area nuda vecchia'})
    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN, status='draft', stand=stand)
    wifi = Service.objects.create(event=ev, code='WIFI', name={'it': 'Wifi'},
                                  description={'it': 'Q vecchio testo'},
                                  base_price=Decimal('1500'), is_active=True)
    riga = ContractLine.objects.create(contract=c, service=wifi, quantity=2,
                                       unit_price=Decimal('900'))
    libera = ContractLine.objects.create(contract=c, custom_description='Su misura',
                                         quantity=1, unit_price=Decimal('10'))
    if stato != 'draft':
        type(c).objects.filter(pk=c.pk).update(status=stato)
        c.refresh_from_db()
    return c, stand, wifi, riga, libera


@pytest.mark.django_db
def test_ricopia_i_testi_attuali(sponsor):
    from catalog.models import Service
    from contracts.services.testi_righe import aggiorna_testi_righe

    c, stand, wifi, riga, libera = _preventivo(sponsor)
    Service.objects.filter(pk=wifi.pk).update(
        name={'it': 'WiFi Password'}, description={'it': '- testo nuovo'})
    type(stand).objects.filter(pk=stand.pk).update(quote_description={'it': 'Area nuda nuova'})
    c.refresh_from_db()

    assert aggiorna_testi_righe(c) == 2
    riga.refresh_from_db(); libera.refresh_from_db()
    assert (riga.service_name_snapshot, riga.service_description_snapshot) == ('WiFi Password', '- testo nuovo')
    assert (riga.quantity, riga.unit_price) == (2, Decimal('900.00'))
    assert c.lines.get(notes='stand:1-A').service_description_snapshot == 'Area nuda nuova'
    assert libera.service_name_snapshot == 'Su misura'
    assert aggiorna_testi_righe(c) == 0


@pytest.mark.django_db
def test_pulsante_non_tocca_i_firmati(admin_client_testi, sponsor):
    from catalog.models import Service

    c, _stand, wifi, riga, _libera = _preventivo(sponsor, stato='signed')
    Service.objects.filter(pk=wifi.pk).update(description={'it': 'nuovo'})
    r = admin_client_testi.post('/admin/contracts/contract/',
                                {'action': 'action_aggiorna_testi', '_selected_action': [str(c.pk)]})
    assert r.status_code == 302
    riga.refresh_from_db()
    assert riga.service_description_snapshot == 'Q vecchio testo'


@pytest.mark.django_db
def test_pulsante_nella_pagina_del_preventivo(admin_client_testi, sponsor):
    c, *_ = _preventivo(sponsor)
    r = admin_client_testi.get(f'/admin/contracts/contract/{c.pk}/change/')
    assert r.status_code == 200
    assert 'Aggiorna i testi dei servizi' in r.content.decode()

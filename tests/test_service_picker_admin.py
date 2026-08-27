"""Finestra 'Catalogo' per la scelta dei servizi nelle righe contratto.

- endpoint /admin/contracts/contract/<id>/servizi-json/ ritorna i servizi
  dell'EVENTO del contratto (id, nome, codice, prezzo, categoria)
- la pagina di modifica contratto carica il JS del selettore
"""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event, EventStatus


@pytest.fixture
def staff(db):
    User = get_user_model()
    return User.objects.create_superuser(
        username='op_picker', email='op_picker@test.it', password='x')


@pytest.fixture
def contratto(db, sponsor):
    evento = Event.objects.create(
        name={'it': 'Ev Picker', 'en': 'Ev Picker'}, code='PCK',
        status=EventStatus.SELLING,
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    Service.objects.create(event=evento, code='WIFI',
                           name={'it': 'Wifi dedicato', 'en': 'Wifi'},
                           base_price=Decimal('150.00'))
    Service.objects.create(event=evento, code='BANNER',
                           name={'it': 'Banner sala', 'en': 'Banner'},
                           base_price=Decimal('800.00'))
    # servizio di un ALTRO evento: non deve comparire
    altro = Event.objects.create(
        name={'it': 'Ev Altro', 'en': 'Ev Altro'}, code='ALT',
        start_date=date(2026, 12, 5), end_date=date(2026, 12, 6),
    )
    Service.objects.create(event=altro, code='ESTRANEO',
                           name={'it': 'Estraneo', 'en': 'Estraneo'},
                           base_price=Decimal('1.00'))
    return Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='PCK-26-001',
    )


@pytest.mark.django_db
def test_endpoint_servizi_json(client, staff, contratto):
    client.force_login(staff)
    url = reverse('admin:contracts_contract_servizi_json', args=[contratto.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    dati = resp.json()['services']
    codici = {s['code'] for s in dati}
    assert {'WIFI', 'BANNER'} <= codici
    assert 'ESTRANEO' not in codici
    wifi = next(s for s in dati if s['code'] == 'WIFI')
    assert wifi['name'] == 'Wifi dedicato'
    assert wifi['price'] == 150.0
    assert wifi['active'] is True


@pytest.mark.django_db
def test_endpoint_richiede_login(client, contratto):
    url = reverse('admin:contracts_contract_servizi_json', args=[contratto.pk])
    resp = client.get(url)
    assert resp.status_code in (302, 403)  # redirect alla login admin


@pytest.mark.django_db
def test_pagina_contratto_carica_il_js(client, staff, contratto):
    client.force_login(staff)
    resp = client.get(reverse('admin:contracts_contract_change', args=[contratto.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'contractline_service_picker_v2.js' in html
    # regressione: il ?v=N nel Media veniva URL-encodato -> 404 del file
    assert '%3F' not in html.split('contractline_service_picker')[1][:20]

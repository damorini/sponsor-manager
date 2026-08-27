"""Regressione 27/08: aggiungere due volte lo stesso 'servizio incluso' a un
servizio dava errore 500 (vincolo unico parent+child violato al DB, mai
validato dal form). Ora il salvataggio viene bloccato con un messaggio."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Service, ServiceInclusion
from events.models import Event


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_superuser(
        username='op_incl', email='op_incl@test.it', password='x')


@pytest.fixture
def servizi(db):
    ev = Event.objects.create(
        name={'it': 'Ev Inclusi', 'en': 'Ev Inclusi'}, code='INCL',
        start_date=date(2027, 4, 1), end_date=date(2027, 4, 2))
    padre = Service.objects.create(event=ev, code='PADRE',
                                   name={'it': 'Padre', 'en': 'Padre'},
                                   base_price=Decimal('1000.00'))
    figlio = Service.objects.create(event=ev, code='FIGLIO',
                                    name={'it': 'Figlio', 'en': 'Figlio'},
                                    base_price=Decimal('0.00'))
    ServiceInclusion.objects.create(parent=padre, child=figlio, quantity=1)
    return padre, figlio


def _payload(padre, figlio, righe):
    dati = {
        'event': str(padre.event_id), 'code': padre.code,
        'name_0': 'Padre', 'name_1': 'Padre',
        'description_0': '', 'description_1': '',
        'category': '', 'accounting_category': '',
        'pricing_mode': 'fixed', 'base_price': '1000.00',
        'vat_rate': '22.00', 'display_order': '0',
        'is_active': 'on',
        # formset varianti e scadenze vuoti
        'variants-TOTAL_FORMS': '0', 'variants-INITIAL_FORMS': '0',
        'deadline_templates-TOTAL_FORMS': '0', 'deadline_templates-INITIAL_FORMS': '0',
        # inclusi
        'inclusions-TOTAL_FORMS': str(len(righe)),
        'inclusions-INITIAL_FORMS': str(sum(1 for r in righe if r.get('id'))),
    }
    for i, r in enumerate(righe):
        dati[f'inclusions-{i}-id'] = r.get('id', '')
        dati[f'inclusions-{i}-parent'] = str(padre.pk)
        dati[f'inclusions-{i}-child'] = str(r['child'])
        dati[f'inclusions-{i}-quantity'] = '1'
    return dati


@pytest.mark.django_db
def test_incluso_duplicato_messaggio_non_500(client, staff, servizi):
    padre, figlio = servizi
    incl = padre.inclusions.first()
    client.force_login(staff)
    url = reverse('admin:catalog_service_change', args=[padre.pk])
    righe = [
        {'id': str(incl.pk), 'child': figlio.pk},
        {'child': figlio.pk},  # DOPPIONE
    ]
    resp = client.post(url, _payload(padre, figlio, righe))
    assert resp.status_code == 200  # form rimostrato, NON 500
    assert 'duplicati' in resp.content.decode() or 'già incluso' in resp.content.decode()
    assert padre.inclusions.count() == 1  # nessun doppione salvato


@pytest.mark.django_db
def test_incluso_duplicato_da_pagina_vecchia_non_500(client, staff, servizi):
    """Il caso del 500 in produzione: la pagina era stata caricata PRIMA che
    l'incluso esistesse (o rispedita dopo il primo salvataggio), quindi il
    formset contiene solo la riga nuova che duplica una riga gia' nel DB."""
    padre, figlio = servizi
    client.force_login(staff)
    url = reverse('admin:catalog_service_change', args=[padre.pk])
    righe = [{'child': figlio.pk}]  # nuova riga, l'esistente NON e' nel form
    resp = client.post(url, _payload(padre, figlio, righe))
    assert resp.status_code == 200  # messaggio, NON 500
    assert 'risulta già incluso' in resp.content.decode()
    assert padre.inclusions.count() == 1

"""
Avviso "preventivi DA INVIARE" in cima al backoffice. Con un solo preventivo
porta dritti alla sua scheda (dove c'e' "Genera e invia preventivo"); sulla
lista gia' filtrata non invita a cliccare la stessa pagina, che sembrava non
fare nulla.
"""
from datetime import date

import pytest
from django.urls import reverse

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        username='regia', email='regia@test.it', password='AdminPass123!')


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Avviso', 'en': 'Ev Avviso'}, code='AVV',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )


def _bozza(sponsor, evento):
    return Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT)


LISTA = '/admin/contracts/contract/'


def test_un_solo_preventivo_apre_la_sua_scheda(client, admin_user, sponsor, evento):
    c = _bozza(sponsor, evento)
    client.force_login(admin_user)
    html = client.get(LISTA).content.decode()
    url = reverse('admin:contracts_contract_change', args=[c.pk])
    assert f'href="{url}"' in html
    assert 'Clicca qui per aprirlo e inviarlo' in html


def test_sulla_lista_filtrata_non_rimanda_a_se_stessa(client, admin_user, sponsor, evento):
    _bozza(sponsor, evento)
    client.force_login(admin_user)
    html = client.get(LISTA, {'todo': 'da_inviare'}).content.decode()
    assert 'Li trovi nella tabella qui sotto' in html
    assert 'Clicca qui per' not in html


def test_nella_scheda_del_preventivo_indica_il_pulsante(client, admin_user, sponsor, evento):
    c = _bozza(sponsor, evento)
    client.force_login(admin_user)
    url = reverse('admin:contracts_contract_change', args=[c.pk])
    html = client.get(url).content.decode()
    assert 'Questo preventivo è ancora DA INVIARE' in html


def test_piu_preventivi_aprono_la_lista(client, admin_user, sponsor, evento):
    _bozza(sponsor, evento)
    _bozza(sponsor, evento)
    client.force_login(admin_user)
    html = client.get('/admin/sponsors/sponsor/').content.decode()
    assert 'href="/admin/contracts/contract/?todo=da_inviare"' in html
    assert 'Hai 2 preventivi creati' in html

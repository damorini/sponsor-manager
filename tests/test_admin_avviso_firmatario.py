"""Avviso all'operatore quando invia un preventivo SENZA firmatario.

Senza legale rappresentante firmatario il cliente viene bloccato alla
conferma (gate portale): l'operatore deve saperlo GIA' al momento
dell'invio, con un banner nella pagina di invio preventivo e un messaggio
dopo l'azione 'Marca come INVIATO'.
"""
import pytest
from datetime import date
from django.urls import reverse


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        username='capo', email='capo@test.it', password='AdminPass123!')


@pytest.fixture
def preventivo_bozza(db, sponsor):
    from sponsors.models import Contact, ContactRole
    from events.models import Event
    from contracts.models import Contract, ContractKind, ContractStatus
    Contact.objects.create(
        sponsor=sponsor, full_name='Anna Verdi', email='anna@test.it',
        roles=[ContactRole.OPERATIONAL],  # NESSUN firmatario
    )
    event = Event.objects.create(
        name={'it': 'Warn Ev', 'en': 'Warn Ev'}, code='WRN',
        start_date=date(2026, 12, 15), end_date=date(2026, 12, 16),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='WRN-26-001',
    )


@pytest.mark.django_db
def test_pagina_invio_mostra_banner_senza_firmatario(client, admin_user, preventivo_bozza):
    client.force_login(admin_user)
    url = reverse('admin:contracts_contract_send_quote', args=[preventivo_bozza.id])
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'Manca il firmatario' in resp.content.decode()


@pytest.mark.django_db
def test_pagina_invio_senza_banner_con_firmatario(client, admin_user, preventivo_bozza):
    preventivo_bozza.sponsor.contacts.update(is_signer=True)
    client.force_login(admin_user)
    url = reverse('admin:contracts_contract_send_quote', args=[preventivo_bozza.id])
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'Manca il firmatario' not in resp.content.decode()


@pytest.mark.django_db
def test_azione_marca_inviato_avvisa(client, admin_user, preventivo_bozza):
    client.force_login(admin_user)
    resp = client.post(
        reverse('admin:contracts_contract_changelist'),
        {'action': 'action_mark_as_sent',
         '_selected_action': [str(preventivo_bozza.id)]},
        follow=True,
    )
    testo = resp.content.decode()
    assert 'FIRMATARIO' in testo, \
        "dopo 'Marca come INVIATO' deve comparire l'avviso firmatario mancante"
    preventivo_bozza.refresh_from_db()
    from contracts.models import ContractStatus
    assert preventivo_bozza.status == ContractStatus.SENT

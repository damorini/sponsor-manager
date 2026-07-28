"""Regressione: la card "Scadenze aperte" della dashboard portale deve
portare a una pagina REALE (le scadenze dell'evento più urgente), non a
un'ancora sulla stessa pagina che "non fa nulla". Con zero scadenze aperte
la card non è cliccabile."""
import pytest
from datetime import date
from django.urls import reverse

from contracts.models import Contract, ContractKind, ContractStatus, Deadline, DeadlineStatus
from events.models import Event


@pytest.fixture
def contratto_firmato(db, user_sponsor, sponsor, contact):
    event = Event.objects.create(
        name={'it': 'Ev Card Scadenze', 'en': 'Ev Card Scadenze'}, code='CRD',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='CRD-26-001',
    )
    return contract, event


@pytest.mark.django_db
def test_card_con_scadenze_linka_pagina_scadenze_evento(client, user_sponsor, contratto_firmato):
    contract, event = contratto_firmato
    Deadline.objects.create(
        contract=contract, deadline_type='tecnica', title='Invio logo',
        due_date=date(2026, 10, 1), status=DeadlineStatus.PENDING,
    )
    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:dashboard'))
    html = resp.content.decode()

    url_scadenze = reverse('portal:event_materials', args=[event.id])
    assert url_scadenze in html, \
        "la card Scadenze aperte deve linkare la pagina scadenze dell'evento"
    assert 'href="#scadenze"' not in html, \
        "niente più ancora interna: portava 'da nessuna parte' per l'utente"

    # e la destinazione risponde davvero
    resp2 = client.get(url_scadenze)
    assert resp2.status_code == 200


@pytest.mark.django_db
def test_card_senza_scadenze_non_e_cliccabile(client, user_sponsor, contratto_firmato):
    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:dashboard'))
    html = resp.content.decode()
    assert 'tutto in regola' in html
    assert 'href="#scadenze"' not in html
    assert resp.context['scadenze_event_id'] is None

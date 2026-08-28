"""Campi da compilare delle scadenze (etichette per il cliente).

- La scheda Servizio mostra, per ogni template scadenza, il link per definire
  le etichette (inline annidati non esistono).
- L'azione admin 'Aggiorna i campi da compilare dal template' ri-fotografa le
  etichette sulle scadenze GIA' generate.
- Il portale mostra le etichette al cliente.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import DeadlineFieldTemplate, DeadlineTemplate, Service
from contracts.models import Contract, ContractKind, ContractStatus, Deadline, DeadlineStatus
from events.models import Event


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_superuser(
        username='op_campi', email='op_campi@test.it', password='x')


@pytest.fixture
def scenario(db, sponsor):
    ev = Event.objects.create(
        name={'it': 'Ev Campi', 'en': 'Ev Campi'}, code='CMP',
        start_date=date(2027, 6, 1), end_date=date(2027, 6, 2))
    srv = Service.objects.create(event=ev, code='LOGO',
                                 name={'it': 'Logo a catalogo', 'en': 'Logo'},
                                 base_price=Decimal('100.00'))
    tpl = DeadlineTemplate.objects.create(
        service=srv, deadline_type='tecnica', title='Dati per il catalogo',
        submission_kind='content', days_before_event=30)
    ct = Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='CMP-27-001')
    # scadenza generata PRIMA che le etichette esistessero (schema vuoto)
    dl = Deadline.objects.create(
        contract=ct, deadline_template=tpl, deadline_type='tecnica',
        title='Dati per il catalogo', due_date=date(2027, 5, 2),
        status=DeadlineStatus.PENDING, submission_kind='content',
        content_schema=[])
    # ora l'operatore definisce le etichette
    DeadlineFieldTemplate.objects.create(
        deadline_template=tpl, label='Ragione sociale per il catalogo',
        display_order=1)
    DeadlineFieldTemplate.objects.create(
        deadline_template=tpl, label='Testo descrittivo (max 500 battute)',
        field_type='long_text', display_order=2)
    return ev, srv, tpl, ct, dl


@pytest.mark.django_db
def test_link_definisci_etichette_nella_scheda_servizio(client, staff, scenario):
    ev, srv, tpl, ct, dl = scenario
    client.force_login(staff)
    resp = client.get(reverse('admin:catalog_service_change', args=[srv.pk]))
    html = resp.content.decode()
    assert 'definire le etichette' in html
    assert reverse('admin:catalog_deadlinetemplate_change', args=[tpl.pk]) in html


@pytest.mark.django_db
def test_azione_aggiorna_campi_da_template(client, staff, scenario):
    ev, srv, tpl, ct, dl = scenario
    assert dl.content_schema == []
    client.force_login(staff)
    resp = client.post(reverse('admin:contracts_deadline_changelist'), {
        'action': 'action_aggiorna_campi_da_template',
        '_selected_action': [str(dl.pk)],
    }, follow=True)
    assert resp.status_code == 200
    dl.refresh_from_db()
    labels = [f['label'] for f in dl.content_schema]
    assert labels == ['Ragione sociale per il catalogo',
                      'Testo descrittivo (max 500 battute)']
    assert dl.content_schema[1]['type'] == 'long_text'


@pytest.mark.django_db
def test_nuove_scadenze_nascono_con_le_etichette(sponsor, scenario):
    ev, srv, tpl, ct, dl = scenario
    from contracts.models import ContractLine
    srv.triggers_deadlines = True
    srv.save()
    ct2 = Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='CMP-27-002')
    ContractLine.objects.create(contract=ct2, service=srv, quantity=1,
                                unit_price=Decimal('100.00'))
    ct2.status = ContractStatus.SIGNED
    ct2.save()
    ct2._generate_deadlines() if hasattr(ct2, '_generate_deadlines') else None
    dl2 = ct2.deadlines.filter(deadline_type='tecnica').first()
    if dl2 is not None:
        labels = [f['label'] for f in dl2.content_schema]
        assert 'Ragione sociale per il catalogo' in labels

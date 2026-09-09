"""I file che il cliente carica su una scadenza devono essere visibili
DENTRO la scadenza (elenco Scadenze e scheda contratto), non solo
nell'elenco generale Documenti."""
from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from contracts.models import Contract, Deadline
from events.models import Event
from shared.models import Document


@pytest.fixture
def operatore_admin(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        username='fr_admin', email='fr_admin@valet.it', password='x')


@pytest.fixture
def scadenza_con_file(db, sponsor):
    inizio = date.today() + timedelta(days=60)
    ev = Event.objects.create(name={'it': 'Evento FR', 'en': 'FR Event'},
                              code='FR', start_date=inizio,
                              end_date=inizio + timedelta(days=1))
    c = Contract.objects.create(sponsor=sponsor, event=ev,
                                contract_number='FR-26-001')
    d = Deadline.objects.create(contract=c, title='Scadenza saldo',
                                due_date=inizio - timedelta(days=10))
    doc = Document.objects.create(
        content_type=ContentType.objects.get_for_model(Deadline),
        object_id=d.pk, document_type='sponsor_material',
        title='contabile_bonifico.pdf', file_name='contabile_bonifico.pdf',
        storage_url='/media/documents/test/contabile_bonifico.pdf',
    )
    return c, d, doc


@pytest.mark.django_db
def test_elenco_scadenze_mostra_il_file_ricevuto(client, operatore_admin,
                                                 scadenza_con_file):
    _c, _d, doc = scadenza_con_file
    client.force_login(operatore_admin)
    html = client.get(reverse('admin:contracts_deadline_changelist')).content.decode()
    assert 'contabile_bonifico.pdf' in html
    assert reverse('core:documento_apri', args=[doc.pk]) in html


@pytest.mark.django_db
def test_scheda_contratto_mostra_il_file_ricevuto(client, operatore_admin,
                                                  scadenza_con_file):
    c, _d, doc = scadenza_con_file
    client.force_login(operatore_admin)
    url = reverse('admin:contracts_contract_change', args=[c.pk])
    html = client.get(url).content.decode()
    assert reverse('core:documento_apri', args=[doc.pk]) in html


@pytest.mark.django_db
def test_scadenza_senza_file_non_mostra_link(client, operatore_admin, sponsor):
    inizio = date.today() + timedelta(days=60)
    ev = Event.objects.create(name={'it': 'Evento FR2'}, code='FR2',
                              start_date=inizio,
                              end_date=inizio + timedelta(days=1))
    c = Contract.objects.create(sponsor=sponsor, event=ev,
                                contract_number='FR2-26-001')
    Deadline.objects.create(contract=c, title='Invio banner',
                            due_date=inizio - timedelta(days=5))
    client.force_login(operatore_admin)
    html = client.get(reverse('admin:contracts_deadline_changelist')).content.decode()
    assert 'documento_apri' not in html


@pytest.mark.django_db
def test_file_nel_cestino_non_viene_mostrato(client, operatore_admin,
                                             scadenza_con_file):
    _c, _d, doc = scadenza_con_file
    doc.delete()          # cestino (soft delete)
    client.force_login(operatore_admin)
    html = client.get(reverse('admin:contracts_deadline_changelist')).content.decode()
    assert 'contabile_bonifico.pdf' not in html

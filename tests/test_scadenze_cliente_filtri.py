"""
Scadenze cliente: box riepilogo cliccabili (?stato=) e ricerca (?q=).

- ?stato=completata|dafare|ritardo filtra le righe della tabella; i
  contatori dei box restano quelli globali della selezione evento.
- ?q= filtra su ragione sociale sponsor e titolo scadenza.
- I box del riepilogo sono link che applicano il filtro.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

URL = 'core:cruscotto_scadenze_cliente'


@pytest.fixture
def staff_client(client, db):
    op = User.objects.create_user(
        username='op_scad', email='op.scad@test.it', password='x',
        is_staff=True, is_superuser=True, is_active=True)
    client.force_login(op)
    return client


@pytest.fixture
def tre_scadenze(db, sponsor):
    """Una scadenza completata, una da fare, una in ritardo (stesso evento)."""
    from catalog.models import DeadlineTemplate, Service
    from contracts.models import (
        Contract, ContractKind, ContractStatus, Deadline, DeadlineStatus,
    )
    from events.models import Event

    event = Event.objects.create(
        name={'it': 'Scad Event', 'en': 'Scad Event'}, code='SCF',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2))
    service = Service.objects.create(
        event=event, name={'it': 'Workshop'}, base_price=Decimal('100.00'))
    tpl = DeadlineTemplate.objects.create(
        service=service, deadline_type='materiali',
        title='Invio materiali', days_before_event=10)
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='SCF-26-001')

    today = timezone.now().date()

    def dl(title, **kw):
        campi = dict(
            contract=contract, deadline_template=tpl,
            deadline_type='materiali', title=title, submission_kind='file',
            due_date=today + timedelta(days=10))
        campi.update(kw)
        return Deadline.objects.create(**campi)

    completata = dl('Logo per programma',
                    status=DeadlineStatus.RECEIVED, completed_at=timezone.now())
    dafare = dl('Testo workshop')
    ritardo = dl('Slide relatore', due_date=today - timedelta(days=1))
    return completata, dafare, ritardo


def _titoli(resp):
    return sorted(r['titolo'] for r in resp.context['righe'])


@pytest.mark.django_db
def test_senza_filtro_mostra_tutte(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL))
    assert resp.status_code == 200
    assert len(resp.context['righe']) == 3
    assert resp.context['tot'] == 3


@pytest.mark.django_db
def test_filtro_stato_ritardo(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'stato': 'ritardo'})
    assert _titoli(resp) == ['Slide relatore']
    # i contatori dei box restano globali
    assert resp.context['tot'] == 3
    assert resp.context['in_ritardo'] == 1
    assert resp.context['completate'] == 1
    assert resp.context['da_fare'] == 1


@pytest.mark.django_db
def test_filtro_stato_completata(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'stato': 'completata'})
    assert _titoli(resp) == ['Logo per programma']


@pytest.mark.django_db
def test_filtro_stato_dafare(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'stato': 'dafare'})
    assert _titoli(resp) == ['Testo workshop']


@pytest.mark.django_db
def test_filtro_stato_non_valido_ignorato(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'stato': 'boh'})
    assert len(resp.context['righe']) == 3


@pytest.mark.django_db
def test_ricerca_per_titolo(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'q': 'slide'})
    assert _titoli(resp) == ['Slide relatore']


@pytest.mark.django_db
def test_ricerca_per_sponsor(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'q': 'Test Sponsor'})
    assert len(resp.context['righe']) == 3


@pytest.mark.django_db
def test_ricerca_e_stato_combinati(staff_client, tre_scadenze):
    resp = staff_client.get(reverse(URL), {'q': 'Test Sponsor', 'stato': 'dafare'})
    assert _titoli(resp) == ['Testo workshop']


@pytest.mark.django_db
def test_box_riepilogo_sono_link(staff_client, tre_scadenze):
    html = staff_client.get(reverse(URL)).content.decode()
    assert 'stato=ritardo' in html
    assert 'stato=completata' in html
    assert 'stato=dafare' in html

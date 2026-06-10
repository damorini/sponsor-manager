"""
#2 Avviso "materiali ricevuti" sul cruscotto home.

- materiali_da_rivedere_qs(): scadenze-materiale RICEVUTE dal cliente e non
  ancora riviste dall'operatore (materials_reviewed_at nullo o anteriore
  all'ultimo upload). Esclude pagamenti e opzioni.
- marca_materiale_rivisto(deadline): segna il materiale come visto (toglie
  l'avviso), chiamata quando l'operatore apre il dettaglio scadenza.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

from core.views import materiali_da_rivedere_qs, marca_materiale_rivisto


def _contract(sponsor):
    from events.models import Event
    from contracts.models import Contract, ContractStatus, ContractKind
    event = Event.objects.create(
        name={'it': 'M', 'en': 'M'}, code='MAT',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2))
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='MAT-26-001',
        total=Decimal('100.00'))


def _dl(contract, **kw):
    from contracts.models import Deadline, DeadlineStatus
    defaults = dict(
        contract=contract, deadline_type='consegna_materiali', title='Materiali',
        due_date=date(2026, 9, 1), submission_kind='file',
        status=DeadlineStatus.RECEIVED, completed_at=timezone.now())
    defaults.update(kw)
    return Deadline.objects.create(**defaults)


def _ids():
    return set(materiali_da_rivedere_qs().values_list('id', flat=True))


@pytest.mark.django_db
def test_received_unreviewed_material_in_qs(sponsor):
    d = _dl(_contract(sponsor), materials_reviewed_at=None)
    assert d.id in _ids()


@pytest.mark.django_db
def test_reviewed_material_not_in_qs(sponsor):
    now = timezone.now()
    d = _dl(_contract(sponsor),
            completed_at=now - timedelta(hours=1), materials_reviewed_at=now)
    assert d.id not in _ids()


@pytest.mark.django_db
def test_reupload_after_review_back_in_qs(sponsor):
    now = timezone.now()
    # rivisto un'ora fa, ma ri-caricato adesso (completed_at piu' recente)
    d = _dl(_contract(sponsor),
            materials_reviewed_at=now - timedelta(hours=1), completed_at=now)
    assert d.id in _ids()


@pytest.mark.django_db
def test_payment_deadline_excluded(sponsor):
    d = _dl(_contract(sponsor), deadline_type='pagamento_acconto',
            materials_reviewed_at=None)
    assert d.id not in _ids()


@pytest.mark.django_db
def test_pending_material_excluded(sponsor):
    from contracts.models import DeadlineStatus
    d = _dl(_contract(sponsor), status=DeadlineStatus.PENDING,
            completed_at=None, materials_reviewed_at=None)
    assert d.id not in _ids()


@pytest.mark.django_db
def test_marca_materiale_rivisto_sets_timestamp_and_clears_alert(sponsor):
    d = _dl(_contract(sponsor), materials_reviewed_at=None)
    marca_materiale_rivisto(d)
    d.refresh_from_db()
    assert d.materials_reviewed_at is not None
    assert d.id not in _ids()


@pytest.mark.django_db
def test_cruscotto_home_alert_appears_and_detail_clears_it(client, sponsor):
    """e2e: la home cruscotto mostra l'avviso; aprendo il dettaglio sparisce."""
    from django.urls import reverse
    from django.contrib.auth import get_user_model

    User = get_user_model()
    op = User.objects.create_user(
        username='op', email='op@test.it', password='x',
        is_staff=True, is_superuser=True, is_active=True)
    d = _dl(_contract(sponsor), materials_reviewed_at=None)

    client.force_login(op)
    resp = client.get(reverse('core:cruscotto_home'))
    assert resp.status_code == 200
    assert 'da rivedere' in resp.content.decode()

    # L'operatore apre il dettaglio -> l'avviso si azzera
    client.get(reverse('core:cruscotto_scadenza_dettaglio', args=[d.id]))
    d.refresh_from_db()
    assert d.materials_reviewed_at is not None
    resp2 = client.get(reverse('core:cruscotto_home'))
    assert 'da rivedere' not in resp2.content.decode()

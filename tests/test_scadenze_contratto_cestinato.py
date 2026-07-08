"""Un contratto cestinato non deve lasciare scadenze vive.

Prima: la cancellazione (cestino) liberava lo stand ma NON esonerava le
scadenze → restavano nel cruscotto «Scadenze cliente» e generavano
reminder/solleciti per contratti che non esistono più. Ora:
- Contract.delete() esonera le scadenze aperte come l'annullamento;
- il cruscotto e i task schedulati escludono comunque i contratti nel
  cestino (difesa per i dati storici).
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def contratto_con_scadenze(db, sponsor):
    from catalog.models import DeadlineTemplate, Service
    from contracts.models import Contract, ContractKind, ContractStatus, Deadline
    from events.models import Event

    event = Event.objects.create(
        name={'it': 'Trash Ev', 'en': 'Trash Ev'}, code='TRS',
        start_date=date(2026, 10, 20), end_date=date(2026, 10, 21))
    service = Service.objects.create(
        event=event, name={'it': 'Spazio'}, base_price=Decimal('100.00'))
    tpl = DeadlineTemplate.objects.create(
        service=service, deadline_type='materiali',
        title='Invio materiali', days_before_event=10)
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='TRS-26-001')
    today = timezone.now().date()
    d1 = Deadline.objects.create(
        contract=contract, deadline_template=tpl, deadline_type='materiali',
        title='Logo HD', submission_kind='file',
        due_date=today + timedelta(days=10))
    d2 = Deadline.objects.create(
        contract=contract, deadline_template=tpl, deadline_type='materiali',
        title='Slide', submission_kind='file',
        due_date=today - timedelta(days=2))
    return contract, d1, d2


@pytest.mark.django_db
def test_cestinare_il_contratto_esonera_le_scadenze(contratto_con_scadenze):
    from contracts.models import DeadlineStatus
    contract, d1, d2 = contratto_con_scadenze
    contract.delete()  # soft: nel cestino
    d1.refresh_from_db()
    d2.refresh_from_db()
    assert d1.status == DeadlineStatus.WAIVED
    assert d2.status == DeadlineStatus.WAIVED


@pytest.mark.django_db
def test_cruscotto_esclude_scadenze_di_contratti_cestinati(client, contratto_con_scadenze):
    """Anche i dati storici (scadenza rimasta PENDING su contratto gia'
    cestinato) non devono comparire nel cruscotto."""
    from django.contrib.auth import get_user_model
    from contracts.models import Contract, Deadline, DeadlineStatus
    contract, d1, d2 = contratto_con_scadenze
    contract.delete()
    # simula il dato storico: la scadenza torna PENDING nonostante il cestino
    Deadline.objects.filter(pk=d1.pk).update(status=DeadlineStatus.PENDING)

    admin_user = get_user_model().objects.create_superuser(
        username='scad_admin', email='scad_admin@test.it', password='Pass123!x')
    client.force_login(admin_user)
    resp = client.get(reverse('core:cruscotto_scadenze_cliente'))
    assert resp.status_code == 200
    titoli = [r['titolo'] for r in resp.context['righe']]
    assert 'Logo HD' not in titoli
    assert 'Slide' not in titoli


@pytest.mark.django_db
def test_reminder_non_partono_per_contratti_cestinati(contratto_con_scadenze):
    """Dato storico: scadenza PENDING con contratto nel cestino -> i task
    schedulati non devono mandare nulla."""
    from django.core import mail
    from contracts.models import Deadline, DeadlineStatus
    from contracts.tasks.scheduled import (
        check_overdue_deadlines, check_upcoming_deadlines,
    )
    contract, d1, d2 = contratto_con_scadenze
    # d1 scade tra 10 giorni (giorno di reminder), d2 e' in ritardo
    contract.delete()
    Deadline.objects.filter(pk__in=[d1.pk, d2.pk]).update(
        status=DeadlineStatus.PENDING)

    mail.outbox.clear()
    check_upcoming_deadlines()
    check_overdue_deadlines()
    assert mail.outbox == [], \
        "nessun reminder/sollecito deve partire per contratti cestinati"

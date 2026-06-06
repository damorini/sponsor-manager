"""
Generazione automatica delle scadenze alla firma del contratto.

Contract.mark_as_signed() -> _generate_deadlines(): per ogni riga con un servizio
'triggers_deadlines=True', crea un Deadline da ciascun DeadlineTemplate attivo.
due_date = event.start_date - days_before_event.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from events.models import Event
from catalog.models import Service, DeadlineTemplate
from contracts.models import Contract, ContractLine, ContractKind, ContractStatus


@pytest.mark.django_db
def test_deadlines_generated_on_sign(sponsor):
    event = Event.objects.create(
        name={'it': 'Dl Event', 'en': 'Dl Event'},
        code='DL',
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 2),
    )
    service = Service.objects.create(
        event=event,
        name={'it': 'Stand', 'en': 'Booth'},
        base_price=Decimal('500.00'),
        triggers_deadlines=True,
    )
    DeadlineTemplate.objects.create(
        service=service,
        deadline_type='materiali',
        title='Invio materiali',
        days_before_event=10,
        is_active=True,
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        contract_number='DL-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)

    contract.mark_as_signed()

    dl = contract.deadlines.filter(deadline_type='materiali').first()
    assert dl is not None, "la scadenza deve essere generata alla firma"
    assert dl.due_date == event.start_date - timedelta(days=10)


@pytest.mark.django_db
def test_no_deadlines_if_service_does_not_trigger(sponsor):
    event = Event.objects.create(
        name={'it': 'Dl Event 2', 'en': 'Dl Event 2'},
        code='DL2',
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 2),
    )
    service = Service.objects.create(
        event=event,
        name={'it': 'Gadget', 'en': 'Gadget'},
        base_price=Decimal('50.00'),
        triggers_deadlines=False,
    )
    DeadlineTemplate.objects.create(
        service=service, deadline_type='materiali',
        title='X', days_before_event=5, is_active=True,
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        contract_number='DL2-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)

    contract.mark_as_signed()

    # Nessuna scadenza "materiali" dal template (il servizio non le genera).
    # NB: le scadenze di PAGAMENTO (acconto/saldo) vengono comunque create.
    assert not contract.deadlines.filter(deadline_type='materiali').exists()

"""
Filtro admin "Cose da fare" sui Contratti: scorciatoie operative
(preventivi da inviare, in attesa firma, firmati senza scadenze,
carrelli abbandonati).
"""
import pytest
from decimal import Decimal
from datetime import date

from contracts.admin import TodoFilter


def _f(value):
    f = TodoFilter.__new__(TodoFilter)
    f.used_parameters = {} if value is None else {'todo': value}
    return f


def _setup(sponsor):
    from events.models import Event
    from contracts.models import (
        Contract, ContractKind, ContractStatus, Deadline, DeadlineStatus)
    ev, _ = Event.objects.get_or_create(
        code='TODO', defaults=dict(name={'it': 'T', 'en': 'T'},
                                   start_date=date(2026, 12, 1), end_date=date(2026, 12, 2)))

    def mk(num, kind, status):
        return Contract.objects.create(
            sponsor=sponsor, event=ev, contract_kind=kind, status=status,
            contract_number=num, total=Decimal('100.00'))

    draft_main = mk('T-26-001', ContractKind.MAIN, ContractStatus.DRAFT)
    sent = mk('T-26-002', ContractKind.MAIN, ContractStatus.SENT)
    signed_no_dl = mk('T-26-003', ContractKind.MAIN, ContractStatus.SIGNED)
    signed_with_dl = mk('T-26-004', ContractKind.MAIN, ContractStatus.SIGNED)
    Deadline.objects.create(contract=signed_with_dl, deadline_type='pagamento_acconto',
                            title='Acconto', due_date=date(2026, 9, 1),
                            status=DeadlineStatus.PENDING)
    addon_draft = mk('T-26-005', ContractKind.ADDON, ContractStatus.DRAFT)
    return dict(draft_main=draft_main, sent=sent, signed_no_dl=signed_no_dl,
                signed_with_dl=signed_with_dl, addon_draft=addon_draft)


def _ids(value, qs):
    return set(_f(value).queryset(None, qs).values_list('pk', flat=True))


@pytest.mark.django_db
def test_todo_filters(sponsor):
    from contracts.models import Contract
    c = _setup(sponsor)
    qs = Contract.objects.all()

    assert _ids('da_inviare', qs) == {c['draft_main'].pk}
    assert _ids('in_attesa_firma', qs) == {c['sent'].pk}
    assert _ids('firmati_senza_scadenze', qs) == {c['signed_no_dl'].pk}
    assert _ids('carrelli', qs) == {c['addon_draft'].pk}
    # nessun filtro -> tutti
    assert _ids(None, qs) == {v.pk for v in c.values()}

"""Regressione: ripristinare un contratto dal cestino deve RI-ASSEGNARE lo
stand. La cancellazione (soft-delete) libera lo spazio espositivo - giusto -
ma prima il restore() si limitava a togliere deleted_at: il contratto firmato
tornava vivo mentre il suo stand restava 'disponibile' e vendibile ad altri
(successo davvero con Galderma A01, 7 AITEB)."""
import pytest
from datetime import date

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event
from venues.models import Stand


@pytest.fixture
def contratto_con_stand(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Ev Restore Stand', 'en': 'Ev Restore Stand'}, code='RST',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    stand = Stand.objects.create(event=event, code='R-01', base_price=1000)
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RST-26-001',
        stand=stand,
    )
    stand.update_status_from_contract()
    stand.refresh_from_db()
    assert stand.status == 'assigned'
    return contract, stand


@pytest.mark.django_db
def test_delete_libera_lo_stand(contratto_con_stand):
    contract, stand = contratto_con_stand
    contract.delete()
    stand.refresh_from_db()
    assert stand.status == 'available'


@pytest.mark.django_db
def test_restore_riassegna_lo_stand(contratto_con_stand):
    contract, stand = contratto_con_stand
    contract.delete()
    stand.refresh_from_db()
    assert stand.status == 'available'

    contract.restore()
    contract.refresh_from_db()
    assert contract.deleted_at is None
    stand.refresh_from_db()
    assert stand.status == 'assigned', \
        "il ripristino del contratto firmato deve ri-assegnare il suo stand"

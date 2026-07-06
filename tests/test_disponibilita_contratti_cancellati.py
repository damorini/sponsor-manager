"""Regressione: i servizi a numero limitato tornano LIBERI quando il contratto
viene ANNULLATO (status cancelled) oppure CANCELLATO (soft-delete).

(Bug storico: quantity_committed escludeva solo status=cancelled, quindi un
contratto cancellato dall'admin - soft-delete, status invariato - continuava
a impegnare i pezzi per sempre.)
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from catalog.models import Service, ServiceVariant
from contracts.models import Contract, ContractKind, ContractStatus, ContractLine


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Free Event', 'en': 'Free Event'},
        code='FR', start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )


@pytest.fixture
def servizio_limitato(db, evento):
    return Service.objects.create(
        event=evento, code='LIM1', name={'it': 'Servizio unico', 'en': 'One-off'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'), total_available=1,
    )


def _contratto_con_riga(evento, sponsor, servizio, numero, variant=None):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=ContractKind.MAIN, status=ContractStatus.SIGNED,
        contract_number=numero,
    )
    ContractLine.objects.create(
        contract=c, service=servizio, service_variant=variant,
        quantity=1, unit_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
    )
    return c


@pytest.mark.django_db
def test_soft_delete_libera_il_servizio(evento, sponsor, servizio_limitato):
    c = _contratto_con_riga(evento, sponsor, servizio_limitato, 'FR-26-001')
    assert servizio_limitato.quantity_available() == 0
    c.delete()  # soft-delete (come dall'admin)
    assert servizio_limitato.quantity_available() == 1
    assert servizio_limitato.is_sold_out is False


@pytest.mark.django_db
def test_annullamento_libera_il_servizio(evento, sponsor, servizio_limitato):
    c = _contratto_con_riga(evento, sponsor, servizio_limitato, 'FR-26-002')
    assert servizio_limitato.quantity_available() == 0
    c.status = ContractStatus.CANCELLED
    c.save(update_fields=['status'])
    assert servizio_limitato.quantity_available() == 1


@pytest.mark.django_db
def test_soft_delete_libera_la_variante(evento, sponsor):
    s = Service.objects.create(
        event=evento, code='VAR1', name={'it': 'Con varianti', 'en': 'With variants'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
    )
    v = ServiceVariant.objects.create(service=s, label='Slot 9:00',
                                      base_price=Decimal('10.00'), total_available=1)
    c = _contratto_con_riga(evento, sponsor, s, 'FR-26-003', variant=v)
    assert v.quantity_available() == 0
    c.delete()
    assert v.quantity_available() == 1

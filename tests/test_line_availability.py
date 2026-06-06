"""
Regressione: la riga di contratto DEVE bloccare quantità superiori alla
disponibilità, sia a livello di SERVIZIO sia di VARIANTE.

(Bug storico: un secondo clean() sovrascriveva quello con i controlli di
disponibilità, rendendoli codice morto: nessun avviso veniva mostrato.)
"""
import pytest
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from events.models import Event
from catalog.models import Service, ServiceVariant
from contracts.models import Contract, ContractKind, ContractStatus, ContractLine


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Avail Event', 'en': 'Avail Event'},
        code='AV', start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )


@pytest.fixture
def contratto(db, evento, sponsor):
    return Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT,
        contract_number='AV-26-001',
    )


def _line(contract, service, qty, variant=None):
    return ContractLine(
        contract=contract, service=service, service_variant=variant,
        quantity=qty, unit_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
    )


@pytest.mark.django_db
def test_servizio_oltre_disponibilita_blocca(evento, contratto):
    s = Service.objects.create(
        event=evento, code='S1', name={'it': 'Servizio uno', 'en': 'Service one'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'), total_available=5,
    )
    with pytest.raises(ValidationError) as exc:
        _line(contratto, s, qty=6).clean()
    assert 'quantity' in exc.value.message_dict


@pytest.mark.django_db
def test_servizio_entro_disponibilita_ok(evento, contratto):
    s = Service.objects.create(
        event=evento, code='S2', name={'it': 'Servizio due', 'en': 'Service two'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'), total_available=5,
    )
    _line(contratto, s, qty=5).clean()  # non solleva


@pytest.mark.django_db
def test_servizio_illimitato_ok(evento, contratto):
    s = Service.objects.create(
        event=evento, code='S3', name={'it': 'Servizio tre', 'en': 'Service three'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'), total_available=None,
    )
    _line(contratto, s, qty=9999).clean()  # illimitato: ok


@pytest.mark.django_db
def test_variante_oltre_disponibilita_blocca(evento, contratto):
    s = Service.objects.create(
        event=evento, code='S4', name={'it': 'Sedia', 'en': 'Chair'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'), total_available=None,
    )
    v = ServiceVariant.objects.create(
        service=s, label='Sedia blu', base_price=Decimal('10.00'),
        total_available=10, is_active=True,
    )
    with pytest.raises(ValidationError) as exc:
        _line(contratto, s, qty=11, variant=v).clean()
    assert 'quantity' in exc.value.message_dict


@pytest.mark.django_db
def test_variante_di_altro_servizio_blocca(evento, contratto):
    s1 = Service.objects.create(
        event=evento, code='S5', name={'it': 'Tavolo', 'en': 'Table'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
    )
    s2 = Service.objects.create(
        event=evento, code='S6', name={'it': 'Sedia2', 'en': 'Chair2'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
    )
    v = ServiceVariant.objects.create(
        service=s2, label='Var X', base_price=Decimal('10.00'), is_active=True,
    )
    with pytest.raises(ValidationError) as exc:
        _line(contratto, s1, qty=1, variant=v).clean()
    assert 'service_variant' in exc.value.message_dict

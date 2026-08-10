"""
Pacchetti "Spazio espositivo" PER TIPOLOGIA di stand.
- ogni tipologia ha il suo servizio (con i suoi inclusi);
- creare uno stand crea in automatico il servizio della sua tipologia;
- la riga-stand di un contratto usa il pacchetto della tipologia dello stand.
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from venues.models import Stand, StandStatus
from catalog.models import Service, ServiceInclusion
from contracts.services.stand_line import (
    stand_service_code, get_or_create_stand_service, genera_riga_da_stand,
)


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Tipi Event', 'en': 'Types Event'},
        code='TY', start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )


def test_codice_servizio_per_tipologia():
    assert stand_service_code('') == 'SPAZIO_ESPOSITIVO'
    assert stand_service_code('desk') == 'SPAZIO_ESPOSITIVO_DESK'
    assert stand_service_code('stand') == 'SPAZIO_ESPOSITIVO_STAND'
    assert stand_service_code('Corner Premium') == 'SPAZIO_ESPOSITIVO_CORNER_PREMIUM'


@pytest.mark.django_db
def test_get_or_create_per_tipologia_idempotente(evento):
    s1 = get_or_create_stand_service(evento, 'desk')
    s2 = get_or_create_stand_service(evento, 'desk')
    assert s1.pk == s2.pk
    assert s1.code == 'SPAZIO_ESPOSITIVO_DESK'
    s_stand = get_or_create_stand_service(evento, 'stand')
    assert s_stand.pk != s1.pk
    assert s_stand.code == 'SPAZIO_ESPOSITIVO_STAND'


@pytest.mark.django_db
def test_creare_stand_crea_servizio_della_tipologia(evento):
    # il signal post_save su Stand deve creare il servizio della tipologia
    Stand.objects.create(
        event=evento, code='X-1', base_price=Decimal('1000.00'),
        status=StandStatus.AVAILABLE, stand_type='stand',
    )
    assert Service.objects.filter(
        event=evento, code='SPAZIO_ESPOSITIVO_STAND'
    ).exists()


@pytest.mark.django_db
def test_riga_stand_usa_pacchetto_della_tipologia(evento, sponsor):
    from contracts.models import Contract, ContractKind, ContractStatus

    big_stand = Stand.objects.create(
        event=evento, code='S-1', base_price=Decimal('6650.00'),
        status=StandStatus.AVAILABLE, stand_type='stand',
    )
    svc_stand = get_or_create_stand_service(evento, 'stand')
    get_or_create_stand_service(evento, 'desk')  # esiste ma con inclusi diversi

    # un incluso presente SOLO nel pacchetto 'stand'
    banner = Service.objects.create(
        event=evento, code='BAN', name={'it': 'Banner', 'en': 'Banner'},
        base_price=Decimal('0.00'),
    )
    ServiceInclusion.objects.create(parent=svc_stand, child=banner, quantity=1)

    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, stand=big_stand,
        contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT,
        contract_number='TY-26-001',
    )
    # la riga stand viene ormai creata in automatico al save del contratto
    # (Contract.save -> _sync_stand_line): una chiamata esplicita e' idempotente
    esito, _msg = genera_riga_da_stand(contract)
    assert esito in ('creata', 'gia_presente')

    codes = sorted(line.service.code for line in contract.lines.all())
    assert 'SPAZIO_ESPOSITIVO_STAND' in codes      # pacchetto della tipologia giusta
    assert 'BAN' in codes                          # incluso espanso a 0
    assert 'SPAZIO_ESPOSITIVO_DESK' not in codes   # NON il pacchetto dell'altra tipologia

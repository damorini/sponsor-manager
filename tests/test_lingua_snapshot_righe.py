"""Snapshot delle righe nella LINGUA DEL CONTRATTO.

Prima gli snapshot (nome/descrizione servizio, etichetta stand, servizi
inclusi) venivano salvati nella lingua dell'interfaccia dell'operatore
(italiano): i preventivi in inglese mostravano voci in italiano anche se
la traduzione esisteva. Ora:
- alla creazione riga lo snapshot usa contract.language;
- l'etichetta stand e' "Exhibition space" per i contratti EN;
- cambiando la lingua di un preventivo non confermato le righe vengono
  ri-tradotte (quelle personalizzate a mano restano intatte).
"""
import pytest
from datetime import date
from decimal import Decimal

from tests.test_quote_confirm import _completa_anagrafica  # noqa: F401


@pytest.fixture
def evento(db):
    from events.models import Event
    return Event.objects.create(
        name={'it': 'Lang Ev', 'en': 'Lang Ev'}, code='LG',
        start_date=date(2026, 11, 10), end_date=date(2026, 11, 11),
    )


@pytest.fixture
def servizio_bilingue(evento):
    from catalog.models import Service
    return Service.objects.create(
        event=evento, code='LG-EM',
        name={'it': 'Incontro con esperto', 'en': 'Expert meeting'},
        description={'it': 'Sala riservata', 'en': 'Private room'},
        base_price=Decimal('1000.00'),
    )


@pytest.mark.django_db
def test_snapshot_in_inglese_su_contratto_en(sponsor, evento, servizio_bilingue):
    from contracts.models import Contract, ContractKind, ContractLine
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        language='en', contract_number='LG-26-001',
    )
    line = ContractLine.objects.create(
        contract=contract, service=servizio_bilingue, quantity=1)
    assert line.service_name_snapshot == 'Expert meeting'
    assert line.service_description_snapshot == 'Private room'


@pytest.mark.django_db
def test_servizi_inclusi_in_inglese(sponsor, evento, servizio_bilingue):
    from catalog.models import Service, ServiceInclusion
    from contracts.models import Contract, ContractKind, ContractLine
    incluso = Service.objects.create(
        event=evento, code='LG-SEDIA',
        name={'it': 'Sedia standard', 'en': 'Standard chair'},
        base_price=Decimal('0.00'),
    )
    ServiceInclusion.objects.create(
        parent=servizio_bilingue, child=incluso, quantity=2)
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        language='en', contract_number='LG-26-002',
    )
    ContractLine.objects.create(
        contract=contract, service=servizio_bilingue, quantity=1)
    sub = contract.lines.exclude(service=servizio_bilingue).get()
    assert sub.service_name_snapshot == 'Standard chair'


@pytest.mark.django_db
def test_etichetta_stand_in_inglese(sponsor, evento):
    from venues.models import Stand
    from contracts.models import Contract, ContractKind
    from contracts.services.stand_line import genera_riga_da_stand
    stand = Stand.objects.create(
        event=evento, code='A02', base_price=Decimal('6650.00'))
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        language='en', contract_number='LG-26-003', stand=stand,
    )
    esito, _msg = genera_riga_da_stand(contract)
    assert esito == 'creata'
    ln = contract.lines.get(notes__contains='stand:A02')
    assert ln.service_name_snapshot == 'Exhibition space - A02'


@pytest.mark.django_db
def test_cambio_lingua_ritraduce_righe_non_personalizzate(sponsor, evento, servizio_bilingue):
    from contracts.models import Contract, ContractKind, ContractStatus, ContractLine
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        language='it', status=ContractStatus.SENT, contract_number='LG-26-004',
    )
    riga = ContractLine.objects.create(
        contract=contract, service=servizio_bilingue, quantity=1)
    assert riga.service_name_snapshot == 'Incontro con esperto'
    # riga personalizzata a mano: non va toccata
    custom = ContractLine.objects.create(
        contract=contract, service=servizio_bilingue, quantity=1,
        service_name_snapshot='Incontro VIP personalizzato')

    contract.language = 'en'
    contract.save()

    riga.refresh_from_db()
    custom.refresh_from_db()
    assert riga.service_name_snapshot == 'Expert meeting'
    assert custom.service_name_snapshot == 'Incontro VIP personalizzato'


@pytest.mark.django_db
def test_comando_riallinea_dry_run_e_apply(sponsor, evento, servizio_bilingue):
    from django.core.management import call_command
    from io import StringIO
    from contracts.models import Contract, ContractKind, ContractStatus, ContractLine
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        language='en', status=ContractStatus.SENT, contract_number='LG-26-005',
    )
    # simula il dato storico sbagliato: snapshot in italiano su contratto EN
    riga = ContractLine.objects.create(
        contract=contract, service=servizio_bilingue, quantity=1,
        service_name_snapshot='Incontro con esperto')

    out = StringIO()
    call_command('riallinea_lingua_righe', '--dry-run', stdout=out)
    riga.refresh_from_db()
    assert riga.service_name_snapshot == 'Incontro con esperto'  # non toccato
    assert 'Expert meeting' in out.getvalue()

    call_command('riallinea_lingua_righe', stdout=StringIO())
    riga.refresh_from_db()
    assert riga.service_name_snapshot == 'Expert meeting'

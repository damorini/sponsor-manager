"""
Bug fix Contract.save(): _sync_option_deadline e _sync_stand_line
venivano chiamate DOPO raise last_err (dead code) e non su nessun
altro path — contratti nuovi non generavano la scadenza-opzione
né la riga-stand al primo salvataggio.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta


@pytest.fixture
def evento(db):
    from events.models import Event
    return Event.objects.create(
        name={'it': 'Sync Ev', 'en': 'Sync Ev'}, code='SYNC',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )


@pytest.fixture
def stand_con_prezzo(db, evento):
    """Stand con base_price (sufficiente per _stand_price_and_label)."""
    from venues.models import Stand
    return Stand.objects.create(
        code='A1', event=evento,
        width_meters=Decimal('3.00'), depth_meters=Decimal('3.00'),
        base_price=Decimal('500.00'),
    )


@pytest.mark.django_db
def test_nuovo_contratto_genera_scadenza_opzione(db, evento, stand_con_prezzo, sponsor):
    """Nuovo contratto DRAFT con option_until + stand → scadenza_opzione creata al 1° save."""
    from contracts.models import Contract, ContractStatus, ContractKind, Deadline

    scadenza_opzione = date.today() + timedelta(days=10)
    c = Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        stand=stand_con_prezzo,
        option_until=scadenza_opzione,
        deposit_percent=Decimal('30'),
    )

    d = Deadline.objects.filter(contract=c, deadline_type='scadenza_opzione').first()
    assert d is not None, "scadenza_opzione non creata al 1° salvataggio"
    assert d.due_date == scadenza_opzione


@pytest.mark.django_db
def test_nuovo_contratto_genera_riga_stand(db, evento, stand_con_prezzo, sponsor):
    """Nuovo contratto DRAFT con stand → ContractLine stand creata al 1° save."""
    from contracts.models import Contract, ContractStatus, ContractKind

    c = Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        stand=stand_con_prezzo,
        deposit_percent=Decimal('30'),
    )

    righe_stand = c.lines.filter(notes__startswith='stand:')
    assert righe_stand.exists(), "riga stand non creata al 1° salvataggio"


@pytest.mark.django_db
def test_contratto_senza_stand_no_riga_stand(db, evento, sponsor):
    """Contratto senza stand: nessuna riga stand creata."""
    from contracts.models import Contract, ContractStatus, ContractKind

    c = Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        deposit_percent=Decimal('30'),
    )
    assert not c.lines.filter(notes__startswith='stand:').exists()


@pytest.mark.django_db
def test_contratto_senza_option_no_scadenza_opzione(db, evento, sponsor):
    """Contratto senza option_until: nessuna scadenza_opzione creata."""
    from contracts.models import Contract, ContractStatus, ContractKind, Deadline

    c = Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        deposit_percent=Decimal('30'),
    )
    assert not Deadline.objects.filter(contract=c, deadline_type='scadenza_opzione').exists()

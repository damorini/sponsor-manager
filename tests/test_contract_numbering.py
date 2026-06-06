"""
Regression: i contratti ADDON (carrelli) ottengono numeri auto-generati e unici.

Storico (STATO_PROGETTO.md #1): contract_number e' unique=True ma in passato
NON veniva generato per i contratti ADDON. Restavano con number='' e il secondo
carrello dello stesso sponsor/evento andava in crash per collisione di unicita'.
La numerazione automatica vive ora in Contract.save() / _generate_contract_number().
"""
import pytest
from datetime import date

from events.models import Event
from contracts.models import Contract, ContractKind, ContractStatus


@pytest.mark.django_db
def test_addon_contracts_get_unique_auto_numbers(sponsor):
    """Due ADDON per lo stesso sponsor/evento: numeri auto-generati e diversi.

    Prima del fix questo test sollevava IntegrityError sul secondo create().
    """
    event = Event.objects.create(
        name={'it': 'Regress Event', 'en': 'Regress Event'},
        code='REG',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )

    def make_addon():
        return Contract.objects.create(
            sponsor=sponsor,
            event=event,
            contract_kind=ContractKind.ADDON,
            status=ContractStatus.DRAFT,
        )

    c1 = make_addon()
    c2 = make_addon()

    assert c1.contract_number, "il primo ADDON deve avere un numero"
    assert c2.contract_number, "il secondo ADDON deve avere un numero"
    assert c1.contract_number != c2.contract_number, "i numeri devono essere unici"

    # Formato SIGLA-AA-NNN (es. REG-26-001 / REG-26-002)
    assert c1.contract_number.startswith('REG-26-')
    assert c2.contract_number.startswith('REG-26-')


@pytest.mark.django_db
def test_contract_number_preserved_if_explicit(sponsor):
    """Se il numero e' fornito esplicitamente, save() non lo sovrascrive."""
    event = Event.objects.create(
        name={'it': 'Regress Event 2', 'en': 'Regress Event 2'},
        code='REG2',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )
    c = Contract.objects.create(
        sponsor=sponsor,
        event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT,
        contract_number='CUSTOM-001',
    )
    assert c.contract_number == 'CUSTOM-001'


@pytest.mark.django_db
def test_save_riprova_su_collisione_numero(sponsor, monkeypatch):
    """Se due contratti generano lo stesso numero (race), il secondo rigenera
    e si salva comunque (nessun IntegrityError propagato)."""
    event = Event.objects.create(
        name={'it': 'Race Event', 'en': 'Race Event'},
        code='RACE', start_date=date(2026, 6, 1), end_date=date(2026, 6, 2),
    )
    first = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.ADDON, status=ContractStatus.DRAFT,
    )
    used = first.contract_number

    orig = Contract._generate_contract_number
    calls = {'n': 0}

    def fake(self):
        calls['n'] += 1
        if calls['n'] == 1:
            return used  # forza una collisione al primo tentativo
        return orig(self)

    monkeypatch.setattr(Contract, '_generate_contract_number', fake)

    second = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.ADDON, status=ContractStatus.DRAFT,
    )
    assert second.pk is not None
    assert second.contract_number != used
    assert calls['n'] >= 2  # ha dovuto rigenerare almeno una volta

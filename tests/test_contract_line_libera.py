"""Regressione: una ContractLine puo' esistere SENZA un Service a catalogo
('riga libera'), per richieste specifiche del cliente non standard - solo
descrizione libera, quantita' e prezzo, nessun controllo di
quantita'/disponibilita' di catalogo. Puo' essere usata piu' volte nello
stesso contratto (piu' righe libere indipendenti)."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from events.models import Event


@pytest.fixture
def contratto(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Ev Riga Libera', 'en': 'Ev Riga Libera'}, code='RL',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='RL-26-001',
    )


@pytest.mark.django_db
def test_riga_libera_si_crea_senza_servizio(contratto):
    riga = ContractLine.objects.create(
        contract=contratto, service=None,
        custom_description='Traduzione simultanea inglese-italiano',
        quantity=2, unit_price=Decimal('350.00'),
    )
    riga.refresh_from_db()
    assert riga.service_id is None
    assert riga.service_name_snapshot == 'Traduzione simultanea inglese-italiano'
    assert riga.line_subtotal == Decimal('700.00')


@pytest.mark.django_db
def test_riga_libera_senza_descrizione_e_bloccata(contratto):
    riga = ContractLine(
        contract=contratto, service=None, quantity=1, unit_price=Decimal('100.00'),
    )
    with pytest.raises(ValidationError):
        riga.clean()


@pytest.mark.django_db
def test_riga_libera_senza_prezzo_e_bloccata(contratto):
    riga = ContractLine(
        contract=contratto, service=None, custom_description='Servizio extra',
        quantity=1,
    )
    with pytest.raises(ValidationError):
        riga.clean()


@pytest.mark.django_db
def test_riga_libera_nessun_controllo_quantita_massima(contratto):
    """Una riga a catalogo con max_quantity=1 blocca quantity=5; una riga
    LIBERA con lo stesso valore invece passa senza problemi."""
    servizio = Service.objects.create(
        event=contratto.event, code='UNICO', name={'it': 'Pezzo unico', 'en': 'Unique'},
        base_price=Decimal('50.00'), max_quantity=1,
    )
    riga_catalogo = ContractLine(
        contract=contratto, service=servizio, quantity=5, unit_price=Decimal('50.00'),
    )
    with pytest.raises(ValidationError):
        riga_catalogo.clean()

    riga_libera = ContractLine(
        contract=contratto, service=None, custom_description='Richiesta speciale',
        quantity=5, unit_price=Decimal('50.00'),
    )
    riga_libera.clean()  # non deve sollevare


@pytest.mark.django_db
def test_piu_righe_libere_nello_stesso_contratto(contratto):
    ContractLine.objects.create(
        contract=contratto, service=None, custom_description='Voce A',
        quantity=1, unit_price=Decimal('100.00'),
    )
    ContractLine.objects.create(
        contract=contratto, service=None, custom_description='Voce B',
        quantity=3, unit_price=Decimal('20.00'),
    )
    righe = list(contratto.lines.filter(service__isnull=True).order_by('created_at'))
    assert len(righe) == 2
    assert righe[0].service_name_snapshot == 'Voce A'
    assert righe[1].service_name_snapshot == 'Voce B'

    contratto.refresh_from_db()
    assert contratto.subtotal == Decimal('160.00')  # 100 + 3*20

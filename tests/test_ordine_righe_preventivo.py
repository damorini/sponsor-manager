"""Regressione: l'ordine delle righe nel preventivo/allegato e' PRIMA per
economia (importo decrescente, poi le incluse) - COME SEMPRE - a meno che
l'operatore non forzi un display_order manuale su alcune righe, nel qual
caso quello vince e le altre righe (tutte a display_order=0, il default)
restano ordinate come prima tra loro."""
from datetime import date
from decimal import Decimal

import pytest

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from contracts.services.pdf_generator import _righe_valorizzate_prima
from events.models import Event


@pytest.fixture
def contratto(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Ev Ordine Righe', 'en': 'Ev Ordine Righe'}, code='ORD',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='ORD-26-001',
    )


def _riga(contratto, nome, prezzo, display_order=0):
    servizio = Service.objects.create(
        event=contratto.event, code=nome.upper().replace(' ', '_')[:20],
        name={'it': nome, 'en': nome}, base_price=prezzo,
    )
    return ContractLine.objects.create(
        contract=contratto, service=servizio, quantity=1, unit_price=prezzo,
        display_order=display_order,
    )


@pytest.mark.django_db
def test_senza_display_order_ordina_per_importo_come_prima(contratto):
    a = _riga(contratto, 'Piccola', Decimal('100'))
    b = _riga(contratto, 'Grande', Decimal('500'))
    c = _riga(contratto, 'Inclusa', Decimal('0'))
    ordinate = _righe_valorizzate_prima(contratto.lines.all())
    assert [r.id for r in ordinate] == [b.id, a.id, c.id]


@pytest.mark.django_db
def test_display_order_forza_alcune_righe_in_fondo(contratto):
    grande = _riga(contratto, 'Grande', Decimal('500'))
    piccola = _riga(contratto, 'Piccola', Decimal('100'))
    forzata_1 = _riga(contratto, 'Forzata prima', Decimal('50'), display_order=1)
    forzata_2 = _riga(contratto, 'Forzata seconda', Decimal('9999'), display_order=2)
    ordinate = _righe_valorizzate_prima(contratto.lines.all())
    # le due righe SENZA display_order (0, default) restano ordinate per
    # importo tra loro e vengono PRIMA; le due forzate chiudono, nell'ORDINE
    # scelto (1, poi 2) indipendentemente dal loro importo.
    assert [r.id for r in ordinate] == [grande.id, piccola.id, forzata_1.id, forzata_2.id]

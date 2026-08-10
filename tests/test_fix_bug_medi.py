"""Regressioni per i bug MEDI dell'audit di luglio:

1. cambio stand su contratto esistente: la riga del vecchio stand viene
   rimossa (prima restava -> preventivo con DUE stand)
2. conferma pagamento su contratto ACTIVE/COMPLETED: no-op idempotente,
   niente ValidationError/500 in admin
3. webhook rimborso PayPal: capture_id letto dal link rel='up' (il primo
   link e' il self del RIMBORSO) + fallback custom_id
4. riattivare vat_applicable ricalcola l'IVA delle righe
5. prezzo/aliquota 0 ESPLICITI su riga nuova non vengono sostituiti dal listino
6. pagina Pagamenti del portale: bottone 'Paga ora' sulle scadenze aperte
"""
import json
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
from events.models import Event
from venues.models import Stand


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Bug Medi', 'en': 'Ev Bug Medi'}, code='BGM',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )


# ---------------------------------------------------------------------------
# 1: cambio stand
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cambio_stand_rimuove_la_riga_vecchia(sponsor, evento):
    stand_a = Stand.objects.create(event=evento, code='BG-A', base_price=Decimal('5000.00'))
    stand_b = Stand.objects.create(event=evento, code='BG-B', base_price=Decimal('3000.00'))
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, stand=stand_a,
    )
    assert contract.lines.filter(notes__startswith='stand:BG-A').exists()

    contract.stand = stand_b
    contract.save()

    assert not contract.lines.filter(notes__startswith='stand:BG-A').exists(), \
        "la riga del VECCHIO stand deve sparire quando si cambia stand"
    assert contract.lines.filter(notes__startswith='stand:BG-B').exists()
    contract.refresh_from_db()
    assert contract.subtotal == Decimal('3000.00'), \
        "il totale deve riflettere SOLO il nuovo stand, non la somma dei due"


@pytest.mark.django_db
def test_rimozione_stand_toglie_la_riga(sponsor, evento):
    stand_a = Stand.objects.create(event=evento, code='BG-C', base_price=Decimal('5000.00'))
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, stand=stand_a,
    )
    contract.stand = None
    contract.save()
    assert not contract.lines.filter(notes__startswith='stand:').exists()


# ---------------------------------------------------------------------------
# 2: conferma pagamento su contratto gia' attivo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_conferma_bonifico_su_contratto_attivo_non_crasha(sponsor, evento):
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='BGM-26-002',
        total=Decimal('1000.00'),
    )
    p = Payment.objects.create(
        contract=contract, payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('1000.00'), status=PaymentStatus.PENDING,
    )
    p.mark_succeeded()  # prima: ValidationError -> 500 in admin
    p.refresh_from_db()
    contract.refresh_from_db()
    assert p.status == PaymentStatus.SUCCEEDED
    assert contract.status == ContractStatus.ACTIVE  # lo stato non regredisce


# ---------------------------------------------------------------------------
# 3: webhook rimborso
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_refund_webhook_trova_il_pagamento_dal_link_up(sponsor, evento):
    from contracts.views.checkout import _handle_capture_refunded
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='BGM-26-003',
        total=Decimal('500.00'),
    )
    p = Payment.objects.create(
        contract=contract, payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=Decimal('500.00'), status=PaymentStatus.SUCCEEDED,
        paypal_capture_id='CAP-XYZ-1',
    )
    # payload realistico: primo link = self del RIMBORSO, poi rel='up' verso la capture
    resource = {
        'id': 'REFUND-1', 'amount': {'value': '500.00'},
        'links': [
            {'rel': 'self', 'href': 'https://api.paypal.com/v2/payments/refunds/REFUND-1'},
            {'rel': 'up', 'href': 'https://api.paypal.com/v2/payments/captures/CAP-XYZ-1'},
        ],
    }
    resp = _handle_capture_refunded('EVT-REFUND-1', resource)
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.status == PaymentStatus.REFUNDED, \
        "il rimborso fatto dal pannello PayPal deve registrarsi sul Payment"


# ---------------------------------------------------------------------------
# 4: riattivazione IVA
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_riattivare_iva_ricalcola_le_righe(sponsor, evento):
    service = Service.objects.create(
        event=evento, code='BG-SRV', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('1000.00'), vat_rate=Decimal('22.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='BGM-26-004',
        vat_applicable=False,
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)
    contract.refresh_from_db()
    assert contract.vat_amount == Decimal('0.00')

    contract.vat_applicable = True
    contract.save()
    contract.refresh_from_db()
    assert contract.vat_amount == Decimal('220.00'), \
        "riattivare l'IVA deve ricalcolare line_vat e vat_amount"
    assert contract.total == Decimal('1220.00')

    # e viceversa: disattivarla azzera
    contract.vat_applicable = False
    contract.save()
    contract.refresh_from_db()
    assert contract.vat_amount == Decimal('0.00')
    assert contract.total == Decimal('1000.00')


# ---------------------------------------------------------------------------
# 5: prezzo 0 esplicito
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_prezzo_zero_esplicito_resta_zero(sponsor, evento):
    service = Service.objects.create(
        event=evento, code='BG-OMG', name={'it': 'Omaggio', 'en': 'Gift'},
        base_price=Decimal('300.00'), vat_rate=Decimal('22.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='BGM-26-005',
    )
    riga = ContractLine.objects.create(
        contract=contract, service=service, quantity=1,
        unit_price=Decimal('0.00'),  # omaggio concordato
    )
    riga.refresh_from_db()
    assert riga.unit_price == Decimal('0.00'), \
        "un prezzo 0 esplicito (omaggio) non deve tornare a listino"
    assert riga.line_subtotal == Decimal('0.00')


# ---------------------------------------------------------------------------
# 6: bottone Paga ora
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pagina_pagamenti_mostra_paga_ora(client, user_sponsor, sponsor, contact, evento):
    from contracts.models import Deadline, DeadlineStatus
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='BGM-26-006',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'),
    )
    Deadline.objects.create(
        contract=contract, deadline_type='pagamento_saldo',
        title='Scadenza saldo', due_date=date(2026, 11, 1),
        status=DeadlineStatus.PENDING,
    )
    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:payments'))
    html = resp.content.decode()
    assert 'Paga ora' in html
    assert reverse('portal:paga_scadenza', args=[contract.id]) in html

    # scadenza pagata: niente bottone
    contract.deadlines.update(status=DeadlineStatus.RECEIVED)
    resp = client.get(reverse('portal:payments'))
    assert 'Paga ora' not in resp.content.decode()

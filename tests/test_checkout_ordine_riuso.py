"""Riuso sicuro dell'ordine PayPal nel checkout.

Il Payment PENDING viene riusato tra una visita e l'altra, ma l'ordine
PayPal associato puo' essere rimasto a meta' (es. tentativo MyBank
abbandonato -> PAYER_ACTION_REQUIRED) o scaduto: riproporlo identico fa
fallire il popup con "si e' verificato un errore nel sistema" a ogni
tentativo. La pagina ora riusa l'ordine SOLO se ancora CREATED,
altrimenti ne genera uno nuovo.
"""
import pytest
from django.urls import reverse

from tests.test_payment_success import addon_cart  # noqa: F401


def _pending_payment(contract, order_id):
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    from contracts.views._payment_helpers import compute_due_amount
    return Payment.objects.create(
        contract=contract,
        status=PaymentStatus.PENDING,
        payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=compute_due_amount(contract),
        currency='EUR',
        paypal_order_id=order_id,
    )


@pytest.mark.django_db
def test_ordine_non_vergine_viene_rigenerato(client, user_sponsor, addon_cart, monkeypatch):
    payment = _pending_payment(addon_cart, 'STALE-123')

    monkeypatch.setattr(
        'contracts.services.paypal_service.get_paypal_order_status',
        lambda oid: 'PAYER_ACTION_REQUIRED')

    def fake_create(p, **kw):
        p.paypal_order_id = 'FRESH-456'
        p.save(update_fields=['paypal_order_id'])
        return {'id': 'FRESH-456'}
    monkeypatch.setattr(
        'contracts.services.paypal_service.create_paypal_order', fake_create)

    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:checkout_card', args=[addon_cart.id]))
    assert resp.status_code == 200

    payment.refresh_from_db()
    assert payment.paypal_order_id == 'FRESH-456'
    assert b'FRESH-456' in resp.content


@pytest.mark.django_db
def test_ordine_vergine_viene_riusato(client, user_sponsor, addon_cart, monkeypatch):
    payment = _pending_payment(addon_cart, 'GOOD-789')

    monkeypatch.setattr(
        'contracts.services.paypal_service.get_paypal_order_status',
        lambda oid: 'CREATED')

    def esplodi(p, **kw):
        raise AssertionError('non deve creare un nuovo ordine se CREATED')
    monkeypatch.setattr(
        'contracts.services.paypal_service.create_paypal_order', esplodi)

    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:checkout_card', args=[addon_cart.id]))
    assert resp.status_code == 200

    payment.refresh_from_db()
    assert payment.paypal_order_id == 'GOOD-789'

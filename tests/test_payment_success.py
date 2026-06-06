"""
Success path del pagamento ecommerce, senza chiamare PayPal.

In sviluppo (DEBUG=True) l'endpoint checkout_dev_mark_paid simula un pagamento
riuscito: registra un Payment SUCCEEDED e firma il contratto ADDON.
Copre la stessa transizione del ritorno PayPal reale.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse

from sponsors.models import Contact
from events.models import Event
from catalog.models import Service
from contracts.models import Contract, ContractLine, ContractKind, ContractStatus
from contracts.payments import PaymentStatus


@pytest.fixture
def addon_cart(db, user_sponsor, sponsor):
    Contact.objects.create(
        portal_user=user_sponsor, sponsor=sponsor,
        full_name='Mario Rossi', email='mario@test.it',
    )
    event = Event.objects.create(
        name={'it': 'Pay Event', 'en': 'Pay Event'},
        code='PAY', start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    service = Service.objects.create(
        event=event, name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('100.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.ADDON,
        status=ContractStatus.DRAFT,
        contract_number='PAY-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)
    return contract


@pytest.mark.django_db
def test_dev_mark_paid_registers_payment_and_signs(client, user_sponsor, addon_cart, settings):
    settings.DEBUG = True  # dev_mark_paid e' disponibile solo con DEBUG=True
    client.force_login(user_sponsor)
    url = reverse('portal:checkout_dev_mark_paid', args=[addon_cart.id])
    resp = client.post(url)

    assert resp.status_code == 302
    addon_cart.refresh_from_db()
    # Un pagamento riuscito esiste e il contratto non e' piu' in bozza/attesa.
    assert addon_cart.payments.filter(status=PaymentStatus.SUCCEEDED).exists()
    assert addon_cart.status in (ContractStatus.SIGNED, ContractStatus.ACTIVE)


@pytest.mark.django_db
def test_dev_mark_paid_forbidden_for_non_owner(client, addon_cart, settings):
    settings.DEBUG = True
    from django.contrib.auth import get_user_model
    from users.models import UserRole
    User = get_user_model()
    intruder = User.objects.create_user(
        username='intruso2', email='intruso2@test.it',
        password='TestPassword123!', is_active=True,
    )
    intruder.role = UserRole.SPONSOR
    intruder.save()

    client.force_login(intruder)
    url = reverse('portal:checkout_dev_mark_paid', args=[addon_cart.id])
    assert client.post(url).status_code == 403

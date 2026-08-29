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
        roles=['operational'],
    )
    # anagrafica di fatturazione completa: dal 29/08 le view di avvio
    # pagamento applicano lo stesso gate acquisti del portale
    for campo, valore in [
        ('vat_number', '01234567890'), ('sdi_code', '0000000'),
        ('pec_email', 'pec@test.it'), ('address_street', 'Via Test 1'),
        ('address_city', 'Bologna'), ('address_zip', '40100'),
        ('address_province', 'BO'), ('address_country', 'Italia'),
        ('website', 'https://test.it'), ('business_description', 'Test'),
    ]:
        if not getattr(sponsor, campo, None):
            setattr(sponsor, campo, valore)
    sponsor.save()
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


def _enable_debug_without_toolbar(settings):
    """dev_mark_paid richiede DEBUG=True, ma attivarlo accende anche il Debug
    Toolbar (le cui URL 'djdt' non sono registrate -> NoReverseMatch). Lo tolgo."""
    settings.DEBUG = True
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if 'debug_toolbar' not in m]


@pytest.mark.django_db
def test_dev_mark_paid_registers_payment_and_signs(client, user_sponsor, addon_cart, settings):
    _enable_debug_without_toolbar(settings)
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
    _enable_debug_without_toolbar(settings)
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

"""
End-to-end del pagamento con BONIFICO dal checkout del portale.

Flusso (contracts/views/checkout.py: bank_transfer_order):
  POST portal:checkout_bank_transfer(contract_id)
    - contratto ADDON in DRAFT con almeno una riga -> DRAFT -> PENDING_PAYMENT
    - carrello vuoto -> redirect al carrello, nessun cambio di stato
    - solo POST (GET -> 405); solo il proprietario (altri -> 403)
  L'incasso viene poi registrato a mano dall'admin.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.contrib.auth import get_user_model

from sponsors.models import Contact
from events.models import Event
from catalog.models import Service
from contracts.models import Contract, ContractLine, ContractKind, ContractStatus

User = get_user_model()


@pytest.fixture
def addon_cart(db, user_sponsor, sponsor):
    """Sponsor con Contact collegato e un carrello ADDON (DRAFT)."""
    Contact.objects.create(
        portal_user=user_sponsor,
        sponsor=sponsor,
        full_name='Mario Rossi',
        email='mario@test.it',
        roles=['operational'],
    )
    # gate acquisti (29/08): l'avvio pagamento richiede anagrafica completa
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
    # Date RELATIVE a oggi: con date fisse il test invecchia e, passata la
    # data, il blocco "evento concluso" lo fa fallire senza che nulla si sia
    # rotto davvero.
    from datetime import timedelta
    inizio = date.today() + timedelta(days=90)
    event = Event.objects.create(
        name={'it': 'BT Event', 'en': 'BT Event'},
        code='BT',
        start_date=inizio,
        end_date=inizio + timedelta(days=1),
    )
    service = Service.objects.create(
        event=event,
        name={'it': 'Servizio X', 'en': 'Service X'},
        base_price=Decimal('100.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor,
        event=event,
        contract_kind=ContractKind.ADDON,
        status=ContractStatus.DRAFT,
        contract_number='BT-26-001',
    )
    return contract, service


@pytest.mark.django_db
class TestBankTransfer:
    def test_moves_to_pending_payment(self, client, user_sponsor, addon_cart):
        """Carrello ADDON con righe: il bonifico porta a 'In attesa pagamento'."""
        contract, service = addon_cart
        ContractLine.objects.create(contract=contract, service=service, quantity=1)

        client.force_login(user_sponsor)
        url = reverse('portal:checkout_bank_transfer', args=[contract.id])
        resp = client.post(url)

        assert resp.status_code == 302
        contract.refresh_from_db()
        assert contract.status == ContractStatus.PENDING_PAYMENT

    def test_empty_cart_does_not_change_status(self, client, user_sponsor, addon_cart):
        """Carrello vuoto: redirect e nessun passaggio di stato."""
        contract, _service = addon_cart  # nessuna riga aggiunta

        client.force_login(user_sponsor)
        url = reverse('portal:checkout_bank_transfer', args=[contract.id])
        resp = client.post(url)

        assert resp.status_code == 302
        contract.refresh_from_db()
        assert contract.status == ContractStatus.DRAFT

    def test_requires_post(self, client, user_sponsor, addon_cart):
        """L'endpoint accetta solo POST (GET -> 405)."""
        contract, _service = addon_cart
        client.force_login(user_sponsor)
        url = reverse('portal:checkout_bank_transfer', args=[contract.id])
        assert client.get(url).status_code == 405

    def test_forbidden_for_non_owner(self, client, addon_cart):
        """Un utente che non possiede il contratto riceve 403."""
        contract, _service = addon_cart
        intruder = User.objects.create_user(
            username='intruso', email='intruso@test.it',
            password='TestPassword123!', is_active=True,
        )
        from users.models import UserRole
        intruder.role = UserRole.SPONSOR
        intruder.save()

        client.force_login(intruder)
        url = reverse('portal:checkout_bank_transfer', args=[contract.id])
        resp = client.post(url)
        assert resp.status_code == 403

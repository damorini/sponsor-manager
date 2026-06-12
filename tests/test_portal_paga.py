"""
Funzionalità "Paga acconto/saldo" nel portale per contratti SIGNED/ACTIVE.

- Bottone "Paga acconto" visibile in contract_detail per SIGNED con acconto dovuto
- Bottone "Paga saldo" visibile in contract_detail per SIGNED con saldo dovuto
- GET paga_scadenza mostra importo e opzioni di pagamento
- POST paga_scadenza con metodo=bonifico crea Payment PENDING BANK_TRANSFER
- Contratto già saldato: nessun bottone e redirect diretto dalla paga_scadenza
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse


@pytest.fixture
def sponsor_user(db):
    from django.contrib.auth import get_user_model
    from users.models import UserRole
    User = get_user_model()
    u = User.objects.create_user(
        username='sp_paga', email='sp_paga@test.it',
        password='x', is_active=True,
    )
    u.role = UserRole.SPONSOR
    u.save()
    return u


@pytest.fixture
def sponsor_con_contatto(db, sponsor_user):
    from sponsors.models import Sponsor, Contact, ContactRole
    from django.utils import timezone
    sp = Sponsor.objects.create(
        legal_name='Sponsor Paga Srl',
        vat_number='99999999999',
        sdi_code='0000000',
        pec_email='paga@pec.it',
        address_street='Via Test 1',
        address_city='Milano',
        address_zip='20100',
        address_province='MI',
        address_country='IT',
        website='https://pagasrl.it',
        business_description='Test',
    )
    from core.models import OrganizerSettings
    Contact.objects.create(
        portal_user=sponsor_user, sponsor=sp,
        full_name='Test Contact',
        email='sp_paga@test.it',
        roles=[ContactRole.OPERATIONAL],
        privacy_accepted_at=timezone.now(),
        privacy_policy_version=OrganizerSettings.load().privacy_policy_version or '1.0',
    )
    return sp


@pytest.fixture
def evento(db):
    from events.models import Event
    return Event.objects.create(
        name={'it': 'Paga Ev', 'en': 'Paga Ev'}, code='PAG1',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )


@pytest.fixture
def contratto_signed_con_acconto(db, sponsor_con_contatto, evento):
    from contracts.models import Contract, ContractStatus, ContractKind
    return Contract.objects.create(
        sponsor=sponsor_con_contatto, event=evento,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED,
        contract_number='PAG1-26-001',
        total=Decimal('1000.00'),
        deposit_percent=Decimal('30'),
        signed_date=date(2026, 5, 1),
    )


# ── 1. Bottone nel detail ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_detail_mostra_bottone_paga_acconto(client, sponsor_user, contratto_signed_con_acconto):
    """contract_detail mostra "Paga acconto" quando l'acconto non è stato pagato."""
    client.force_login(sponsor_user)
    url = reverse('portal:contract_detail', args=[contratto_signed_con_acconto.id])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Paga acconto' in html or 'paga_scadenza' in html


@pytest.mark.django_db
def test_detail_mostra_bottone_paga_saldo(client, sponsor_user, contratto_signed_con_acconto):
    """contract_detail mostra "Paga saldo" quando l'acconto è stato pagato."""
    from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
    Payment.objects.create(
        contract=contratto_signed_con_acconto,
        payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('300.00'),
        status=PaymentStatus.SUCCEEDED,
    )
    client.force_login(sponsor_user)
    url = reverse('portal:contract_detail', args=[contratto_signed_con_acconto.id])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Paga saldo' in html or 'paga_scadenza' in html


@pytest.mark.django_db
def test_detail_nessun_bottone_paga_se_saldato(client, sponsor_user, contratto_signed_con_acconto):
    """Nessun bottone di pagamento se il contratto è già saldato."""
    from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
    Payment.objects.create(
        contract=contratto_signed_con_acconto,
        payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('1000.00'),
        status=PaymentStatus.SUCCEEDED,
    )
    client.force_login(sponsor_user)
    url = reverse('portal:contract_detail', args=[contratto_signed_con_acconto.id])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'paga_scadenza' not in html


# ── 2. GET paga_scadenza ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_paga_scadenza_mostra_importo(client, sponsor_user, contratto_signed_con_acconto):
    """GET paga_scadenza: mostra l'importo acconto e le opzioni di pagamento."""
    client.force_login(sponsor_user)
    url = reverse('portal:paga_scadenza', args=[contratto_signed_con_acconto.id])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert '300' in html  # € 300.00 (30% di 1000)
    assert 'bonifico' in html.lower() or 'Bonifico' in html


# ── 3. POST bonifico ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_post_bonifico_crea_payment_pending(client, sponsor_user, contratto_signed_con_acconto):
    """POST paga_scadenza con metodo=bonifico crea un Payment PENDING BANK_TRANSFER."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    client.force_login(sponsor_user)
    url = reverse('portal:paga_scadenza', args=[contratto_signed_con_acconto.id])
    resp = client.post(url, {'metodo': 'bonifico'})
    assert resp.status_code == 302
    p = Payment.objects.filter(
        contract=contratto_signed_con_acconto,
        status=PaymentStatus.PENDING,
        payment_method=PaymentMethodChoice.BANK_TRANSFER,
    ).first()
    assert p is not None
    assert p.amount_gross == Decimal('300.00')


# ── 4. Redirect se già saldato ─────────────────────────────────────────────

@pytest.mark.django_db
def test_paga_scadenza_redirect_se_saldato(client, sponsor_user, contratto_signed_con_acconto):
    """paga_scadenza redirige al detail se il contratto è già saldato."""
    from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
    Payment.objects.create(
        contract=contratto_signed_con_acconto,
        payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('1000.00'),
        status=PaymentStatus.SUCCEEDED,
    )
    client.force_login(sponsor_user)
    url = reverse('portal:paga_scadenza', args=[contratto_signed_con_acconto.id])
    resp = client.get(url)
    assert resp.status_code == 302

"""
Cruscotto finanziario operatore:
- Card "Bonifici in attesa": conteggio Payment PENDING + method=bank_transfer per evento
- Card "Email fallite": conteggio Communication FAILED collegate ai contratti dell'evento
- View "Registra incasso": POST crea Payment(SUCCEEDED) e riconcilia scadenze
"""
import pytest
from decimal import Decimal
from datetime import date, datetime
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def staff_user(db):
    from django.contrib.auth import get_user_model
    from users.models import UserRole
    User = get_user_model()
    u = User.objects.create_user(
        username='staff_test', email='staff@test.it',
        password='x', is_active=True, is_staff=True, is_superuser=True,
    )
    u.role = UserRole.ADMIN
    u.save()
    return u


def _make_event_and_contract(sponsor, event_code='FIN1', total=Decimal('1000.00'),
                              signed=True):
    from events.models import Event
    from contracts.models import Contract, ContractStatus, ContractKind
    ev = Event.objects.create(
        name={'it': f'Evento {event_code}', 'en': f'Event {event_code}'},
        code=event_code,
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )
    status = ContractStatus.SIGNED if signed else ContractStatus.DRAFT
    c = Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=status, contract_number=f'{event_code}-26-001',
        total=total, deposit_percent=Decimal('30'),
    )
    return ev, c


@pytest.mark.django_db
def test_bonifici_in_attesa_shown_in_cruscotto(client, staff_user, sponsor):
    """La vista evento_dettaglio include il conteggio bonifici pending nel context."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    ev, c = _make_event_and_contract(sponsor)

    # 2 bonifici in attesa + 1 paypal pending (non deve contare)
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
                           amount_gross=Decimal('300.00'), status=PaymentStatus.PENDING)
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
                           amount_gross=Decimal('700.00'), status=PaymentStatus.PENDING)
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.PAYPAL,
                           amount_gross=Decimal('300.00'), status=PaymentStatus.PENDING)

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_evento', args=[ev.id]))

    assert resp.status_code == 200
    ctx_incassi = resp.context.get('incassi', {})
    assert ctx_incassi.get('bonifici_in_attesa') == 2


@pytest.mark.django_db
def test_email_fallite_shown_in_cruscotto(client, staff_user, sponsor):
    """La vista evento_dettaglio include il conteggio email fallite nel context."""
    from shared.models import Communication, CommunicationStatus, CommunicationChannel, CommunicationType
    from django.contrib.contenttypes.models import ContentType
    ev, c = _make_event_and_contract(sponsor, event_code='FIN2')

    ct = ContentType.objects.get_for_model(c)
    # 1 fallita + 1 inviata (non deve contare)
    Communication.objects.create(
        content_type=ct, object_id=c.id,
        channel=CommunicationChannel.EMAIL,
        communication_type=CommunicationType.MANUAL,
        subject='Test fail', body_text='x',
        status=CommunicationStatus.FAILED,
    )
    Communication.objects.create(
        content_type=ct, object_id=c.id,
        channel=CommunicationChannel.EMAIL,
        communication_type=CommunicationType.MANUAL,
        subject='Test ok', body_text='x',
        status=CommunicationStatus.SENT,
    )

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_evento', args=[ev.id]))

    assert resp.status_code == 200
    assert resp.context['incassi']['email_fallite'] == 1


@pytest.mark.django_db
def test_registra_incasso_get(client, staff_user, sponsor):
    """GET /cruscotto/contratto/<id>/registra-incasso/ restituisce 200 con form."""
    ev, c = _make_event_and_contract(sponsor, event_code='FIN3')

    client.force_login(staff_user)
    url = reverse('core:cruscotto_registra_incasso', args=[c.id])
    resp = client.get(url)

    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'amount_gross' in html or 'Importo' in html


@pytest.mark.django_db
def test_registra_incasso_post_creates_payment_and_reconciles(client, staff_user, sponsor):
    """POST registra_incasso crea Payment SUCCEEDED e marca la scadenza acconto come RECEIVED."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    from contracts.models import Deadline, DeadlineStatus, ContractStatus
    ev, c = _make_event_and_contract(sponsor, event_code='FIN4')

    # Scadenza acconto aperta
    from contracts.models import Deadline, DeadlineStatus
    Deadline.objects.create(
        contract=c, deadline_type='pagamento_acconto',
        title='Acconto FIN4', due_date=date(2026, 9, 1),
        status=DeadlineStatus.PENDING,
    )

    client.force_login(staff_user)
    url = reverse('core:cruscotto_registra_incasso', args=[c.id])
    resp = client.post(url, {
        'amount_gross': '300.00',
        'payment_method': PaymentMethodChoice.BANK_TRANSFER,
        'bank_transfer_reference': 'BON-2026-001',
        'notes': 'Bonifico ricevuto',
    })

    # Redirect dopo successo
    assert resp.status_code in (200, 302)

    # Payment creato con status SUCCEEDED
    p = Payment.objects.filter(contract=c, status=PaymentStatus.SUCCEEDED).first()
    assert p is not None
    assert p.amount_gross == Decimal('300.00')
    assert p.payment_method == PaymentMethodChoice.BANK_TRANSFER
    assert p.bank_transfer_reference == 'BON-2026-001'

    # Scadenza acconto riconciliata (acconto = 300 = 30% di 1000)
    from contracts.models import Deadline, DeadlineStatus
    acc = Deadline.objects.filter(contract=c, deadline_type='pagamento_acconto').first()
    assert acc is not None
    assert acc.status == DeadlineStatus.RECEIVED


def _contratto_con_iva(sponsor, event_code, subtotal, vat_amount, deposit_percent=None,
                        status=None):
    """Contratto con subtotal/vat_amount/total impostati esplicitamente
    (come farebbe recalculate_totals), per testare gli importi IVA esclusa
    del cruscotto senza dipendere da ContractLine."""
    from events.models import Event
    from contracts.models import Contract, ContractStatus, ContractKind
    ev = Event.objects.create(
        name={'it': f'Evento {event_code}', 'en': f'Event {event_code}'},
        code=event_code,
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )
    c = Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=status or ContractStatus.SIGNED, contract_number=f'{event_code}-26-001',
        subtotal=subtotal, vat_amount=vat_amount, total=subtotal + vat_amount,
        deposit_percent=deposit_percent, vat_applicable=(vat_amount > 0),
    )
    return ev, c


@pytest.mark.django_db
def test_cruscotto_evento_mostra_importi_iva_esclusa(client, staff_user, sponsor):
    """Il KPI 'Confermato' dell'evento e' l'IMPONIBILE (subtotal), non il
    totale IVA inclusa - altrimenti sommare aziende con e senza IVA applicata
    mescola basi diverse e il totale non ha piu' senso."""
    ev, c = _contratto_con_iva(
        sponsor, 'IVAK', subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'))

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_evento', args=[ev.id]))

    assert resp.context['confermati']['totale'] == Decimal('1000.00')


@pytest.mark.django_db
def test_incassato_esente_iva_non_viene_toccato(client, staff_user, sponsor):
    """Contratto ESENTE IVA (subtotal == total): l'incasso registrato non va
    scontato di nulla, il rapporto subtotal/total e' 1."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    ev, c = _contratto_con_iva(
        sponsor, 'IVAE', subtotal=Decimal('500.00'), vat_amount=Decimal('0.00'))
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
                            amount_gross=Decimal('500.00'), status=PaymentStatus.SUCCEEDED)

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_evento', args=[ev.id]))

    assert resp.context['incassi']['incassato'] == Decimal('500.00')
    assert resp.context['incassi']['da_incassare'] == Decimal('0.00')


@pytest.mark.django_db
def test_incassato_con_iva_viene_scontato_proporzionalmente(client, staff_user, sponsor):
    """Contratto CON IVA (22%): un incasso di 610 (500 imponibile + 110 IVA,
    pagamento completo) deve contare come 500 nel cruscotto (IVA esclusa)."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    ev, c = _contratto_con_iva(
        sponsor, 'IVAP', subtotal=Decimal('500.00'), vat_amount=Decimal('110.00'))
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
                            amount_gross=Decimal('610.00'), status=PaymentStatus.SUCCEEDED)

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_evento', args=[ev.id]))

    assert resp.context['incassi']['incassato'] == Decimal('500.00')
    assert resp.context['incassi']['da_incassare'] == Decimal('0.00')


@pytest.mark.django_db
def test_da_incassare_evento_righe_iva_esclusa(client, staff_user, sponsor):
    """La pagina 'Da incassare' mostra totale/incassato/residuo IVA esclusa."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    ev, c = _contratto_con_iva(
        sponsor, 'IVAD', subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'))
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
                            amount_gross=Decimal('610.00'), status=PaymentStatus.SUCCEEDED)

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_da_incassare', args=[ev.id]))

    riga = resp.context['righe'][0]
    assert riga['totale'] == Decimal('1000.00')
    assert riga['incassato'] == Decimal('500.00')
    assert riga['residuo'] == Decimal('500.00')


@pytest.mark.django_db
def test_bonifici_in_attesa_card_in_template(client, staff_user, sponsor):
    """Il template cruscotto/evento.html mostra la card 'Bonifici in attesa'."""
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    ev, c = _make_event_and_contract(sponsor, event_code='FIN5')
    Payment.objects.create(contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
                           amount_gross=Decimal('300.00'), status=PaymentStatus.PENDING)

    client.force_login(staff_user)
    resp = client.get(reverse('core:cruscotto_evento', args=[ev.id]))
    html = resp.content.decode()
    assert 'Bonifici in attesa' in html
    assert 'Email fallite' in html

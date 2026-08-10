"""Test delle funzioni pratiche aggiunte dall'audit di luglio (round 2):

1. cruscotto home: avvisi 'preventivi senza risposta' e 'opzioni in scadenza'
2. export Excel di Da incassare / Incassato
3. conferma esplicita sull'azione Annulla contratti
4. azione 'Sposta scadenze' (di N giorni / a data fissa)
5. duplica evento (servizi+varianti+inclusioni+template+stand, originale intatto)
6. colonna Incassato/Residuo nella changelist contratti
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalog.models import DeadlineTemplate, Service, ServiceInclusion, ServiceVariant
from contracts.models import Contract, ContractKind, ContractStatus, Deadline, DeadlineStatus
from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
from events.models import Event, EventStatus
from users.models import UserRole
from venues.models import Stand, StandBlock


@pytest.fixture
def staff_user(db):
    User = get_user_model()
    u = User.objects.create_user(
        username='op_round2', email='op_round2@test.it', password='x',
        is_active=True, is_staff=True, is_superuser=True)
    u.role = UserRole.ADMIN
    u.save()
    return u


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Round2', 'en': 'Ev Round2'}, code='RND2',
        status=EventStatus.SELLING,
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )


def _login_con_evento(client, staff_user):
    client.force_login(staff_user)
    session = client.session
    session['cruscotto_event_chosen'] = True
    session.save()


# ---------------------------------------------------------------------------
# 1: avvisi cruscotto home
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_home_avvisa_preventivi_fermi_e_opzioni(client, staff_user, sponsor, evento):
    from core.event_scope import SESSION_EVENT_CHOSEN
    fermo = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='RND2-26-001',
        sent_date=timezone.now() - timedelta(days=10),
    )
    stand = Stand.objects.create(event=evento, code='R2-01', base_price=Decimal('1000.00'))
    Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='RND2-26-002',
        stand=stand, option_until=date.today() + timedelta(days=3),
    )
    client.force_login(staff_user)
    session = client.session
    session[SESSION_EVENT_CHOSEN] = True
    session.save()
    resp = client.get(reverse('core:cruscotto_home'))
    assert resp.status_code == 200
    assert resp.context['fermi_count'] == 1
    assert resp.context['opzioni_count'] == 1
    html = resp.content.decode()
    assert 'senza risposta' in html
    assert 'opzione/i stand in scadenza' in html


# ---------------------------------------------------------------------------
# 2: export Excel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_export_excel_da_incassare_e_incassato(client, staff_user, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RND2-26-003',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'),
    )
    Payment.objects.create(
        contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('610.00'), status=PaymentStatus.SUCCEEDED,
        completed_at=timezone.now(),
    )
    client.force_login(staff_user)
    XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    r1 = client.get(reverse('core:cruscotto_da_incassare_export', args=[evento.id]))
    assert r1.status_code == 200 and r1['Content-Type'] == XLSX
    assert r1.content[:2] == b'PK'  # xlsx = zip

    r2 = client.get(reverse('core:cruscotto_incassato_export', args=[evento.id]))
    assert r2.status_code == 200 and r2['Content-Type'] == XLSX
    assert r2.content[:2] == b'PK'


# ---------------------------------------------------------------------------
# 3: conferma esplicita su Annulla
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_annulla_richiede_conferma(client, staff_user, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='RND2-26-004',
    )
    client.force_login(staff_user)
    url = reverse('admin:contracts_contract_changelist')

    # primo POST: pagina di conferma, il contratto NON viene annullato
    resp = client.post(url, {
        'action': 'action_cancel', '_selected_action': [str(c.id)],
    })
    assert resp.status_code == 200
    assert 'Conferma annullamento' in resp.content.decode()
    c.refresh_from_db()
    assert c.status == ContractStatus.SENT

    # secondo POST con conferma: annullato
    resp = client.post(url, {
        'action': 'action_cancel', '_selected_action': [str(c.id)],
        '_annulla_confermato': '1', 'reason': 'rinuncia cliente',
    }, follow=True)
    c.refresh_from_db()
    assert c.status == ContractStatus.CANCELLED
    assert c.cancellation_reason == 'rinuncia cliente'


# ---------------------------------------------------------------------------
# 4: sposta scadenze
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sposta_scadenze_di_n_giorni(client, staff_user, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RND2-26-005',
    )
    dl = Deadline.objects.create(
        contract=c, deadline_type='tecnica', title='Invio logo',
        due_date=date(2026, 9, 1), status=DeadlineStatus.PENDING,
    )
    client.force_login(staff_user)
    url = reverse('admin:contracts_deadline_changelist')

    # pagina intermedia
    resp = client.post(url, {
        'action': 'action_sposta_scadenze', '_selected_action': [str(dl.id)],
    })
    assert 'Sposta scadenze' in resp.content.decode()

    # +30 giorni
    client.post(url, {
        'action': 'action_sposta_scadenze', '_selected_action': [str(dl.id)],
        '_sposta_confermato': '1', 'giorni': '30',
    }, follow=True)
    dl.refresh_from_db()
    assert dl.due_date == date(2026, 10, 1)

    # data fissa (vince sui giorni)
    client.post(url, {
        'action': 'action_sposta_scadenze', '_selected_action': [str(dl.id)],
        '_sposta_confermato': '1', 'giorni': '5', 'data_fissa': '2026-11-15',
    }, follow=True)
    dl.refresh_from_db()
    assert dl.due_date == date(2026, 11, 15)


# ---------------------------------------------------------------------------
# 5: duplica evento
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_duplica_evento_clona_struttura_senza_toccare_originale(sponsor, evento):
    from events.clone import duplica_evento

    blocco = StandBlock.objects.create(event=evento, code='BL-1')
    Stand.objects.create(event=evento, code='DUP-01',
                         base_price=Decimal('2000.00'), stand_block=blocco,
                         status='assigned')
    padre = Service.objects.create(
        event=evento, code='DUP-SRV', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('100.00'))
    figlio = Service.objects.create(
        event=evento, code='DUP-INC', name={'it': 'Incluso', 'en': 'Included'},
        base_price=Decimal('0.00'))
    ServiceInclusion.objects.create(parent=padre, child=figlio, quantity=2)
    ServiceVariant.objects.create(service=padre, label='Rosso',
                                  base_price=Decimal('120.00'))
    DeadlineTemplate.objects.create(
        service=padre, deadline_type='tecnica', title='Invio grafica',
        days_before_event=30)
    # un contratto sull'originale: NON deve essere clonato ne' toccato
    Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RND2-26-006')

    nuovo = duplica_evento(evento)

    assert nuovo.pk != evento.pk
    assert nuovo.status == EventStatus.PLANNING
    assert nuovo.slug != evento.slug
    assert '(copia)' in (nuovo.name.get('it') or '')

    # NB: la creazione degli Stand auto-genera anche il servizio "pacchetto
    # spazio espositivo": confrontiamo i codici, non il conteggio secco.
    codici_clone = set(nuovo.services.values_list('code', flat=True))
    assert {'DUP-SRV', 'DUP-INC'} <= codici_clone
    srv_clone = nuovo.services.get(code='DUP-SRV')
    assert srv_clone.variants.count() == 1
    assert srv_clone.deadline_templates.count() == 1
    assert ServiceInclusion.objects.filter(parent=srv_clone).count() == 1
    assert Stand.objects.filter(event=nuovo).count() == 1
    assert Stand.objects.get(event=nuovo).status == 'available'
    assert StandBlock.objects.filter(event=nuovo).count() == 1
    assert Contract.all_objects.filter(event=nuovo).count() == 0

    # originale intatto
    evento.refresh_from_db()
    assert evento.status == EventStatus.SELLING
    codici_orig = set(evento.services.values_list('code', flat=True))
    assert {'DUP-SRV', 'DUP-INC'} <= codici_orig
    assert Contract.all_objects.filter(event=evento).count() == 1


# ---------------------------------------------------------------------------
# 6: colonna Incassato/Residuo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_colonna_incassato_residuo_changelist(client, staff_user, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RND2-26-007',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'),
    )
    Payment.objects.create(
        contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('500.00'), status=PaymentStatus.SUCCEEDED,
    )
    client.force_login(staff_user)
    resp = client.get(reverse('admin:contracts_contract_changelist'))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Incassato / Residuo' in html
    riga = resp.context['cl'].result_list
    obj = next(o for o in riga if o.pk == c.pk)
    assert obj._incassato == Decimal('500.00')

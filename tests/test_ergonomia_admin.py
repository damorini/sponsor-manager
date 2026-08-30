"""Ergonomia backoffice (intervento del 30/08, richiesta: 'tutto macchinoso').

Copre:
- azioni rapide a UN click sulle scadenze (ricevuta/esonera) + permessi
- pagina Registra incasso: riepilogo importi, ritorno alla provenienza
- bottoni contestuali sulla scheda contratto in base allo stato
- nuovi filtri 'Cose da fare' coerenti con i conteggi del cruscotto
- badge scadenze onesto sul doppio requisito + avviso al salvataggio
- colonna Portale dei contatti con lo stato reale
- nuovo contratto pre-compilato con l'evento attivo
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalog.models import DeadlineTemplate, Service
from contracts.models import (Contract, ContractKind, ContractStatus,
                              Deadline, DeadlineStatus)
from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
from events.models import Event, EventStatus
from sponsors.models import Contact

DOPO = date.today() + timedelta(days=90)


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_superuser(
        username='op_ergo', email='op_ergo@test.it', password='x')


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Ergo', 'en': 'Ev Ergo'}, code='ERGO',
        status=EventStatus.SELLING,
        start_date=DOPO, end_date=DOPO + timedelta(days=1))


@pytest.fixture
def contratto(db, sponsor, evento):
    return Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='ERGO-26-001',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'))


# ---------------------------------------------------------------------------
# Azioni rapide scadenze
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_azione_rapida_ricevuta_ed_esonera(client, staff, contratto):
    dl = Deadline.objects.create(
        contract=contratto, deadline_type='tecnica', title='Logo',
        due_date=DOPO, status=DeadlineStatus.PENDING)
    client.force_login(staff)
    resp = client.post(reverse('admin:contracts_deadline_segna_ricevuta',
                               args=[dl.pk]))
    assert resp.status_code == 200
    dl.refresh_from_db()
    assert dl.status == DeadlineStatus.RECEIVED

    dl2 = Deadline.objects.create(
        contract=contratto, deadline_type='tecnica', title='Banner',
        due_date=DOPO, status=DeadlineStatus.PENDING)
    resp = client.post(reverse('admin:contracts_deadline_esonera', args=[dl2.pk]))
    assert resp.status_code == 200
    dl2.refresh_from_db()
    assert dl2.status == DeadlineStatus.WAIVED

    # GET rifiutato (solo POST via JS)
    dl3 = Deadline.objects.create(
        contract=contratto, deadline_type='tecnica', title='Altro',
        due_date=DOPO, status=DeadlineStatus.PENDING)
    resp = client.get(reverse('admin:contracts_deadline_esonera', args=[dl3.pk]))
    assert resp.status_code == 405
    dl3.refresh_from_db()
    assert dl3.status == DeadlineStatus.PENDING


@pytest.mark.django_db
def test_chips_scorciatoie_nelle_liste(client, staff, contratto):
    """Le scorciatoie 'Cose da fare' sono visibili sopra le liste, non solo
    nel pannello filtri (che parte chiuso)."""
    client.force_login(staff)
    html = client.get(reverse('admin:contracts_contract_changelist')).content.decode()
    assert 'vt-chips' in html
    assert '?todo=da_inviare' in html
    assert '?trash=cestino' in html
    html = client.get(reverse('admin:contracts_deadline_changelist')).content.decode()
    assert 'vt-chips' in html
    assert '?status__exact=overdue' in html


@pytest.mark.django_db
def test_lista_scadenze_mostra_azioni_rapide(client, staff, contratto):
    Deadline.objects.create(
        contract=contratto, deadline_type='tecnica', title='Logo QA',
        due_date=DOPO, status=DeadlineStatus.PENDING)
    Deadline.objects.create(
        contract=contratto, deadline_type='pagamento_saldo', title='Saldo QA',
        due_date=DOPO, status=DeadlineStatus.PENDING)
    client.force_login(staff)
    html = client.get(reverse('admin:contracts_deadline_changelist')).content.decode()
    assert 'dq-btn' in html                      # bottoni un-click presenti
    assert 'Registra incasso' in html            # sulla riga di pagamento
    assert 'deadline_quick_actions_v1.js' in html


# ---------------------------------------------------------------------------
# Registra incasso: riepilogo + ritorno
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_registra_incasso_riepilogo_e_next(client, staff, contratto):
    Payment.objects.create(
        contract=contratto, payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('220.00'), status=PaymentStatus.SUCCEEDED,
        completed_at=timezone.now())
    client.force_login(staff)
    url = reverse('core:cruscotto_registra_incasso', args=[contratto.pk])
    resp = client.get(url + '?next=/admin/contracts/contract/')
    html = resp.content.decode()
    assert 'Già incassato' in html and 'Residuo' in html
    assert 'IVA inclusa' in html  # avvisa che serve il lordo
    assert 'ri-fill' in html      # bottoni compila-importo

    resp = client.post(url, {
        'amount_gross': '1000.00', 'payment_method': 'bank_transfer',
        'next': '/admin/contracts/contract/'})
    assert resp.status_code == 302
    assert resp.url == '/admin/contracts/contract/'
    # next esterno rifiutato
    resp = client.post(url, {
        'amount_gross': '1.00', 'payment_method': 'bank_transfer',
        'next': '//evil.com/x'})
    assert resp.status_code == 302
    assert not resp.url.startswith('//')


# ---------------------------------------------------------------------------
# Bottoni contestuali scheda contratto
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bottoni_contestuali_per_stato(client, staff, sponsor, evento):
    client.force_login(staff)
    inviato = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='ERGO-26-002')
    html = client.get(reverse('admin:contracts_contract_change',
                              args=[inviato.pk])).content.decode()
    assert 'Segna come firmato' in html
    assert 'Trasforma in contratto' in html
    # il LINK registra-incasso (object tool) non c'e' sui non confermati
    assert reverse('core:cruscotto_registra_incasso', args=[inviato.pk]) not in html

    firmato = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='ERGO-26-003')
    html = client.get(reverse('admin:contracts_contract_change',
                              args=[firmato.pk])).content.decode()
    assert reverse('core:cruscotto_registra_incasso', args=[firmato.pk]) in html
    assert 'Genera proforma' in html
    assert 'Rigenera PDF' in html
    assert 'Anteprima preventivo' not in html  # fase preventivo conclusa


# ---------------------------------------------------------------------------
# Filtri 'Cose da fare' coerenti coi conteggi
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_todo_filter_nuovi_lookup(client, staff, sponsor, evento):
    Contract.objects.create(   # confermato
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='ERGO-26-004')
    Contract.objects.create(   # opzione in scadenza (3 giorni)
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='ERGO-26-005',
        option_until=date.today() + timedelta(days=3))
    Contract.objects.create(   # inviato fermo da 10 giorni
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='ERGO-26-006',
        sent_date=timezone.now() - timedelta(days=10))
    client.force_login(staff)
    base = reverse('admin:contracts_contract_changelist')

    r = client.get(base + '?todo=confermati')
    assert 'ERGO-26-004' in r.content.decode()
    assert 'ERGO-26-005' not in r.content.decode()

    r = client.get(base + '?todo=opzioni_in_scadenza')
    assert 'ERGO-26-005' in r.content.decode()
    assert 'ERGO-26-004' not in r.content.decode()

    r = client.get(base + '?todo=senza_risposta')
    assert 'ERGO-26-006' in r.content.decode()
    assert 'ERGO-26-004' not in r.content.decode()


# ---------------------------------------------------------------------------
# Badge scadenze onesto + avviso al salvataggio
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_badge_scadenze_onesto(client, staff, evento):
    meta_config = Service.objects.create(
        event=evento, code='META', name={'it': 'Meta', 'en': 'Meta'},
        base_price=Decimal('10.00'), triggers_deadlines=False)
    DeadlineTemplate.objects.create(
        service=meta_config, deadline_type='tecnica', title='Invio logo',
        days_before_event=30)
    spunta_sola = Service.objects.create(
        event=evento, code='SPUNTA', name={'it': 'Spunta', 'en': 'S'},
        base_price=Decimal('10.00'), triggers_deadlines=True)
    client.force_login(staff)
    html = client.get(reverse('admin:catalog_service_changelist')).content.decode()
    assert 'SPENTE' in html                 # template senza spunta
    assert 'spunta senza template' in html  # spunta senza template


# ---------------------------------------------------------------------------
# Colonna Portale con lo stato reale
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_colonna_portale_stato_reale(client, staff, sponsor):
    User = get_user_model()
    mai = User.objects.create_user(username='mai@x.it', email='mai@x.it',
                                   password='x', is_active=True)
    mai.role = 'sponsor'
    mai.save()
    Contact.objects.create(sponsor=sponsor, full_name='Mai Entrato',
                           email='mai@x.it', portal_user=mai,
                           has_portal_access=True)
    attivo = User.objects.create_user(username='ok@x.it', email='ok@x.it',
                                      password='x', is_active=True)
    attivo.role = 'sponsor'
    attivo.last_login = timezone.now()
    attivo.save()
    Contact.objects.create(sponsor=sponsor, full_name='Gia Attivo',
                           email='ok@x.it', portal_user=attivo,
                           has_portal_access=True)
    client.force_login(staff)
    html = client.get(reverse('admin:sponsors_contact_changelist')).content.decode()
    assert 'mai entrato' in html
    assert 'attivo' in html


# ---------------------------------------------------------------------------
# Nuovo contratto pre-compilato con l'evento attivo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_nuovo_contratto_precompila_evento_attivo(client, staff, evento):
    from core.event_scope import SESSION_EVENT_KEY
    client.force_login(staff)
    session = client.session
    session[SESSION_EVENT_KEY] = str(evento.pk)
    session.save()
    resp = client.get(reverse('admin:contracts_contract_add'))
    assert resp.status_code == 200
    assert str(evento.pk) in resp.content.decode()

"""
Avvisi "cosa manca" (core/controlli.py): il sistema segnala all'operatore
le cose lasciate a meta' o che il cliente non puo' vedere nel portale.

- contatto con "Accesso al portale" spuntato ma mai invitato (niente account);
- contratto inviato/firmato di un'azienda in cui nessuno puo' entrare;
- contratto firmato con importo ma senza scadenze di pagamento.

Compaiono nella home del cruscotto, nei filtri delle liste, nell'email
mattutina di alert e (per gli inviti) al salvataggio di azienda/contatto.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from contracts.models import Contract, ContractKind, ContractStatus, Deadline
from core import controlli
from events.models import Event, EventStatus
from sponsors.models import Contact, ContactRole, Sponsor
from users.models import UserRole


@pytest.fixture
def staff_user(db):
    u = get_user_model().objects.create_user(
        username='op_avvisi', email='op_avvisi@test.it', password='x',
        is_active=True, is_staff=True, is_superuser=True)
    u.role = UserRole.ADMIN
    u.save()
    return u


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Avvisi', 'en': 'Ev Avvisi'}, code='AVV',
        status=EventStatus.SELLING,
        start_date=date(2030, 11, 28), end_date=date(2030, 11, 28),
    )


@pytest.fixture
def azienda(db):
    return Sponsor.objects.create(legal_name='Nuova Pharma Srl',
                                  vat_number='09999999999', address_country='IT')


@pytest.fixture
def contatto_spuntato(azienda):
    """Come nasce dal '+' della scheda contratto: spunta si', account no."""
    return Contact.objects.create(
        sponsor=azienda, full_name='Alberto Rossi', email='alberto@nuovapharma.it',
        roles=[ContactRole.OPERATIONAL], is_primary=True, has_portal_access=True)


def _firmato(azienda, evento, total=Decimal('1000.00'), n='AVV-26-001'):
    c = Contract.objects.create(
        sponsor=azienda, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number=n)
    Contract.objects.filter(pk=c.pk).update(total=total)
    c.refresh_from_db()
    return c


def _login(client, staff_user):
    from core.event_scope import SESSION_EVENT_CHOSEN
    client.force_login(staff_user)
    s = client.session
    s[SESSION_EVENT_CHOSEN] = True
    s.save()


@pytest.mark.django_db
def test_contatto_spuntato_senza_account_da_invitare(contatto_spuntato):
    assert list(controlli.contatti_da_invitare()) == [contatto_spuntato]
    u = get_user_model().objects.create_user(
        username='alberto', email='alberto@nuovapharma.it', password='x')
    contatto_spuntato.portal_user = u
    contatto_spuntato.save()
    assert not controlli.contatti_da_invitare().exists()


@pytest.mark.django_db
def test_contratto_che_il_cliente_non_vede(evento, azienda, contatto_spuntato):
    c = _firmato(azienda, evento)
    assert list(controlli.contratti_cliente_senza_accesso()) == [c]
    u = get_user_model().objects.create_user(
        username='alberto', email='alberto@nuovapharma.it', password='x')
    contatto_spuntato.portal_user = u
    contatto_spuntato.save()
    assert not controlli.contratti_cliente_senza_accesso().exists()


@pytest.mark.django_db
def test_bozza_non_conta_come_non_vista(evento, azienda):
    Contract.objects.create(sponsor=azienda, event=evento,
                            contract_kind=ContractKind.MAIN,
                            status=ContractStatus.DRAFT)
    assert not controlli.contratti_cliente_senza_accesso().exists()


@pytest.mark.django_db
def test_evento_archiviato_non_segnalato(evento, azienda):
    _firmato(azienda, evento)
    Event.objects.filter(pk=evento.pk).update(status=EventStatus.ARCHIVED)
    assert not controlli.contratti_cliente_senza_accesso().exists()
    assert not controlli.contratti_senza_scadenze_pagamento().exists()


@pytest.mark.django_db
def test_firmato_con_importo_senza_scadenze_pagamento(evento, azienda):
    c = _firmato(azienda, evento)
    _firmato(azienda, evento, total=Decimal('0.00'), n='AVV-26-002')
    assert list(controlli.contratti_senza_scadenze_pagamento()) == [c]
    Deadline.objects.create(contract=c, deadline_type='pagamento_saldo',
                            title='Saldo', due_date=date(2030, 11, 13))
    assert not controlli.contratti_senza_scadenze_pagamento().exists()


@pytest.mark.django_db
def test_cruscotto_mostra_gli_avvisi(client, staff_user, evento, azienda,
                                     contatto_spuntato):
    _firmato(azienda, evento)
    _login(client, staff_user)
    html = client.get(reverse('core:cruscotto_home')).content.decode()
    assert 'mai invitato' in html
    assert 'che il cliente NON può vedere' in html
    assert 'senza scadenze di pagamento' in html
    assert 'Nuova Pharma Srl' in html


@pytest.mark.django_db
def test_filtri_delle_liste(client, staff_user, evento, azienda, contatto_spuntato):
    c = _firmato(azienda, evento)
    _login(client, staff_user)
    r = client.get(reverse('admin:sponsors_contact_changelist') + '?invito=da_mandare')
    assert r.status_code == 200
    assert 'alberto@nuovapharma.it' in r.content.decode()
    for todo in ('cliente_senza_accesso', 'senza_scadenze_pagamento'):
        r = client.get(reverse('admin:contracts_contract_changelist') + '?todo=' + todo)
        assert r.status_code == 200
        assert c.contract_number in r.content.decode()


@pytest.mark.django_db
def test_salvataggio_contatto_ricorda_invito(client, staff_user, contatto_spuntato):
    _login(client, staff_user)
    url = reverse('admin:sponsors_contact_change', args=[contatto_spuntato.pk])
    form = client.get(url).context['adminform'].form
    dati = {k: v for k, v in form.initial.items() if v is not None}
    dati.update({'sponsor': str(contatto_spuntato.sponsor_id),
                 'roles': ['operational'], 'has_portal_access': 'on',
                 'is_primary': 'on', 'preferred_language': 'it'})
    r = client.post(url, dati, follow=True)
    testi = [str(m) for m in r.context['messages']]
    assert any('invito NON ancora mandato' in t for t in testi), testi


@pytest.mark.django_db
def test_email_alert_operatore(settings, staff_user, evento, azienda,
                               contatto_spuntato):
    from contracts.tasks.scheduled import send_operator_alerts
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    _firmato(azienda, evento)
    send_operator_alerts()
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert 'inviti portale da mandare' in msg.subject
    corpo = msg.alternatives[0][0] if msg.alternatives else msg.body
    assert 'alberto@nuovapharma.it' in corpo
    assert 'AVV-26-001' in corpo

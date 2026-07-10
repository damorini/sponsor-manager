"""EVENTO ATTIVO di sessione per lo staff.

Al primo accesso il cruscotto chiede su quale evento lavorare
(pagina 'Scegli evento'); da quel momento TUTTE le liste dell'admin
mostrano solo i dati di quell'evento, senza filtri manuali. Si cambia
o si spegne dal selettore «Evento» nell'header (vale anche per i
superuser). 'Tutti gli eventi' = nessun filtro.
"""
import pytest
from datetime import date
from django.urls import reverse

from core.event_scope import (
    SESSION_EVENT_CHOSEN, SESSION_EVENT_KEY,
    events_for_user, scope_by_event, scope_generic_by_event,
)


# ---------------------------------------------------------------- fixtures

@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        username='capo_ev', email='capo_ev@test.it', password='AdminPass123!')


@pytest.fixture
def due_eventi(db):
    from events.models import Event, EventStatus
    a = Event.objects.create(
        name={'it': 'Evento Alfa', 'en': 'Event Alfa'}, code='ALF',
        start_date=date(2026, 11, 10), end_date=date(2026, 11, 11),
        status=EventStatus.SELLING)
    b = Event.objects.create(
        name={'it': 'Evento Beta', 'en': 'Event Beta'}, code='BET',
        start_date=date(2026, 12, 10), end_date=date(2026, 12, 11),
        status=EventStatus.SELLING)
    return a, b


@pytest.fixture
def due_contratti(db, sponsor, due_eventi):
    from contracts.models import Contract, ContractKind, ContractStatus
    a, b = due_eventi
    ca = Contract.objects.create(
        sponsor=sponsor, event=a, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='ALF-26-777')
    cb = Contract.objects.create(
        sponsor=sponsor, event=b, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='BET-26-888')
    return ca, cb


class _FakeRequest:
    """Request minimale per i test unitari delle funzioni di scoping."""
    def __init__(self, user, session=None):
        self.user = user
        self.session = session if session is not None else {}


def _scegli(client, event_id):
    return client.post(reverse('core:scegli_evento'), {'event_id': event_id})


# ------------------------------------------------- funzioni di scoping

@pytest.mark.django_db
def test_scope_filtra_anche_il_superuser_se_evento_attivo(admin_user, due_contratti):
    from contracts.models import Contract
    ca, cb = due_contratti
    req = _FakeRequest(admin_user, {SESSION_EVENT_KEY: str(ca.event_id)})
    qs = scope_by_event(req, Contract.objects.all(), 'event')
    assert list(qs) == [ca]


@pytest.mark.django_db
def test_scope_senza_evento_attivo_mostra_tutto(admin_user, due_contratti):
    from contracts.models import Contract
    req = _FakeRequest(admin_user, {})
    qs = scope_by_event(req, Contract.objects.all(), 'event')
    assert qs.count() == 2


@pytest.mark.django_db
def test_scope_combina_rbac_ed_evento_attivo(due_contratti, due_eventi):
    """Operatore con solo Alfa gestito + evento attivo Beta = niente
    (l'intersezione e' vuota: il RBAC non si aggira con la sessione)."""
    from django.contrib.auth import get_user_model
    from contracts.models import Contract
    a, b = due_eventi
    op = get_user_model().objects.create_user(
        username='op_ev', email='op_ev@test.it', password='X12345678!')
    op.role = 'operator'
    op.is_staff = True
    op.save()
    op.managed_events.set([a])
    req = _FakeRequest(op, {SESSION_EVENT_KEY: str(b.pk)})
    assert scope_by_event(req, Contract.objects.all(), 'event').count() == 0
    # con l'evento gestito invece vede il suo contratto
    req2 = _FakeRequest(op, {SESSION_EVENT_KEY: str(a.pk)})
    assert scope_by_event(req2, Contract.objects.all(), 'event').count() == 1


@pytest.mark.django_db
def test_events_for_user_esclude_archiviati(admin_user, due_eventi):
    from events.models import EventStatus
    a, b = due_eventi
    b.status = EventStatus.ARCHIVED
    b.save()
    req = _FakeRequest(admin_user)
    assert list(events_for_user(req)) == [a]


@pytest.mark.django_db
def test_scope_generico_rispetta_evento_attivo(admin_user, due_contratti, sponsor):
    """Documenti: con evento attivo si vedono solo quelli dei suoi contratti,
    ma quelli agganciati alle anagrafiche restano sempre visibili."""
    from shared.models import Document
    ca, cb = due_contratti
    da = Document.objects.create(entity=ca, title='doc-alfa',
                                 document_type='other', storage_url='http://x/a')
    db_ = Document.objects.create(entity=cb, title='doc-beta',
                                  document_type='other', storage_url='http://x/b')
    ds = Document.objects.create(entity=sponsor, title='doc-anagrafica',
                                 document_type='other', storage_url='http://x/s')
    req = _FakeRequest(admin_user, {SESSION_EVENT_KEY: str(ca.event_id)})
    visti = set(scope_generic_by_event(req, Document.objects.all()))
    assert da in visti and ds in visti and db_ not in visti


# ------------------------------------------------------- viste e header

@pytest.mark.django_db
def test_primo_accesso_redirige_alla_scelta_evento(client, admin_user):
    client.force_login(admin_user)
    resp = client.get(reverse('core:cruscotto_home'))
    assert resp.status_code == 302
    assert resp.url == reverse('core:scegli_evento')


@pytest.mark.django_db
def test_scelta_tutti_non_viene_piu_richiesta(client, admin_user):
    client.force_login(admin_user)
    resp = _scegli(client, 'tutti')
    assert resp.status_code == 302
    assert client.session[SESSION_EVENT_CHOSEN] is True
    assert client.session[SESSION_EVENT_KEY] == ''
    assert client.get(reverse('core:cruscotto_home')).status_code == 200


@pytest.mark.django_db
def test_pagina_scelta_mostra_le_card(client, admin_user, due_eventi):
    client.force_login(admin_user)
    resp = client.get(reverse('core:scegli_evento'))
    testo = resp.content.decode()
    assert 'Evento Alfa' in testo and 'Evento Beta' in testo
    assert 'Tutti gli eventi' in testo


@pytest.mark.django_db
def test_scelta_evento_filtra_le_liste_admin(client, admin_user, due_contratti):
    ca, cb = due_contratti
    client.force_login(admin_user)
    _scegli(client, str(ca.event_id))
    testo = client.get(reverse('admin:contracts_contract_changelist')).content.decode()
    assert 'ALF-26-777' in testo
    assert 'BET-26-888' not in testo


@pytest.mark.django_db
def test_switcher_salta_da_un_evento_allaltro(client, admin_user, due_contratti):
    ca, cb = due_contratti
    client.force_login(admin_user)
    _scegli(client, str(ca.event_id))
    url_contratti = reverse('admin:contracts_contract_changelist')
    resp = client.post(reverse('core:imposta_evento_attivo'),
                       {'event_id': str(cb.event_id), 'next': url_contratti})
    assert resp.status_code == 302 and resp.url == url_contratti
    testo = client.get(url_contratti).content.decode()
    assert 'BET-26-888' in testo and 'ALF-26-777' not in testo


@pytest.mark.django_db
def test_switcher_tutti_spegne_il_filtro(client, admin_user, due_contratti):
    ca, cb = due_contratti
    client.force_login(admin_user)
    _scegli(client, str(ca.event_id))
    client.post(reverse('core:imposta_evento_attivo'), {'event_id': 'tutti'})
    testo = client.get(reverse('admin:contracts_contract_changelist')).content.decode()
    assert 'ALF-26-777' in testo and 'BET-26-888' in testo


@pytest.mark.django_db
def test_operatore_non_attiva_eventi_non_suoi(client, due_eventi):
    """Se un operatore forza l'id di un evento non gestito, la scelta
    viene ignorata (equivale a 'tutti', dove il RBAC continua a filtrare)."""
    from django.contrib.auth import get_user_model
    a, b = due_eventi
    op = get_user_model().objects.create_user(
        username='op_ev2', email='op_ev2@test.it', password='X12345678!')
    op.role = 'operator'
    op.is_staff = True
    op.save()
    op.managed_events.set([a])
    client.force_login(op)
    client.post(reverse('core:imposta_evento_attivo'), {'event_id': str(b.pk)})
    assert client.session[SESSION_EVENT_KEY] == ''
    # quello gestito invece si attiva
    client.post(reverse('core:imposta_evento_attivo'), {'event_id': str(a.pk)})
    assert client.session[SESSION_EVENT_KEY] == str(a.pk)


@pytest.mark.django_db
def test_header_mostra_il_selettore_con_evento_scelto(client, admin_user, due_eventi):
    a, _ = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    testo = client.get(reverse('core:cruscotto_home')).content.decode()
    assert 'vt-event-switcher' in testo
    assert 'vt-ev-on' in testo  # evidenziazione "filtro acceso"
    assert 'Tutti gli eventi' in testo


@pytest.mark.django_db
def test_evento_attivo_sparito_spegne_il_filtro(client, admin_user, due_eventi, due_contratti):
    """Se l'evento attivo viene archiviato, il filtro si spegne da solo
    (niente liste vuote inspiegabili)."""
    from events.models import EventStatus
    a, b = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    a.status = EventStatus.ARCHIVED
    a.save()
    resp = client.get(reverse('core:cruscotto_home'))
    assert resp.status_code == 200
    assert client.session[SESSION_EVENT_KEY] == ''
    testo = client.get(reverse('admin:contracts_contract_changelist')).content.decode()
    assert 'ALF-26-777' in testo and 'BET-26-888' in testo

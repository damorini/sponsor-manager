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
        self.GET = {}


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


# ------------------------------------- fix dalla review multi-agente

@pytest.mark.django_db
def test_contatori_lista_aziende_restano_totali(client, admin_user, sponsor,
                                                due_eventi):
    """Le colonne Contratti/Attivi mostrano i TOTALI dell'azienda anche con
    evento attivo (il filtro non deve 'contaminare' i conteggi)."""
    from django.contrib import admin as djadmin
    from contracts.models import Contract, ContractKind, ContractStatus
    from sponsors.models import Sponsor
    a, b = due_eventi
    Contract.objects.create(sponsor=sponsor, event=a, contract_kind=ContractKind.MAIN,
                            status=ContractStatus.SENT, contract_number='ALF-26-201')
    Contract.objects.create(sponsor=sponsor, event=b, contract_kind=ContractKind.MAIN,
                            status=ContractStatus.SIGNED, contract_number='BET-26-202')
    req = _FakeRequest(admin_user, {SESSION_EVENT_KEY: str(a.pk)})
    row = djadmin.site._registry[Sponsor].get_queryset(req).get(pk=sponsor.pk)
    assert row._contracts_count == 2   # totale, non solo l'evento attivo
    assert row._active_contracts == 1  # il firmato su Beta conta


@pytest.mark.django_db
def test_cestino_aziende_visibile_con_evento_attivo(client, admin_user,
                                                    due_eventi, sponsor):
    """Il Cestino non e' ristretto all'evento attivo: chi e' cestinato ha i
    contratti gia' cestinati e sparirebbe per sempre."""
    from contracts.models import Contract, ContractKind, ContractStatus
    from sponsors.models import Sponsor
    a, b = due_eventi
    cestinato = Sponsor.objects.create(legal_name='Cestinata S.r.l.',
                                       vat_number='11122233344', address_country='IT')
    c = Contract.objects.create(sponsor=cestinato, event=b,
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SENT,
                                contract_number='BET-26-203')
    c.delete()           # prima il contratto nel cestino (flusso obbligato)
    cestinato.delete()   # poi l'azienda
    client.force_login(admin_user)
    _scegli(client, str(b.pk))
    url = reverse('admin:sponsors_sponsor_changelist') + '?trash=cestino'
    assert 'Cestinata' in client.get(url).content.decode()


@pytest.mark.django_db
def test_dettaglio_scadenza_altro_evento_si_apre(client, admin_user, sponsor,
                                                 due_eventi):
    """Le pagine di dettaglio del cruscotto (scadenza, documento) devono
    aprirsi via link diretto anche se di un altro evento."""
    from datetime import date as d
    from contracts.models import Contract, ContractKind, ContractStatus, Deadline
    a, b = due_eventi
    cb = Contract.objects.create(sponsor=sponsor, event=b,
                                 contract_kind=ContractKind.MAIN,
                                 status=ContractStatus.SIGNED,
                                 contract_number='BET-26-204')
    dl = Deadline.objects.create(contract=cb, deadline_type='consegna_materiali',
                                 title='Materiali', due_date=d(2026, 11, 1),
                                 submission_kind='file')
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    resp = client.get(reverse('core:cruscotto_scadenza_dettaglio', args=[dl.id]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_documento_altro_evento_si_apre(client, admin_user, contratti_separati,
                                        due_eventi):
    """L'anteprima PDF (documento_apri) di un contratto di un ALTRO evento
    deve aprirsi anche con un evento attivo diverso."""
    from django.conf import settings
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from shared.models import Document
    a, _ = due_eventi
    _, cb = contratti_separati
    path = default_storage.save('documents/test_evento_attivo.pdf',
                                ContentFile(b'%PDF-1.4 test'))
    try:
        doc = Document.objects.create(
            entity=cb, title='pdf-beta', document_type='other',
            storage_url=settings.MEDIA_URL + path)
        client.force_login(admin_user)
        _scegli(client, str(a.pk))
        resp = client.get(reverse('core:documento_apri', args=[doc.id]))
        assert resp.status_code == 200
    finally:
        default_storage.delete(path)


@pytest.mark.django_db
def test_event_id_non_valido_non_esplode(client, admin_user):
    client.force_login(admin_user)
    resp = client.post(reverse('core:imposta_evento_attivo'),
                       {'event_id': 'non-sono-un-uuid'})
    assert resp.status_code == 302          # niente 500
    assert client.session[SESSION_EVENT_KEY] == ''


@pytest.mark.django_db
def test_banner_filtro_sulla_lista_aziende(client, admin_user, contratti_separati,
                                           due_eventi):
    a, _ = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    url = reverse('admin:sponsors_sponsor_changelist')
    assert 'Filtro evento attivo' in client.get(url).content.decode()
    _scegli(client, 'tutti')
    assert 'Filtro evento attivo' not in client.get(url).content.decode()


# --------------------------------------------- anagrafiche (Sponsor/Contact)

@pytest.fixture
def sponsor_beta(db):
    from sponsors.models import Sponsor
    return Sponsor.objects.create(
        legal_name='Beta Pharma S.p.A.', vat_number='98765432109',
        address_country='IT')


@pytest.fixture
def contratti_separati(db, sponsor, sponsor_beta, due_eventi):
    """sponsor (conftest) ha un contratto SOLO su Alfa; sponsor_beta SOLO su Beta."""
    from contracts.models import Contract, ContractKind, ContractStatus
    a, b = due_eventi
    ca = Contract.objects.create(
        sponsor=sponsor, event=a, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='ALF-26-101')
    cb = Contract.objects.create(
        sponsor=sponsor_beta, event=b, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='BET-26-102')
    return ca, cb


@pytest.mark.django_db
def test_lista_aziende_filtrata_su_evento_attivo(client, admin_user,
                                                 contratti_separati, due_eventi):
    a, _ = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    testo = client.get(reverse('admin:sponsors_sponsor_changelist')).content.decode()
    assert 'Test Sponsor S.r.l.' in testo      # contratto su Alfa
    assert 'Beta Pharma' not in testo          # contratto solo su Beta


@pytest.mark.django_db
def test_lista_aziende_completa_senza_evento_attivo(client, admin_user,
                                                    contratti_separati):
    client.force_login(admin_user)
    _scegli(client, 'tutti')
    testo = client.get(reverse('admin:sponsors_sponsor_changelist')).content.decode()
    assert 'Test Sponsor S.r.l.' in testo and 'Beta Pharma' in testo


@pytest.mark.django_db
def test_lista_contatti_filtrata_su_evento_attivo(client, admin_user, sponsor,
                                                  sponsor_beta, contratti_separati,
                                                  due_eventi):
    from sponsors.models import Contact, ContactRole
    Contact.objects.create(sponsor=sponsor, full_name='Carla Alfa',
                           email='carla.alfa@test.it', roles=[ContactRole.OPERATIONAL])
    Contact.objects.create(sponsor=sponsor_beta, full_name='Bruno Beta',
                           email='bruno.beta@test.it', roles=[ContactRole.OPERATIONAL])
    a, _ = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    testo = client.get(reverse('admin:sponsors_contact_changelist')).content.decode()
    assert 'carla.alfa@test.it' in testo
    assert 'bruno.beta@test.it' not in testo


@pytest.mark.django_db
def test_autocomplete_sponsor_resta_anagrafica_completa(client, admin_user,
                                                        contratti_separati, due_eventi):
    """Sul form del nuovo contratto la scelta dello sponsor pesca
    dall'anagrafica GENERALE anche con un evento attivo."""
    import json
    a, _ = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    resp = client.get('/admin/autocomplete/', {
        'app_label': 'contracts', 'model_name': 'contract',
        'field_name': 'sponsor', 'term': 'Beta'})
    assert resp.status_code == 200
    risultati = json.loads(resp.content)['results']
    assert any('Beta Pharma' in r['text'] for r in risultati)


@pytest.mark.django_db
def test_scheda_azienda_fuori_evento_si_apre(client, admin_user, sponsor_beta,
                                             contratti_separati, due_eventi):
    """Un link diretto alla scheda di un'azienda di un ALTRO evento
    deve aprirsi (niente 404): il filtro vale solo per le liste."""
    a, _ = due_eventi
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    url = reverse('admin:sponsors_sponsor_change', args=[sponsor_beta.pk])
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_scheda_contratto_altro_evento_si_apre(client, admin_user,
                                               contratti_separati, due_eventi):
    """Vale anche per i modelli-evento: la scheda di un contratto di un
    altro evento resta raggiungibile via link diretto."""
    a, _ = due_eventi
    _, cb = contratti_separati
    client.force_login(admin_user)
    _scegli(client, str(a.pk))
    url = reverse('admin:contracts_contract_change', args=[cb.pk])
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_azienda_con_solo_contratto_cestinato_non_compare(client, admin_user,
                                                          sponsor_beta,
                                                          contratti_separati,
                                                          due_eventi):
    _, b = due_eventi
    _, cb = contratti_separati
    client.force_login(admin_user)
    _scegli(client, str(b.pk))
    testo = client.get(reverse('admin:sponsors_sponsor_changelist')).content.decode()
    assert 'Beta Pharma' in testo
    cb.delete()  # soft delete: il contratto finisce nel cestino
    testo = client.get(reverse('admin:sponsors_sponsor_changelist')).content.decode()
    assert 'Beta Pharma' not in testo


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

"""PASS ALLESTIMENTO: azione sulla lista dei contratti, email allo Sponsor in
copia all'amministrazione, data d'invio visibile in colonna e nel filtro."""
from datetime import date, time

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services import pass_allestimento as pa
from events.models import Event, EventSetupDay, SetupKind

LISTA = '/admin/contracts/contract/'


@pytest.fixture
def evento(db):
    ev = Event.objects.create(
        name={'it': 'Congresso Pass'}, code='PAS',
        start_date=date(2027, 2, 25), end_date=date(2027, 2, 27),
        magazzino_indirizzo='Magazzino XYZ\nVia Calzoni 1/5 - Bologna',
        magazzino_dettagli='Ricevimento merci 22-24/02, ore 9-17')
    EventSetupDay.objects.create(event=ev, kind=SetupKind.ALLESTIMENTO,
                                 date=date(2027, 2, 24), start_time=time(8),
                                 end_time=time(21), notes='solo preallestiti')
    EventSetupDay.objects.create(event=ev, kind=SetupKind.DISALLESTIMENTO,
                                 date=date(2027, 2, 27), start_time=time(17),
                                 end_time=time(23, 59))
    return ev


@pytest.fixture
def contratto(evento, sponsor, contact):
    return Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PAS-001')


@pytest.fixture
def regia(client, db):
    u = get_user_model().objects.create_superuser(
        username='regia', email='regia@test.it', password='AdminPass123!')
    client.force_login(u)
    return client


def test_email_con_tutte_le_indicazioni(contratto):
    assert pa.invia(contratto) == 'contact@test.it'
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert m.to == ['contact@test.it']
    assert 'amministrazione@valet.it' in m.cc
    assert 'PASS ALLESTIMENTO' in m.subject and 'Congresso Pass' in m.subject
    html = m.alternatives[0][0]
    for atteso in ('COMPLIMENTI', 'hanno superato tutti i passaggi',
                   'Mercoledì 24/02/2027', '08:00 – 21:00', 'solo preallestiti',
                   'Disallestimento', '17:00 – 23:59', 'Magazzino XYZ',
                   'Via Calzoni 1/5', 'Ricevimento merci', 'porto franco', 'PAS-001'):
        assert atteso in html, atteso
    contratto.refresh_from_db()
    assert contratto.pass_allestimento_inviato_il is not None


def test_in_inglese_per_contratto_en(contratto):
    contratto.language = 'en'
    contratto.save(update_fields=['language'])
    pa.invia(contratto)
    m = mail.outbox[0]
    assert 'SET-UP PASS' in m.subject
    html = m.alternatives[0][0]
    assert 'CONGRATULATIONS' in html and 'Wednesday 24/02/2027' in html


def test_azione_conferma_poi_invia(regia, contratto):
    dati = {'action': 'action_invia_pass_allestimento', '_selected_action': [contratto.pk]}
    r = regia.post(LISTA, dati)
    assert r.status_code == 200 and 'Invia PASS allestimento' in r.content.decode()
    assert not mail.outbox                      # prima la conferma, niente invio
    regia.post(LISTA, {**dati, '_pass_confermato': '1'})
    assert len(mail.outbox) == 1
    contratto.refresh_from_db()
    assert contratto.pass_allestimento_inviato_il


def test_gia_inviato_non_riparte_senza_spunta(regia, contratto):
    pa.invia(contratto)
    dati = {'action': 'action_invia_pass_allestimento', '_selected_action': [contratto.pk],
            '_pass_confermato': '1'}
    regia.post(LISTA, dati)
    assert len(mail.outbox) == 1
    regia.post(LISTA, {**dati, 'reinvia': '1'})
    assert len(mail.outbox) == 2


def test_annullato_non_riceve(regia, contratto):
    Contract.objects.filter(pk=contratto.pk).update(status=ContractStatus.CANCELLED)
    regia.post(LISTA, {'action': 'action_invia_pass_allestimento',
                       '_selected_action': [contratto.pk], '_pass_confermato': '1'})
    assert not mail.outbox


def test_colonna_e_filtro(regia, contratto):
    html = regia.get(LISTA).content.decode()
    assert 'PASS allestimento' in html
    assert 'PAS-001' in regia.get(LISTA + '?pass_allestimento=no').content.decode()
    pa.invia(contratto)
    assert 'PAS-001' not in regia.get(LISTA + '?pass_allestimento=no').content.decode()
    assert 'PAS-001' in regia.get(LISTA + '?pass_allestimento=si').content.decode()


def test_anteprima_non_invia(regia, contratto):
    r = regia.get(f'{LISTA}{contratto.pk}/anteprima-pass-allestimento/')
    assert r.status_code == 200
    assert 'ANTEPRIMA' in r.content.decode() and 'COMPLIMENTI' in r.content.decode()
    assert not mail.outbox
    contratto.refresh_from_db()
    assert contratto.pass_allestimento_inviato_il is None

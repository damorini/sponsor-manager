"""Multi-azienda: la stessa persona (stesso login) gestisce piu' aziende.

- Al login con 2+ contatti -> maschera 'Scegli l'azienda'.
- La scelta vive in sessione; le pagine usano l'azienda attiva.
- 'Cambia azienda' permette di passare all'altra.
- Con 1 solo contatto il flusso resta invariato (nessuna maschera).
"""
import pytest
from django.utils import timezone

from core.models import OrganizerSettings
from sponsors.models import Sponsor, Contact, ContactRole
from users.models import User, UserRole


@pytest.fixture
def user_due_aziende(db):
    user = User.objects.create_user(
        username='multi@test.it', email='multi@test.it',
        password='Multi1234!', is_active=True)
    user.role = UserRole.SPONSOR
    user.save()
    versione = OrganizerSettings.load().privacy_policy_version or '1.0'
    aziende = []
    for nome in ('Alfa Srl', 'Beta Spa'):
        sp = Sponsor.objects.create(legal_name=nome, address_country='IT')
        Contact.objects.create(
            sponsor=sp, portal_user=user, full_name=f'Mario Rossi ({nome})',
            email='multi@test.it', roles=[ContactRole.OPERATIONAL],
            has_portal_access=True,
            privacy_accepted_at=timezone.now(), privacy_policy_version=versione,
            welcome_seen_at=timezone.now(),
        )
        aziende.append(sp)
    return user, aziende


@pytest.mark.django_db
def test_login_multiazienda_chiede_azienda(client, user_due_aziende):
    user, _ = user_due_aziende
    resp = client.post('/portal/login/', {'username': 'multi@test.it',
                                          'password': 'Multi1234!'})
    assert resp.status_code == 302
    assert '/portal/scegli-azienda/' in resp.url


@pytest.mark.django_db
def test_maschera_mostra_le_aziende_e_la_scelta_funziona(client, user_due_aziende):
    user, (alfa, beta) = user_due_aziende
    client.force_login(user)
    resp = client.get('/portal/scegli-azienda/')
    html = resp.content.decode()
    assert resp.status_code == 200
    assert 'Alfa Srl' in html and 'Beta Spa' in html

    contatto_beta = Contact.objects.get(sponsor=beta)
    resp = client.post('/portal/scegli-azienda/', {'contact_id': str(contatto_beta.pk)})
    assert resp.status_code == 302
    # la dashboard ora lavora su Beta
    resp = client.get('/portal/profilo/')
    assert 'Beta Spa' in resp.content.decode()


@pytest.mark.django_db
def test_cambia_azienda(client, user_due_aziende):
    user, (alfa, beta) = user_due_aziende
    client.force_login(user)
    c_alfa = Contact.objects.get(sponsor=alfa)
    c_beta = Contact.objects.get(sponsor=beta)
    client.post('/portal/scegli-azienda/', {'contact_id': str(c_alfa.pk)})
    assert 'Alfa Srl' in client.get('/portal/profilo/').content.decode()
    client.post('/portal/scegli-azienda/', {'contact_id': str(c_beta.pk)})
    assert 'Beta Spa' in client.get('/portal/profilo/').content.decode()


@pytest.mark.django_db
def test_senza_scelta_le_pagine_rimandano_alla_maschera(client, user_due_aziende):
    user, _ = user_due_aziende
    client.force_login(user)   # nessuna scelta in sessione
    resp = client.get('/portal/pagamenti/')
    assert resp.status_code == 302
    assert '/portal/scegli-azienda/' in resp.url


@pytest.mark.django_db
def test_utente_monoazienda_non_vede_la_maschera(client_authenticated, contact):
    # fixture standard: 1 solo contatto -> selezione automatica, niente maschera
    resp = client_authenticated.get('/portal/profilo/')
    assert resp.status_code == 200

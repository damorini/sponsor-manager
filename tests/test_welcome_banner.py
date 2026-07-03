"""Messaggio di benvenuto al primo accesso nel portale (pagina 'I miei dati').

- Un contatto nuovo (welcome_seen_at NULL) vede il banner.
- Dopo il dismiss (o dopo il primo salvataggio) il banner sparisce e non torna.
"""
import pytest


@pytest.mark.django_db
def test_banner_appare_al_primo_accesso(client_authenticated, contact):
    assert contact.welcome_seen_at is None
    resp = client_authenticated.get('/portal/profilo/')
    assert resp.status_code == 200
    assert 'Benvenuto nella tua area riservata' in resp.content.decode()


@pytest.mark.django_db
def test_dismiss_chiude_il_banner(client_authenticated, contact):
    # chiudo il benvenuto
    resp = client_authenticated.post('/portal/profilo/', {'azione': 'dismiss_welcome'})
    assert resp.status_code == 302
    contact.refresh_from_db()
    assert contact.welcome_seen_at is not None
    # non ricompare piu'
    resp = client_authenticated.get('/portal/profilo/')
    assert 'Benvenuto nella tua area riservata' not in resp.content.decode()


@pytest.mark.django_db
def test_salvataggio_chiude_il_banner(client_authenticated, contact):
    # un salvataggio normale dei dati marca il benvenuto come visto
    resp = client_authenticated.post('/portal/profilo/', {
        'sponsor_legal_name': 'Test Sponsor S.r.l.',
        'contact_email': 'contact@test.it',
        'contact_last_name': 'Rossi',
    })
    assert resp.status_code == 302
    contact.refresh_from_db()
    assert contact.welcome_seen_at is not None

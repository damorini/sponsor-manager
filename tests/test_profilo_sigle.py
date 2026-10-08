"""Portale, profilo: province e paese sono campi da 2 caratteri. Scrivere
"Roma" o "Italia" faceva fallire il salvataggio con un errore del database
(caso reale ACEA MEDICA / D.T.A.). Ora le sigle si normalizzano e il resto
riceve un messaggio chiaro."""
import pytest
from django.urls import reverse


def _dati(sponsor, **extra):
    dati = {'sponsor_legal_name': sponsor.legal_name,
            'contact_last_name': 'Rossi', 'contact_email': 'x@example.org'}
    dati.update(extra)
    return dati


@pytest.mark.django_db
def test_provincia_per_esteso_non_rompe_il_salvataggio(client_authenticated, sponsor):
    resp = client_authenticated.post(
        reverse('portal:profile'),
        _dati(sponsor, sponsor_address_province='Roma'), follow=True)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'sigla di 2 lettere' in html
    assert 'character varying' not in html
    sponsor.refresh_from_db()
    assert sponsor.address_province != 'Roma'


@pytest.mark.django_db
def test_sigle_normalizzate(client_authenticated, sponsor):
    client_authenticated.post(
        reverse('portal:profile'),
        _dati(sponsor, sponsor_address_province='rm',
              sponsor_address_country='Italia'), follow=True)
    sponsor.refresh_from_db()
    assert sponsor.address_province == 'RM'
    assert sponsor.address_country == 'IT'


@pytest.mark.django_db
def test_campo_provincia_limitato_nel_browser(client_authenticated):
    html = client_authenticated.get(reverse('portal:profile')).content.decode()
    assert 'name="sponsor_address_province"' in html
    assert 'maxlength="2"' in html
    assert 'Sigla di 2 lettere' in html


@pytest.mark.django_db
def test_firmatario_provincia_per_esteso(client_authenticated, sponsor, contact):
    resp = client_authenticated.post(reverse('portal:profile'), {
        'azione': 'edit_contact', 'contact_id': contact.id,
        'mod_full_name': 'Mario Rossi', 'mod_email': contact.email,
        'mod_is_signer': 'on', 'mod_birth_province': 'Milano',
    }, follow=True)
    assert resp.status_code == 200
    assert 'sigla di 2 lettere' in resp.content.decode()

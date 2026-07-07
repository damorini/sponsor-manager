"""Domanda 'Azienda farmaceutica?': flag sul modello Sponsor con Codice SIS
condizionale (richiesto solo se flaggato) e salvataggio da 'I miei dati'."""
import pytest


@pytest.mark.django_db
def test_codice_sis_richiesto_solo_se_farmaceutica(sponsor):
    # Non farmaceutica: il Codice SIS non e' tra i campi mancanti
    assert 'Codice SIS' not in sponsor.campi_anagrafica_mancanti()
    # Farmaceutica senza codice: diventa obbligatorio
    sponsor.is_pharma_company = True
    assert 'Codice SIS' in sponsor.campi_anagrafica_mancanti()
    # Farmaceutica con codice: ok
    sponsor.sis_code = 'SIS123456'
    assert 'Codice SIS' not in sponsor.campi_anagrafica_mancanti()


@pytest.mark.django_db
def test_salvataggio_flag_e_codice_dal_portale(client_authenticated, sponsor, contact):
    resp = client_authenticated.post('/portal/profilo/', {
        'sponsor_legal_name': sponsor.legal_name,
        'sponsor_vat_number': sponsor.vat_number,
        'sponsor_is_pharma_company': 'on',
        'sponsor_sis_code': 'SIS123456',
    })
    assert resp.status_code == 302
    sponsor.refresh_from_db()
    assert sponsor.is_pharma_company is True
    assert sponsor.sis_code == 'SIS123456'


@pytest.mark.django_db
def test_deflag_dal_portale(client_authenticated, sponsor, contact):
    sponsor.is_pharma_company = True
    sponsor.sis_code = 'SIS123456'
    sponsor.save()
    # Checkbox non spuntata: nel POST il parametro non arriva
    resp = client_authenticated.post('/portal/profilo/', {
        'sponsor_legal_name': sponsor.legal_name,
        'sponsor_sis_code': 'SIS123456',
    })
    assert resp.status_code == 302
    sponsor.refresh_from_db()
    assert sponsor.is_pharma_company is False


@pytest.mark.django_db
def test_pagina_profilo_mostra_domanda(client_authenticated, sponsor):
    resp = client_authenticated.get('/portal/profilo/')
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'sponsor_is_pharma_company' in html
    assert 'sponsor_sis_code' in html

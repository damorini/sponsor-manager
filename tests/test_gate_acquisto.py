"""Gate anagrafica: con anagrafica incompleta lo sponsor NAVIGA comunque il
portale, ma il flusso di ACQUISTO (catalogo/carrello/checkout) resta bloccato
finche' non completa i dati di fatturazione."""
import pytest


@pytest.mark.django_db
def test_pagine_normali_navigabili_con_anagrafica_incompleta(client_authenticated, sponsor):
    # Il sponsor della fixture e' incompleto (mancano sdi, pec, indirizzo, ecc.)
    assert sponsor.campi_anagrafica_mancanti()
    # Una pagina non-acquisto deve caricare (prima veniva rimandata a profilo)
    resp = client_authenticated.get('/portal/pagamenti/')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_catalogo_bloccato_con_anagrafica_incompleta(client_authenticated, sponsor):
    assert sponsor.campi_anagrafica_mancanti()
    resp = client_authenticated.get('/portal/catalog/')
    assert resp.status_code == 302
    assert '/portal/profilo/' in resp.url


@pytest.mark.django_db
def test_catalogo_ok_con_anagrafica_completa(client_authenticated, sponsor):
    sponsor.sdi_code = 'ABCDEFG'
    sponsor.pec_email = 'pec@demo.it'
    sponsor.address_street = 'Via Roma 1'
    sponsor.address_city = 'Bologna'
    sponsor.address_zip = '40100'
    sponsor.address_province = 'BO'
    sponsor.website = 'https://demo.it'
    sponsor.business_description = 'Distributore'
    sponsor.save()
    assert sponsor.campi_anagrafica_mancanti() == []
    resp = client_authenticated.get('/portal/catalog/')
    # Non deve piu' rimandare a profilo
    assert not (resp.status_code == 302 and '/portal/profilo/' in getattr(resp, 'url', ''))

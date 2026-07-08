"""Pagina 'Ci siamo quasi' al posto del Forbidden bianco.

Chi arriva al portale senza un profilo sponsor utilizzabile (utente non
sponsor, o sponsor senza Contact collegato) non deve piu' vedere la pagina
bianca "riservata ad utenti con i privilegi di accesso", ma una pagina con
la grafica del portale che spiega di fare il primo accesso con le
credenziali ricevute (o scrivere a helpdesk@valet.it). Status 403 invariato.
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_utente_non_sponsor_vede_ci_siamo_quasi(client):
    from django.contrib.auth import get_user_model
    operatore = get_user_model().objects.create_user(
        username='op1', email='op1@test.it', password='TestPassword123!',
        is_active=True)  # ruolo default: NON sponsor
    client.force_login(operatore)

    resp = client.get(reverse('portal:dashboard'))
    assert resp.status_code == 403
    html = resp.content.decode()
    assert 'Ci siamo quasi' in html
    assert 'helpdesk@valet.it' in html
    assert reverse('portal:login') in html


@pytest.mark.django_db
def test_sponsor_senza_contact_vede_ci_siamo_quasi(client, user_sponsor):
    # user_sponsor ha ruolo sponsor ma NESSUN Contact collegato
    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:dashboard'))
    assert resp.status_code == 403
    assert 'Ci siamo quasi' in resp.content.decode()


@pytest.mark.django_db
def test_sponsor_regolare_non_la_vede(client_authenticated):
    resp = client_authenticated.get(reverse('portal:dashboard'))
    assert resp.status_code == 200
    assert 'Ci siamo quasi' not in resp.content.decode()

"""
Config SMTP: istruzioni chiare per il test e vista diretta "test invio".

- La change form del singleton EmailSettings spiega passo-passo come fare
  il test e offre un link diretto alla pagina di invio prova.
- La pagina admin:core_emailsettings_test_invio invia l'email di prova
  senza passare dall'azione dell'elenco.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import EmailSettings

User = get_user_model()


@pytest.fixture
def staff_client(client, db):
    op = User.objects.create_user(
        username='op_smtp', email='op.smtp@test.it', password='x',
        is_staff=True, is_superuser=True, is_active=True)
    client.force_login(op)
    return client


@pytest.mark.django_db
def test_pagina_test_invio_accessibile(staff_client):
    resp = staff_client.get(reverse('admin:core_emailsettings_test_invio'))
    assert resp.status_code == 200
    assert 'Invia a' in resp.content.decode()


@pytest.mark.django_db
def test_post_indirizzo_non_valido(staff_client):
    resp = staff_client.post(
        reverse('admin:core_emailsettings_test_invio'),
        {'apply_test': '1', 'test_email': 'non-valido'}, follow=True)
    assert 'Indirizzo email non valido' in resp.content.decode()


@pytest.mark.django_db
def test_post_smtp_non_configurato(staff_client):
    # Singleton di default: enabled=False -> get_connection() None -> warning
    EmailSettings.load()
    resp = staff_client.post(
        reverse('admin:core_emailsettings_test_invio'),
        {'apply_test': '1', 'test_email': 'destinatario@test.it'}, follow=True)
    assert 'Configurazione SMTP non attiva' in resp.content.decode()


@pytest.mark.django_db
def test_istruzioni_nella_change_form(staff_client):
    s = EmailSettings.load()
    resp = staff_client.get(
        reverse('admin:core_emailsettings_change', args=[s.pk]))
    html = resp.content.decode()
    assert 'Come fare il test' in html
    assert reverse('admin:core_emailsettings_test_invio') in html

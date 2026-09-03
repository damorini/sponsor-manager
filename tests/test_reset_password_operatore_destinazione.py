"""Reset password di un OPERATORE: l'email e la pagina finale devono
indirizzare al BACKOFFICE, non al portale sponsor (dove un operatore viene
respinto). La pagina per impostare la password resta una sola per tutti."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def operatore(db):
    u = User.objects.create_user(
        username='elisa_test', email='elisa.test@valet.it',
        password='Vecchia123!', is_active=True, is_staff=True)
    u.role = 'operator'
    u.save()
    return u


@pytest.fixture
def cliente(db):
    u = User.objects.create_user(
        username='cli_test', email='cli.test@azienda.it',
        password='Vecchia123!', is_active=True)
    u.role = 'sponsor'
    u.save()
    return u


def _chiedi_reset(client, email):
    mail.outbox.clear()
    client.post(reverse('portal:password_reset'), {'email': email})
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    corpo = m.body + ''.join(a for a, _t in m.alternatives)
    return m, corpo


@pytest.mark.django_db
def test_email_operatore_parla_di_backoffice(client, operatore):
    m, corpo = _chiedi_reset(client, operatore.email)
    assert 'Backoffice' in m.subject
    assert 'Portale sponsor' not in m.subject
    assert 'backoffice' in corpo.lower()
    assert '/admin/' in corpo          # dove accedere dopo


@pytest.mark.django_db
def test_email_cliente_resta_sul_portale(client, cliente):
    m, corpo = _chiedi_reset(client, cliente.email)
    assert 'Portale sponsor' in m.subject
    assert 'backoffice' not in corpo.lower()


@pytest.mark.django_db
def test_dopo_il_reset_operatore_va_al_backoffice(client, operatore):
    _m, corpo = _chiedi_reset(client, operatore.email)
    mm = re.search(r'/portal/password-reset/([^/]+)/([^/\s"<]+)/', corpo)
    assert mm, 'link di conferma non trovato'
    url = reverse('portal:password_reset_confirm',
                  kwargs={'uidb64': mm.group(1), 'token': mm.group(2)})
    resp = client.post(url, {'new_password1': 'NuovaPassSicura26!',
                             'new_password2': 'NuovaPassSicura26!'})
    assert resp.status_code == 302
    finale = client.get(resp.url)
    html = finale.content.decode()
    assert 'Vai al backoffice' in html
    assert 'href="/admin/"' in html
    operatore.refresh_from_db()
    assert operatore.check_password('NuovaPassSicura26!')


@pytest.mark.django_db
def test_dopo_il_reset_cliente_va_al_portale(client, cliente):
    _m, corpo = _chiedi_reset(client, cliente.email)
    mm = re.search(r'/portal/password-reset/([^/]+)/([^/\s"<]+)/', corpo)
    url = reverse('portal:password_reset_confirm',
                  kwargs={'uidb64': mm.group(1), 'token': mm.group(2)})
    resp = client.post(url, {'new_password1': 'NuovaPassSicura26!',
                             'new_password2': 'NuovaPassSicura26!'})
    html = client.get(resp.url).content.decode()
    assert 'Vai al backoffice' not in html
    assert reverse('portal:login') in html

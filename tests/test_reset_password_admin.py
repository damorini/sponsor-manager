"""Reset password per gli utenti del backoffice.

- La login dell'admin mostra il link 'Password dimenticati?' (compare da solo
  quando esiste l'URL con nome admin_password_reset).
- /admin/password_reset/ porta al flusso di reset del portale.
- Il flusso di reset vale ora per QUALSIASI utente attivo (prima era
  limitato al ruolo sponsor: un operatore non poteva recuperare la password).
- Nell'admin Utenti c'e' l'azione 'Invia email di RESET PASSWORD'.
"""
import pytest
from django.core import mail
from django.urls import reverse


@pytest.fixture
def operatore(db):
    from django.contrib.auth import get_user_model
    u = get_user_model().objects.create_user(
        username='op_reset', email='op_reset@test.it',
        password='VecchiaPass123!', is_active=True)
    u.role = 'operator'
    u.save()
    return u


@pytest.mark.django_db
def test_login_admin_mostra_link_reset(client):
    resp = client.get('/admin/login/')
    assert resp.status_code == 200
    assert 'password_reset' in resp.content.decode()


@pytest.mark.django_db
def test_admin_password_reset_redirige_al_portale(client):
    resp = client.get('/admin/password_reset/')
    assert resp.status_code == 302
    assert resp.url == reverse('portal:password_reset')


@pytest.mark.django_db
def test_reset_funziona_anche_per_operatori(client, operatore):
    mail.outbox.clear()
    resp = client.post(reverse('portal:password_reset'),
                       {'email': 'op_reset@test.it'})
    assert resp.status_code == 302  # -> pagina 'email inviata'
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ['op_reset@test.it']
    corpo = mail.outbox[0].body + ''.join(
        alt for alt, _m in mail.outbox[0].alternatives)
    assert 'password-reset' in corpo  # link di conferma presente


@pytest.mark.django_db
def test_azione_admin_invia_reset(client, operatore):
    from django.contrib.auth import get_user_model
    boss = get_user_model().objects.create_superuser(
        username='boss_reset', email='boss_reset@test.it', password='Xx12345678!')
    client.force_login(boss)

    mail.outbox.clear()
    resp = client.post(
        reverse('admin:users_user_changelist'),
        {'action': 'action_invia_reset_password',
         '_selected_action': [str(operatore.id)]},
        follow=True,
    )
    assert resp.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ['op_reset@test.it']

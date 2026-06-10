"""
#6 L'email di reset password deve esistere e renderizzare in IT e EN col link
di reset. Prima mancava il template -> send_email sollevava e l'email non
partiva affatto.
"""
import pytest


@pytest.mark.django_db
def test_password_reset_email_renders_it_and_en(mailoutbox):
    from django.contrib.auth import get_user_model
    from contracts.services.email_sender import send_email

    User = get_user_model()
    u = User.objects.create_user(username='pr', email='pr@test.it', password='x')
    url = 'https://x.it/portal/password-reset/abc/def/'

    send_email(template_name='password_reset', context={'user': u, 'reset_url': url},
               to=[u.email], subject='S-IT', language='it')
    send_email(template_name='password_reset', context={'user': u, 'reset_url': url},
               to=[u.email], subject='S-EN', language='en')

    assert len(mailoutbox) == 2
    it_body, en_body = mailoutbox[0].body, mailoutbox[1].body
    assert url in it_body and url in en_body
    assert 'Reimposta' in it_body          # corpo italiano
    assert 'Reset your password' in en_body  # corpo inglese

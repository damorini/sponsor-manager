"""
#5 Le notifiche di testo semplice devono usare la connessione SMTP del
pannello (core.models.EmailSettings, provider Brevo) come le altre email,
non il send_mail nudo di Django (che in prod cade sul backend console).

send_plain_email(subject, body, recipients) instrada via
EmailSettings.get_connection() quando configurato, con from_full come mittente.
"""
import pytest

from contracts.services.email_sender import send_plain_email


@pytest.mark.django_db
def test_no_recipients_is_noop(mailoutbox):
    assert send_plain_email('S', 'B', []) == 0
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_fallback_default_from_when_panel_disabled(settings, mailoutbox):
    # EmailSettings non abilitato -> get_connection None -> backend di default
    n = send_plain_email('Oggetto', 'Corpo', ['op@valet.it'])
    assert n == 1
    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.subject == 'Oggetto'
    assert msg.to == ['op@valet.it']
    assert msg.from_email == settings.DEFAULT_FROM_EMAIL


@pytest.mark.django_db
def test_uses_panel_connection_and_from(monkeypatch, mailoutbox):
    from core.models import EmailSettings
    from django.core.mail import get_connection as dj_get_connection

    es = EmailSettings.load()
    es.enabled = True
    es.host = 'mail.valet.it'
    es.from_email = 'noreply@valet.it'
    es.from_name = 'Sponsor Manager'
    es.save()

    # Evita SMTP reale: la "connessione del pannello" usa il backend locmem
    # (cosi' l'email viene catturata in mailoutbox) ma il from resta from_full.
    monkeypatch.setattr(
        EmailSettings, 'get_connection',
        lambda self: dj_get_connection(
            'django.core.mail.backends.locmem.EmailBackend'))

    send_plain_email('Oggetto', 'Corpo', ['op@valet.it'])

    assert len(mailoutbox) == 1
    assert mailoutbox[0].from_email == 'Sponsor Manager <noreply@valet.it>'

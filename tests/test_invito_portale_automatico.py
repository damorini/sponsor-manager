"""Invito al portale automatico alla prima mail verso un contatto dello sponsor."""
import pytest
from django.core import mail

from contracts.services.email_sender import send_email


def _manda(sponsor, *to):
    return send_email(template_name='x', context={'sponsor': sponsor},
                      subject='Prova', to=list(to),
                      custom_body_html='<p>Gentile {{ contact.full_name }}</p>')


@pytest.mark.django_db
def test_primo_contatto_riceve_invito_una_volta(sponsor):
    from sponsors.models import Contact
    nuovo = Contact.objects.create(sponsor=sponsor, full_name='Anna Neri',
                                   email='anna@test.it')
    mail.outbox.clear()
    com = _manda(sponsor, 'anna@test.it')
    assert com.inviti_portale == ['anna@test.it']
    assert len(mail.outbox) == 2            # la mail + l'invito
    assert 'portale' in mail.outbox[1].subject.lower()
    nuovo.refresh_from_db()
    assert nuovo.portal_user_id

    mail.outbox.clear()
    com = _manda(sponsor, 'anna@test.it')   # seconda mail: niente invito
    assert com.inviti_portale == []
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_chi_ha_gia_accesso_o_non_e_contatto_non_invitato(sponsor, contact):
    mail.outbox.clear()
    com = _manda(sponsor, contact.email, 'esterno@altro.it')
    assert com.inviti_portale == []
    assert len(mail.outbox) == 2            # solo le due mail, nessun invito


@pytest.mark.django_db
def test_mail_senza_sponsor_nessun_invito(db):
    mail.outbox.clear()
    send_email(template_name='x', context={}, subject='Staff', to=['a@valet.it'],
               custom_body_html='<p>Ciao</p>')
    assert len(mail.outbox) == 1

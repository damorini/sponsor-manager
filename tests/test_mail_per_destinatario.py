"""Mail allo sponsor con piu' destinatari: una per persona, col suo nome."""
import pytest
from django.core import mail

from contracts.services.email_sender import send_email


@pytest.mark.django_db
def test_una_mail_per_persona_col_suo_nome(sponsor, contact):
    from sponsors.models import Contact
    Contact.objects.create(sponsor=sponsor, first_name='Giulia', last_name='Verdi',
                           full_name='Giulia Verdi', email='giulia@test.it')
    mail.outbox.clear()
    send_email(
        template_name='x', context={'sponsor': sponsor}, subject='Prova',
        to=[contact.email, 'giulia@test.it', 'staff@valet.it'],
        cc=['amministrazione@valet.it'],
        custom_body_html='<p>Gentile {{ contact.full_name }},</p>',
    )
    assert len(mail.outbox) == 3
    corpo = {m.to[0]: m.alternatives[0][0] for m in mail.outbox}
    assert all(len(m.to) == 1 for m in mail.outbox)
    assert 'Gentile Test Contact' in corpo[contact.email]
    assert 'Gentile Giulia Verdi' in corpo['giulia@test.it']
    assert sponsor.legal_name in corpo['staff@valet.it']
    # la copia all'amministrazione una volta sola
    assert sum(1 for m in mail.outbox if 'amministrazione@valet.it' in m.cc) == 1


@pytest.mark.django_db
def test_mail_senza_sponsor_resta_una(db):
    mail.outbox.clear()
    send_email(template_name='x', context={}, subject='Staff',
               to=['a@valet.it', 'b@valet.it'], custom_body_html='<p>Ciao</p>')
    assert len(mail.outbox) == 1 and len(mail.outbox[0].to) == 2

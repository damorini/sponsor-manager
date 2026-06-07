"""
Notifica email al cliente quando la segreteria (operatore) scrive un messaggio.
"""
import pytest
from django.contrib import admin as djadmin
from django.test import RequestFactory

from users.models import User
from sponsors.admin import PortalMessageAdmin
from sponsors.models import Contact, ContactRole, MessageSender, PortalMessage


@pytest.mark.django_db
def test_email_al_cliente_quando_operatore_scrive(sponsor, mailoutbox):
    Contact.objects.create(
        sponsor=sponsor, full_name='Cliente', email='cliente@test.it',
        has_portal_access=True, roles=[ContactRole.OPERATIONAL])
    op = User.objects.create_user(username='op@test.it', email='op@test.it',
                                  password='x')
    rf = RequestFactory()
    req = rf.post('/admin/sponsors/portalmessage/add/')
    req.user = op
    ma = PortalMessageAdmin(PortalMessage, djadmin.site)
    obj = PortalMessage(sponsor=sponsor, sender=MessageSender.OPERATOR,
                        body='Ti rispondo io', is_active=True)
    ma.save_model(req, obj, None, change=False)

    assert len(mailoutbox) == 1
    assert 'cliente@test.it' in mailoutbox[0].to


@pytest.mark.django_db
def test_nessuna_email_se_nessun_contatto_portale(sponsor, mailoutbox):
    # contatto SENZA accesso portale -> nessun destinatario
    Contact.objects.create(
        sponsor=sponsor, full_name='NoPortal', email='nop@test.it',
        has_portal_access=False, roles=[ContactRole.OPERATIONAL])
    op = User.objects.create_user(username='op2@test.it', email='op2@test.it',
                                  password='x')
    rf = RequestFactory()
    req = rf.post('/x/'); req.user = op
    ma = PortalMessageAdmin(PortalMessage, djadmin.site)
    obj = PortalMessage(sponsor=sponsor, sender=MessageSender.OPERATOR,
                        body='msg', is_active=True)
    ma.save_model(req, obj, None, change=False)
    assert len(mailoutbox) == 0

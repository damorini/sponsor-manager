"""Invito al portale: protezioni del 27/08.

1. L'email di un account OPERATORE del backoffice non puo' essere usata come
   accesso cliente (prima l'invito lo declassava a sponsor e ne resettava la
   password; il portale comunque lo respingeva con 'Ci siamo quasi').
2. Re-invitare un cliente che ha GIA' usato il portale (es. per un altro
   congresso) NON gli cambia la password: le credenziali restano valide.
3. Re-invitare un cliente mai entrato rigenera la password temporanea.
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from portal.services.invitation import invite_contact_to_portal
from sponsors.models import Contact

User = get_user_model()


@pytest.mark.django_db
def test_email_operatore_rifiutata(sponsor):
    staff = User.objects.create_user(
        username='op_bo', email='operatore@valet.it', password='SegretaBO1!',
        is_staff=True)
    staff.role = 'operator'
    staff.save()
    c = Contact.objects.create(sponsor=sponsor, full_name='Test Operatore',
                               email='operatore@valet.it')
    with pytest.raises(ValueError, match='OPERATORE'):
        invite_contact_to_portal(c, send_email=False)
    staff.refresh_from_db()
    assert staff.role == 'operator'          # non declassato
    assert staff.check_password('SegretaBO1!')  # password intatta


@pytest.mark.django_db
def test_reinvito_utente_gia_attivo_non_resetta_password(sponsor):
    u = User.objects.create_user(
        username='cliente1', email='cliente1@azienda.it', password='SuaPass123!',
        is_active=True)
    u.role = 'sponsor'
    u.last_login = timezone.now()
    u.save()
    c = Contact.objects.create(sponsor=sponsor, full_name='Cliente Uno',
                               email='cliente1@azienda.it')
    user, pwd, created = invite_contact_to_portal(c, send_email=False)
    assert pwd is None and created is False
    user.refresh_from_db()
    assert user.check_password('SuaPass123!')  # credenziali invariate
    c.refresh_from_db()
    assert c.portal_user_id == user.pk and c.has_portal_access


@pytest.mark.django_db
def test_reinvito_utente_mai_entrato_rigenera_password(sponsor):
    u = User.objects.create_user(
        username='cliente2', email='cliente2@azienda.it', password='Vecchia123!',
        is_active=True)
    u.role = 'sponsor'
    u.save()
    assert u.last_login is None
    c = Contact.objects.create(sponsor=sponsor, full_name='Cliente Due',
                               email='cliente2@azienda.it',
                               portal_user=u, has_portal_access=True)
    user, pwd, created = invite_contact_to_portal(c, send_email=False)
    assert pwd and created is False
    user.refresh_from_db()
    assert user.check_password(pwd)
    assert not user.check_password('Vecchia123!')

"""Regressione 28/08: cambiare l'email di un contatto erroneamente collegato a
un account OPERATORE riscriveva email e username dell'account backoffice
(l'operatore 'direzione scuola' si e' ritrovato l'email di un cliente)."""
import pytest
from django.contrib.auth import get_user_model

from sponsors.models import Contact

User = get_user_model()


@pytest.mark.django_db
def test_email_contatto_non_riscrive_utente_staff(sponsor):
    staff = User.objects.create_user(
        username='bo@valet.it', email='bo@valet.it', password='x', is_staff=True)
    staff.role = 'operator'
    staff.save()
    c = Contact.objects.create(sponsor=sponsor, full_name='Contatto Errato',
                               email='bo@valet.it', portal_user=staff,
                               has_portal_access=True)
    c.email = 'cliente.nuovo@azienda.it'
    c.save()
    staff.refresh_from_db()
    assert staff.email == 'bo@valet.it'       # NON riscritta
    assert staff.username == 'bo@valet.it'


@pytest.mark.django_db
def test_email_contatto_sincronizza_utente_sponsor(sponsor):
    u = User.objects.create_user(
        username='cli@azienda.it', email='cli@azienda.it', password='x')
    u.role = 'sponsor'
    u.save()
    c = Contact.objects.create(sponsor=sponsor, full_name='Cliente Ok',
                               email='cli@azienda.it', portal_user=u,
                               has_portal_access=True)
    c.email = 'nuova@azienda.it'
    c.save()
    u.refresh_from_db()
    assert u.email == 'nuova@azienda.it'      # sync normale per i clienti
    assert u.username == 'nuova@azienda.it'

"""
Guida rapida del portale (/portal/guida/): pagina informativa raggiungibile
dallo sponsor, anche con anagrafica incompleta (whitelist nei gate).
"""
import pytest


@pytest.mark.django_db
def test_guida_reachable_and_has_content(client):
    from django.urls import reverse
    from django.utils import timezone
    from django.contrib.auth import get_user_model
    from core.models import OrganizerSettings
    from sponsors.models import Sponsor, Contact, ContactRole
    from users.models import UserRole

    User = get_user_model()
    user = User.objects.create_user(
        username='g_sp', email='g@test.it', password='x', is_active=True)
    user.role = UserRole.SPONSOR
    user.save()
    # Anagrafica VOLUTAMENTE incompleta: la guida deve restare raggiungibile.
    sponsor = Sponsor.objects.create(legal_name='Guida Sponsor', vat_number='99999999999')
    ver = OrganizerSettings.load().privacy_policy_version or '1.0'
    Contact.objects.create(
        portal_user=user, sponsor=sponsor, full_name='G C', email='gc@test.it',
        phone='+390', roles=[ContactRole.OPERATIONAL],
        privacy_accepted_at=timezone.now(), privacy_policy_version=ver)

    client.force_login(user)
    resp = client.get(reverse('portal:guida'))

    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Guida rapida' in html
    assert 'Caricare i file delle scadenze' in html
    assert 'Acquistare servizi' in html

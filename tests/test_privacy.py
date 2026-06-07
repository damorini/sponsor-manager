"""
Privacy nel portale: presa visione obbligatoria al primo accesso + opt-in marketing.
"""
import pytest
from django.urls import reverse

from sponsors.models import Contact, ContactRole


@pytest.fixture
def contatto_no_privacy(db, user_sponsor, sponsor):
    return Contact.objects.create(
        portal_user=user_sponsor, sponsor=sponsor,
        full_name='Senza Privacy', email='nopriv@test.it',
        roles=[ContactRole.OPERATIONAL],
    )


@pytest.mark.django_db
def test_redirect_al_consenso_se_non_accettata(client, user_sponsor, contatto_no_privacy):
    client.force_login(user_sponsor)
    r = client.get(reverse('portal:dashboard'))
    assert r.status_code == 302
    assert reverse('portal:privacy_consent') in r['Location']


@pytest.mark.django_db
def test_accetta_privacy_e_marketing(client, user_sponsor, contatto_no_privacy):
    client.force_login(user_sponsor)
    r = client.post(reverse('portal:privacy_consent'),
                    {'privacy': 'on', 'marketing': 'on'})
    assert r.status_code == 302
    contatto_no_privacy.refresh_from_db()
    assert contatto_no_privacy.privacy_accepted_at is not None
    assert contatto_no_privacy.privacy_policy_version  # versione registrata
    assert contatto_no_privacy.marketing_consent is True
    assert contatto_no_privacy.marketing_consent_at is not None
    # ora la dashboard è accessibile
    assert client.get(reverse('portal:dashboard')).status_code == 200


@pytest.mark.django_db
def test_accetta_senza_marketing(client, user_sponsor, contatto_no_privacy):
    client.force_login(user_sponsor)
    client.post(reverse('portal:privacy_consent'), {'privacy': 'on'})
    contatto_no_privacy.refresh_from_db()
    assert contatto_no_privacy.privacy_accepted_at is not None
    assert contatto_no_privacy.marketing_consent is False


@pytest.mark.django_db
def test_senza_spunta_privacy_non_salva(client, user_sponsor, contatto_no_privacy):
    client.force_login(user_sponsor)
    client.post(reverse('portal:privacy_consent'), {'marketing': 'on'})
    contatto_no_privacy.refresh_from_db()
    assert contatto_no_privacy.privacy_accepted_at is None

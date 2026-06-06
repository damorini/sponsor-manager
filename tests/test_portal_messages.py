"""
Archivio messaggi del portale + conferma di lettura (letto/da leggere).
"""
import pytest
from django.urls import reverse

from sponsors.models import PortalMessage, Sponsor


@pytest.mark.django_db
def test_archivio_mostra_i_messaggi(client, user_sponsor, sponsor, contact):
    PortalMessage.objects.create(sponsor=sponsor, body='Ciao messaggio test', is_active=True)
    client.force_login(user_sponsor)
    r = client.get(reverse('portal:messages'))
    assert r.status_code == 200
    assert 'Ciao messaggio test' in r.content.decode()


@pytest.mark.django_db
def test_conferma_lettura_segna_letto(client, user_sponsor, sponsor, contact):
    m = PortalMessage.objects.create(sponsor=sponsor, body='Da leggere', is_active=True)
    assert not m.is_read
    client.force_login(user_sponsor)
    r = client.post(reverse('portal:message_mark_read', args=[m.id]),
                    {'next': reverse('portal:messages')})
    assert r.status_code in (302, 200)
    m.refresh_from_db()
    assert m.is_read
    assert m.read_by_id == contact.id


@pytest.mark.django_db
def test_non_si_legge_messaggio_di_altro_sponsor(client, user_sponsor, sponsor, contact):
    altro = Sponsor.objects.create(
        legal_name='Altro Sponsor', vat_number='99999999999', address_country='IT')
    m = PortalMessage.objects.create(sponsor=altro, body='Riservato', is_active=True)
    client.force_login(user_sponsor)
    r = client.post(reverse('portal:message_mark_read', args=[m.id]))
    assert r.status_code == 404
    m.refresh_from_db()
    assert not m.is_read


@pytest.mark.django_db
def test_messaggio_disattivato_non_compare(client, user_sponsor, sponsor, contact):
    PortalMessage.objects.create(sponsor=sponsor, body='Nascosto', is_active=False)
    client.force_login(user_sponsor)
    r = client.get(reverse('portal:messages'))
    assert 'Nascosto' not in r.content.decode()

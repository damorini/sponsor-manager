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


@pytest.mark.django_db
def test_cliente_puo_rispondere(client, user_sponsor, sponsor, contact):
    from sponsors.models import MessageSender
    root = PortalMessage.objects.create(
        sponsor=sponsor, sender=MessageSender.OPERATOR, body='Domanda', is_active=True)
    client.force_login(user_sponsor)
    r = client.post(reverse('portal:message_reply', args=[root.id]),
                    {'body': 'La mia risposta'})
    assert r.status_code in (301, 302)
    rep = PortalMessage.objects.filter(parent=root, sender=MessageSender.SPONSOR).first()
    assert rep is not None and rep.body == 'La mia risposta'
    assert rep.read_at is None  # non letta dall'operatore
    root.refresh_from_db()
    assert root.is_read  # rispondendo, il cliente ha letto il messaggio operatore


@pytest.mark.django_db
def test_badge_conta_solo_messaggi_operatore(client, user_sponsor, sponsor, contact):
    from sponsors.models import MessageSender
    PortalMessage.objects.create(sponsor=sponsor, sender=MessageSender.OPERATOR,
                                 body='op', is_active=True)
    PortalMessage.objects.create(sponsor=sponsor, sender=MessageSender.SPONSOR,
                                 body='mia', is_active=True)
    client.force_login(user_sponsor)
    r = client.get(reverse('portal:messages'))
    assert r.context['non_letti'] == 1  # conta solo i messaggi dell'operatore

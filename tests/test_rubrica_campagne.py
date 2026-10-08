# tests/test_rubrica_campagne.py
"""Campagne per aree di interesse: invio, prova, disiscrizione globale."""
import re
import pytest
from django.core import mail, signing
from django.urls import reverse


@pytest.fixture
def campagna(db):
    from sponsors.models import InterestArea, InterestCampaign, Sponsor, Contact
    a = InterestArea.objects.create(name='Cardiologia')
    s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
    for nome, email in (('Mario Rossi', 'mario@alfa.it'), ('Anna Bianchi', 'anna@alfa.it')):
        Contact.objects.create(sponsor=s, full_name=nome, email=email).interest_areas.set([a])
    c = InterestCampaign.objects.create(
        name='Congresso cardio', subject={'it': 'Novità per {{ sponsor.legal_name }}'},
        body={'it': '<p>Gentile {{ contact.full_name }}, ecco il congresso.</p>'})
    c.interest_areas.set([a])
    return c


@pytest.mark.django_db
class TestInvio:
    def test_invia_a_tutti_i_destinatari_personalizzata(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk) == 2
        assert sorted(m.to[0] for m in mail.outbox) == ['anna@alfa.it', 'mario@alfa.it']
        m = next(m for m in mail.outbox if m.to == ['mario@alfa.it'])
        # send_email antepone sempre la ragione sociale all'oggetto (come per
        # le campagne per evento): "Alfa Srl – Novità per Alfa Srl"
        assert m.subject == 'Alfa Srl – Novità per Alfa Srl'
        html = m.alternatives[0][0] if m.alternatives else m.body
        assert 'Mario Rossi' in html and '/campagne/disiscrizione/' in html
        # il link deve portare l'indirizzo di QUESTO destinatario
        token = re.search(r'/campagne/disiscrizione/([^/"]+)/', html).group(1)
        assert signing.loads(token, salt='marketing-optout') == {'e': 'mario@alfa.it'}
        campagna.refresh_from_db()
        assert campagna.sent_count == 2

    def test_prova_va_solo_al_tester(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk, test_to='io@valet.it') == 1
        assert [m.to for m in mail.outbox] == [['io@valet.it']]
        assert '[PROVA]' in mail.outbox[0].subject
        campagna.refresh_from_db()
        assert campagna.sent_count == 0


    def test_prova_link_porta_indirizzo_del_tester(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        send_interest_campaign(campagna.pk, test_to='io@valet.it')
        m = mail.outbox[0]
        html = m.alternatives[0][0] if m.alternatives else m.body
        token = re.search(r'/campagne/disiscrizione/([^/"]+)/', html).group(1)
        assert signing.loads(token, salt='marketing-optout') == {'e': 'io@valet.it'}

    @pytest.mark.parametrize('vuoto', ['', '   '])
    def test_prova_con_indirizzo_vuoto_non_invia_a_nessuno(self, campagna, vuoto):
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk, test_to=vuoto) == 0
        assert len(mail.outbox) == 0
        campagna.refresh_from_db()
        assert campagna.sent_count == 0


@pytest.mark.django_db
class TestDisiscrizioneGlobale:
    def test_link_disiscrive_da_tutto_il_marketing(self, client, campagna):
        from sponsors.models import SuppressedEmail
        token = signing.dumps({'e': 'mario@alfa.it'}, salt='marketing-optout')
        resp = client.get(reverse('portal:marketing_unsubscribe', args=[token]))
        assert resp.status_code == 200
        assert SuppressedEmail.is_suppressed('mario@alfa.it')
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk) == 1

    def test_token_manomesso(self, client):
        from sponsors.models import SuppressedEmail
        resp = client.get(reverse('portal:marketing_unsubscribe', args=['falso']))
        assert resp.status_code == 200 and SuppressedEmail.objects.count() == 0


@pytest.mark.django_db
class TestAdminInvio:
    def test_invio_una_sola_volta(self, client, campagna):
        from users.models import User
        u = User.objects.create_superuser(username='s', email='s@valet.it', password='x')
        client.force_login(u)
        url = reverse('admin:sponsors_interestcampaign_changelist')
        dati = {'action': 'action_invia', '_selected_action': [campagna.pk]}
        client.post(url, dati)
        client.post(url, dati)                          # doppio clic
        assert len(mail.outbox) == 2                    # 2 destinatari, una volta sola
        campagna.refresh_from_db()
        assert campagna.sent_at is not None and campagna.sent_by == u


@pytest.mark.django_db
class TestAdminProva:
    def _admin(self, client, email):
        from users.models import User
        u = User.objects.create_superuser(username='s2', email=email, password='x')
        client.force_login(u)

    def test_prova_senza_email_utente_non_invia_nulla(self, client, campagna):
        self._admin(client, '')
        url = reverse('admin:sponsors_interestcampaign_changelist')
        resp = client.post(url, {'action': 'action_prova', '_selected_action': [campagna.pk]},
                           follow=True)
        assert len(mail.outbox) == 0
        from html import unescape
        assert "non ha un'email" in unescape(resp.content.decode())

    def test_prova_senza_destinatari_avvisa(self, client, campagna):
        self._admin(client, 'a@valet.it')
        campagna.interest_areas.clear()
        url = reverse('admin:sponsors_interestcampaign_changelist')
        resp = client.post(url, {'action': 'action_prova', '_selected_action': [campagna.pk]},
                           follow=True)
        assert len(mail.outbox) == 0
        assert 'Nessun destinatario' in resp.content.decode()

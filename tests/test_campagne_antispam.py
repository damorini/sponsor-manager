"""Le campagne non devono sembrare spam.

Due cose mancavano:

1. Nessuna PAUSA fra un invio e l'altro: il ciclo spediva tutto alla
   massima velocita'. Con qualche centinaio di destinatari il server di
   posta puo' limitare o chiudere la connessione a meta', e una raffica
   improvvisa e' uno dei segnali che i filtri guardano.
2. Nessuna intestazione List-Unsubscribe: il link c'era nel corpo, ma non
   il pulsante "Annulla iscrizione" accanto al mittente in Gmail e
   Outlook. Senza, la gente segnala come spam invece di disiscriversi.
"""
import pytest
from django.core import mail
from django.urls import reverse


@pytest.fixture
def campagna(db):
    from sponsors.models import Contact, InterestArea, InterestCampaign, Sponsor
    sp = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
    area = InterestArea.objects.create(name='Cardiologia')
    for i in (1, 2, 3):
        c = Contact.objects.create(
            sponsor=sp, first_name=f'C{i}', last_name='Rossi',
            email=f'c{i}@alfa.it', marketing_consent=True)
        c.interest_areas.add(area)
    camp = InterestCampaign.objects.create(
        name='Promo', subject={'it': 'Oggetto'}, body={'it': '<p>Ciao</p>'})
    camp.interest_areas.add(area)
    return camp


# --- 1. la pausa ---------------------------------------------------------

@pytest.mark.django_db
class TestQuantoAttende:

    def test_legge_il_valore_dal_pannello(self, settings):
        from core.models import EmailSettings
        from contracts.tasks.notifications import pausa_fra_invii
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 7
        es.save()
        assert pausa_fra_invii() == 7

    def test_zero_significa_nessuna_attesa(self, settings):
        from core.models import EmailSettings
        from contracts.tasks.notifications import pausa_fra_invii
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 0
        es.save()
        assert pausa_fra_invii() == 0

    def test_un_valore_assurdo_viene_limitato(self, settings):
        from core.models import EmailSettings
        from contracts.tasks.notifications import pausa_fra_invii
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 9999
        es.save()
        assert pausa_fra_invii() == 60

    def test_in_sviluppo_non_attende(self, settings):
        """Con i task inline la pausa bloccherebbe la richiesta dell'admin."""
        from core.models import EmailSettings
        from contracts.tasks.notifications import pausa_fra_invii
        settings.CELERY_TASK_ALWAYS_EAGER = True
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 10
        es.save()
        assert pausa_fra_invii() == 0


@pytest.mark.django_db
class TestAttendeFraUnInvioELAltro:

    def _conta_attese(self, monkeypatch, settings):
        from core.models import EmailSettings
        from contracts.tasks import notifications
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 3
        es.save()
        attese = []
        monkeypatch.setattr(notifications, '_attendi', attese.append)
        return attese

    def test_attende_fra_i_destinatari_ma_non_dopo_l_ultimo(
            self, campagna, monkeypatch, settings):
        from contracts.tasks.notifications import send_interest_campaign
        attese = self._conta_attese(monkeypatch, settings)
        inviate = send_interest_campaign(campagna.pk)
        assert inviate == 3
        # 3 email -> 2 attese: dopo l'ultima non c'e' nessuno da aspettare
        assert attese == [3, 3]

    def test_la_prova_non_attende(self, campagna, monkeypatch, settings):
        from contracts.tasks.notifications import send_interest_campaign
        attese = self._conta_attese(monkeypatch, settings)
        send_interest_campaign(campagna.pk, test_to='io@valet.it')
        assert attese == []

    def test_con_pausa_zero_non_attende(self, campagna, monkeypatch, settings):
        from core.models import EmailSettings
        from contracts.tasks import notifications
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 0
        es.save()
        attese = []
        monkeypatch.setattr(notifications, '_attendi', attese.append)
        notifications.send_interest_campaign(campagna.pk)
        assert attese == []


# --- 2. l'intestazione di disiscrizione ---------------------------------

@pytest.mark.django_db
class TestIntestazioneDisiscrizione:

    def test_ogni_email_porta_list_unsubscribe(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        mail.outbox.clear()
        send_interest_campaign(campagna.pk)
        assert len(mail.outbox) == 3
        for m in mail.outbox:
            assert 'List-Unsubscribe' in m.extra_headers, m.extra_headers

    def test_e_un_click_solo(self, campagna):
        """Gmail e Outlook mostrano il pulsante solo con questa intestazione."""
        from contracts.tasks.notifications import send_interest_campaign
        mail.outbox.clear()
        send_interest_campaign(campagna.pk)
        m = mail.outbox[0]
        assert m.extra_headers.get('List-Unsubscribe-Post') == \
            'List-Unsubscribe=One-Click'

    def test_l_indirizzo_e_fra_parentesi_angolari(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        mail.outbox.clear()
        send_interest_campaign(campagna.pk)
        valore = mail.outbox[0].extra_headers['List-Unsubscribe']
        # le parentesi angolari non sono un vezzo: senza, l'intestazione non
        # e' conforme e i gestori di posta la ignorano
        assert valore.startswith('<') and valore.endswith('>'), valore
        assert 'campagne/disiscrizione/' in valore, valore

    def test_l_indirizzo_disiscrive_davvero(self, campagna, client):
        """Il pulsante di Gmail manda un POST: deve disiscrivere per davvero,
        altrimenti l'intestazione e' una promessa non mantenuta."""
        from contracts.tasks.notifications import send_interest_campaign
        from sponsors.models import SuppressedEmail
        mail.outbox.clear()
        send_interest_campaign(campagna.pk)
        indirizzo = mail.outbox[0].extra_headers['List-Unsubscribe'].strip('<>')
        percorso = indirizzo.split('://', 1)[-1]
        percorso = percorso[percorso.index('/'):]
        assert client.post(percorso).status_code == 200
        assert SuppressedEmail.objects.filter(
            email=mail.outbox[0].to[0]).exists()

    def test_la_prova_non_porta_il_token_di_un_contatto_vero(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        mail.outbox.clear()
        send_interest_campaign(campagna.pk, test_to='io@valet.it')
        assert mail.outbox[0].to == ['io@valet.it']
        assert 'List-Unsubscribe' in mail.outbox[0].extra_headers


@pytest.mark.django_db
class TestAncheLeCampagneDiEvento:
    """L'altro invio di campagne, quello per evento, ha le stesse esigenze."""

    def test_il_batch_per_evento_mette_l_intestazione(self, db):
        from datetime import date
        from contracts.models import Contract, ContractKind, ContractStatus
        from contracts.tasks.notifications import send_promotional_campaign_batch
        from events.models import Event, PromotionalCampaign
        from sponsors.models import Contact, Sponsor

        ev = Event.objects.create(name={'it': 'Ev'}, code='ANTISPAM',
                                  start_date=date(2026, 11, 1),
                                  end_date=date(2026, 11, 2))
        sp = Sponsor.objects.create(legal_name='Beta Srl', address_country='IT')
        Contact.objects.create(sponsor=sp, last_name='Blu',
                               email='blu@beta.it', marketing_consent=True)
        Contract.objects.create(sponsor=sp, event=ev,
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SIGNED,
                                contract_number='AS-001')
        camp = PromotionalCampaign.objects.create(
            event=ev, name='x', subject={'it': 's'}, body={'it': '<p>b</p>'})

        mail.outbox.clear()
        send_promotional_campaign_batch(camp.pk)
        assert mail.outbox, "nessuna email inviata: scenario da rivedere"
        assert 'List-Unsubscribe' in mail.outbox[0].extra_headers


@pytest.mark.django_db
class TestLaCampagnaNonVieneUccisaAMeta:
    """CELERY_TASK_TIME_LIMIT globale e' mezz'ora. Con una pausa di 15
    secondi, oltre i 120 destinatari il task verrebbe ucciso a META' e una
    parte della lista non riceverebbe nulla, senza che nessuno se ne
    accorga: il valore suggerito nel pannello sarebbe una bugia."""

    def test_i_task_delle_campagne_hanno_un_tempo_proprio(self):
        from django.conf import settings
        from contracts.tasks.notifications import (
            send_interest_campaign, send_promotional_campaign_batch)
        globale = settings.CELERY_TASK_TIME_LIMIT
        for task in (send_interest_campaign, send_promotional_campaign_batch):
            assert task.time_limit and task.time_limit > globale, (
                f"{task.name} usa ancora il limite globale di {globale}s")

    def test_su_una_lista_lunga_la_pausa_si_riduce(self, settings):
        from core.models import EmailSettings
        from contracts.tasks.notifications import (
            BUDGET_CAMPAGNA, pausa_fra_invii)
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 60
        es.save()
        ridotta = pausa_fra_invii(destinatari=1000)
        assert ridotta < 60
        assert ridotta * 999 <= BUDGET_CAMPAGNA

    def test_su_una_lista_corta_resta_quella_impostata(self, settings):
        from core.models import EmailSettings
        from contracts.tasks.notifications import pausa_fra_invii
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 15
        es.save()
        assert pausa_fra_invii(destinatari=50) == 15

    def test_un_solo_destinatario_non_fa_dividere_per_zero(self, settings):
        from core.models import EmailSettings
        from contracts.tasks.notifications import pausa_fra_invii
        settings.CELERY_TASK_ALWAYS_EAGER = False
        es = EmailSettings.load()
        es.pausa_campagne_secondi = 30
        es.save()
        assert pausa_fra_invii(destinatari=1) == 30
        assert pausa_fra_invii(destinatari=0) == 30

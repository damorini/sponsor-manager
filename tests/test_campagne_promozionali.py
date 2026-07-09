"""Campagne promozionali: email ricorrente agli sponsor CONFERMATI di un
evento, con disiscrizione one-click da QUEL SOLO tipo di messaggio.

Copre: eleggibilita' (solo sponsor con contratto MAIN firmato/attivo/
completato, esclude cestinati/annullati/bozze), rispetto dell'intervallo
(is_due), esclusione dei disiscritti, il link di disiscrizione (idempotente,
non tocca altre comunicazioni), e la schedulazione giornaliera.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core import mail
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def evento_promo(db):
    from events.models import Event
    return Event.objects.create(
        name={'it': 'Promo Ev', 'en': 'Promo Ev'}, code='PROMO',
        start_date=date(2026, 11, 1), end_date=date(2026, 11, 2),
    )


def _sponsor_con_contratto(evento, status, legal_name, email='sponsor@test.it',
                           kind=None, lingua='it'):
    from sponsors.models import Sponsor, Contact
    from contracts.models import Contract, ContractKind
    sponsor = Sponsor.objects.create(legal_name=legal_name, address_country='IT')
    Contact.objects.create(
        sponsor=sponsor, full_name='Referente ' + legal_name, email=email,
        preferred_language=lingua,
    )
    from contracts.models import ContractKind as CK
    Contract.objects.create(
        sponsor=sponsor, event=evento,
        contract_kind=kind or CK.MAIN, status=status,
        contract_number=f'PROMO-{legal_name[:4].upper()}-001',
    )
    return sponsor


@pytest.fixture
def campagna(db, evento_promo):
    from events.models import PromotionalCampaign
    return PromotionalCampaign.objects.create(
        event=evento_promo, name='Servizi extra visibilità',
        subject={'it': 'Opportunità per {{ sponsor.legal_name }}', 'en': 'Opportunities'},
        body={'it': '<p>Ciao {{ contact.full_name }}, guarda le novità.</p>',
             'en': '<p>Hi {{ contact.full_name }}, check the news.</p>'},
        interval_days=14,
    )


@pytest.mark.django_db
class TestEleggibilita:
    def test_include_sponsor_firmato(self, evento_promo, campagna):
        from contracts.models import ContractStatus
        _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Firmato SRL')
        emails = list(campagna.eligible_contacts_queryset().values_list('email', flat=True))
        assert 'sponsor@test.it' in emails

    def test_esclude_bozza(self, evento_promo, campagna):
        from contracts.models import ContractStatus
        _sponsor_con_contratto(evento_promo, ContractStatus.DRAFT, 'Bozza SRL')
        assert campagna.eligible_contacts_queryset().count() == 0

    def test_esclude_annullato(self, evento_promo, campagna):
        from contracts.models import ContractStatus
        _sponsor_con_contratto(evento_promo, ContractStatus.CANCELLED, 'Annullato SRL')
        assert campagna.eligible_contacts_queryset().count() == 0

    def test_esclude_contratto_cestinato(self, evento_promo, campagna):
        from contracts.models import ContractStatus, Contract
        sponsor = _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Cestinato SRL')
        Contract.objects.get(sponsor=sponsor).delete()  # soft
        assert campagna.eligible_contacts_queryset().count() == 0

    def test_esclude_addon(self, evento_promo, campagna):
        """Solo i contratti MAIN contano come 'sponsor dell'evento': un
        acquisto ecommerce (addon) da solo non basta."""
        from contracts.models import ContractStatus, ContractKind
        _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Addon SRL',
                               kind=ContractKind.ADDON)
        assert campagna.eligible_contacts_queryset().count() == 0

    def test_esclude_altro_evento(self, db, campagna):
        from events.models import Event
        from contracts.models import ContractStatus
        altro = Event.objects.create(
            name={'it': 'Altro', 'en': 'Other'}, code='ALTRO',
            start_date=date(2026, 12, 1), end_date=date(2026, 12, 2))
        _sponsor_con_contratto(altro, ContractStatus.SIGNED, 'Altro Evento SRL')
        assert campagna.eligible_contacts_queryset().count() == 0

    def test_esclude_disiscritto(self, evento_promo, campagna):
        from contracts.models import ContractStatus
        from events.models import PromotionalCampaignOptOut
        sponsor = _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Disiscritto SRL')
        contact = sponsor.contacts.first()
        PromotionalCampaignOptOut.objects.create(campaign=campagna, contact=contact)
        assert campagna.eligible_contacts_queryset().count() == 0


@pytest.mark.django_db
class TestIsDue:
    def test_mai_inviata_e_attiva_e_dovuta(self, campagna):
        assert campagna.is_active
        assert campagna.last_sent_at is None
        assert campagna.is_due is True

    def test_inattiva_non_e_dovuta(self, campagna):
        campagna.is_active = False
        assert campagna.is_due is False

    def test_inviata_di_recente_non_e_dovuta(self, campagna):
        campagna.last_sent_at = timezone.now() - timedelta(days=3)
        campagna.interval_days = 14
        assert campagna.is_due is False

    def test_intervallo_scaduto_e_dovuta(self, campagna):
        campagna.last_sent_at = timezone.now() - timedelta(days=20)
        campagna.interval_days = 14
        assert campagna.is_due is True


@pytest.mark.django_db
def test_invio_batch_manda_email_e_aggiorna_last_sent(evento_promo, campagna):
    from contracts.models import ContractStatus
    from contracts.tasks.notifications import send_promotional_campaign_batch
    _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Uno SRL',
                           email='uno@test.it', lingua='it')
    _sponsor_con_contratto(evento_promo, ContractStatus.ACTIVE, 'Due SRL',
                           email='due@test.it', lingua='en')

    mail.outbox.clear()
    sent = send_promotional_campaign_batch(campagna.id)
    assert sent == 2
    assert len(mail.outbox) == 2

    campagna.refresh_from_db()
    assert campagna.last_sent_at is not None

    destinatari = {m.to[0] for m in mail.outbox}
    assert destinatari == {'uno@test.it', 'due@test.it'}

    # lingua rispettata + link di disiscrizione presente nell'email
    for m in mail.outbox:
        corpo = m.body + ''.join(alt for alt, _mime in m.alternatives)
        assert '/campagne/annulla/' in corpo
        if m.to == ['due@test.it']:
            assert 'check the news' in corpo
        else:
            assert 'guarda le novità' in corpo


@pytest.mark.django_db
def test_placeholder_risolto_anche_nell_oggetto(evento_promo, campagna):
    """L'oggetto usa lo stesso motore di placeholder del corpo: {{ event_name }}
    e {{ sponsor.legal_name }} non devono restare letterali nell'email."""
    from contracts.models import ContractStatus
    from contracts.tasks.notifications import send_promotional_campaign_batch
    campagna.subject = {'it': 'Novità per {{ sponsor.legal_name }} · {{ event_name }}'}
    campagna.save()
    _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Placeholder SRL',
                           email='ph@test.it')

    mail.outbox.clear()
    send_promotional_campaign_batch(campagna.id)
    assert len(mail.outbox) == 1
    subject = mail.outbox[0].subject
    assert '{{' not in subject
    assert 'Placeholder SRL' in subject
    assert 'Promo Ev' in subject


@pytest.mark.django_db
def test_invio_batch_salta_disiscritti(evento_promo, campagna):
    from contracts.models import ContractStatus
    from events.models import PromotionalCampaignOptOut
    from contracts.tasks.notifications import send_promotional_campaign_batch
    sponsor = _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Uno SRL',
                                     email='uno@test.it')
    contact = sponsor.contacts.first()
    PromotionalCampaignOptOut.objects.create(campaign=campagna, contact=contact)

    mail.outbox.clear()
    sent = send_promotional_campaign_batch(campagna.id)
    assert sent == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_check_promotional_campaigns_rispetta_intervallo(evento_promo, campagna):
    from contracts.models import ContractStatus
    from contracts.tasks.scheduled import check_promotional_campaigns
    _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Uno SRL')

    mail.outbox.clear()
    n = check_promotional_campaigns()
    assert n == 1
    assert len(mail.outbox) == 1

    # appena inviata: una seconda chiamata non deve rimandare nulla
    mail.outbox.clear()
    n2 = check_promotional_campaigns()
    assert n2 == 0
    assert mail.outbox == []


@pytest.mark.django_db
class TestUnsubscribeView:
    def _token(self, campagna, contact):
        from django.core import signing
        return signing.dumps({'c': str(campagna.id), 'k': str(contact.id)},
                             salt='promo-campaign-optout')

    def test_link_valido_disiscrive(self, client, evento_promo, campagna):
        from contracts.models import ContractStatus
        from events.models import PromotionalCampaignOptOut
        sponsor = _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Uno SRL')
        contact = sponsor.contacts.first()
        token = self._token(campagna, contact)

        resp = client.get(reverse('portal:campaign_unsubscribe', args=[token]))
        assert resp.status_code == 200
        assert 'Fatto, sei stato rimosso' in resp.content.decode() or \
               PromotionalCampaignOptOut.objects.filter(
                   campaign=campagna, contact=contact).exists()
        assert PromotionalCampaignOptOut.objects.filter(
            campaign=campagna, contact=contact).exists()

    def test_link_idempotente(self, client, evento_promo, campagna):
        from contracts.models import ContractStatus
        from events.models import PromotionalCampaignOptOut
        sponsor = _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Uno SRL')
        contact = sponsor.contacts.first()
        token = self._token(campagna, contact)

        client.get(reverse('portal:campaign_unsubscribe', args=[token]))
        client.get(reverse('portal:campaign_unsubscribe', args=[token]))
        assert PromotionalCampaignOptOut.objects.filter(
            campaign=campagna, contact=contact).count() == 1

    def test_token_manomesso_non_disiscrive(self, client):
        resp = client.get(reverse('portal:campaign_unsubscribe', args=['token-farlocco']))
        assert resp.status_code == 200
        assert 'non valido' in resp.content.decode()

    def test_disiscrizione_non_tocca_altre_email(self, client, evento_promo, campagna):
        """La disiscrizione riguarda SOLO questa campagna: il contatto resta
        raggiungibile per le comunicazioni transazionali (email diretta)."""
        from contracts.models import ContractStatus
        from contracts.services.email_sender import send_email
        sponsor = _sponsor_con_contratto(evento_promo, ContractStatus.SIGNED, 'Uno SRL',
                                         email='uno@test.it')
        contact = sponsor.contacts.first()
        token = self._token(campagna, contact)
        client.get(reverse('portal:campaign_unsubscribe', args=[token]))

        mail.outbox.clear()
        send_email(
            template_name='manual', context={}, to=['uno@test.it'],
            subject='Conferma scadenza', communication_type='manual',
            custom_body_html='<p>Testo email transazionale.</p>',
        )
        assert len(mail.outbox) == 1

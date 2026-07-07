"""
End-to-end della CONFERMA PREVENTIVO online dal portale sponsor.

Flusso (portal/views/contract.py):
  GET  portal:quote_confirm_page  -> pagina di conferma (solo se status == SENT)
  POST portal:quote_confirm       -> SENT -> SIGNED, genera scadenze e il PDF
                                     "domanda di ammissione" (document_type='admission_request')

Esercita le URL reali col test Client, la transizione di stato reale e la
generazione PDF reale (docxtpl + LibreOffice).
"""
import pytest
from pathlib import Path
from datetime import date
from django.urls import reverse
from django.conf import settings

from sponsors.models import Contact, ContactRole
from events.models import Event
from contracts.models import Contract, ContractKind, ContractStatus
from shared.models import Document


def _completa_anagrafica(sponsor):
    """Compila i campi anagrafici obbligatori: senza, la conferma del
    preventivo viene bloccata dal gate anagrafica (vedi quote_confirm_view)."""
    sponsor.sdi_code = 'ABCDEFG'
    sponsor.pec_email = 'pec@test.it'
    sponsor.address_street = 'Via Roma 1'
    sponsor.address_city = 'Bologna'
    sponsor.address_zip = '40100'
    sponsor.address_province = 'BO'
    sponsor.website = 'https://test.it'
    sponsor.business_description = 'Distributore dispositivi medici'
    sponsor.save()


@pytest.fixture
def quote_setup(db, user_sponsor, sponsor):
    """Sponsor (anagrafica completa) con un contatto operativo+firmatario
    e un contratto in stato SENT."""
    from django.utils import timezone
    from core.models import OrganizerSettings
    _completa_anagrafica(sponsor)
    Contact.objects.create(
        portal_user=user_sponsor,
        sponsor=sponsor,
        full_name='Mario Rossi',
        email='mario@test.it',
        roles=[ContactRole.OPERATIONAL],
        is_signer=True,
        privacy_accepted_at=timezone.now(),
        privacy_policy_version=OrganizerSettings.load().privacy_policy_version or '1.0',
    )
    event = Event.objects.create(
        name={'it': 'Quote Event', 'en': 'Quote Event'},
        code='QT',
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor,
        event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT,
        contract_number='QT-26-001',
    )
    return contract


@pytest.mark.django_db
class TestQuoteConfirm:
    def test_confirm_page_renders_when_sent(self, client, user_sponsor, quote_setup):
        """La pagina di conferma si apre per un preventivo in stato SENT."""
        client.force_login(user_sponsor)
        url = reverse('portal:quote_confirm_page', args=[quote_setup.id])
        resp = client.get(url)
        assert resp.status_code == 200
        # la pagina deve contenere il form che fa POST verso la conferma
        confirm_action = reverse('portal:quote_confirm', args=[quote_setup.id])
        assert confirm_action in resp.content.decode(), \
            "la pagina di conferma deve avere il form verso portal:quote_confirm"

    def test_confirm_page_blocked_when_not_sent(self, client, user_sponsor, quote_setup):
        """Se il preventivo non e' SENT, la pagina rimanda al dettaglio (302)."""
        quote_setup.status = ContractStatus.DRAFT
        quote_setup.save(update_fields=['status'])
        client.force_login(user_sponsor)
        url = reverse('portal:quote_confirm_page', args=[quote_setup.id])
        resp = client.get(url)
        assert resp.status_code == 302

    def test_confirm_transitions_to_signed_and_creates_pdf(self, client, user_sponsor, quote_setup):
        """POST di conferma: SENT -> SIGNED + Document 'admission_request'."""
        client.force_login(user_sponsor)
        url = reverse('portal:quote_confirm', args=[quote_setup.id])
        resp = client.post(url)

        assert resp.status_code == 302  # redirect a contract_detail
        quote_setup.refresh_from_db()
        assert quote_setup.status == ContractStatus.SIGNED

        doc = Document.objects.filter(document_type='admission_request').order_by('-created_at').first()
        assert doc is not None, "la domanda di ammissione deve essere stata generata"
        # LibreOffice ha davvero prodotto un PDF (non solo il fallback .docx)
        assert doc.mime_type == 'application/pdf'
        assert doc.file_size_bytes and doc.file_size_bytes > 1000

        # il file su disco esiste ed e' un PDF valido
        rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
        disk_path = Path(settings.MEDIA_ROOT) / rel
        assert disk_path.exists(), f"file PDF mancante su disco: {disk_path}"
        assert disk_path.read_bytes()[:4] == b'%PDF', "il file non e' un PDF valido"

    def test_confirm_requires_post(self, client, user_sponsor, quote_setup):
        """L'endpoint di conferma accetta solo POST (GET -> 405)."""
        client.force_login(user_sponsor)
        url = reverse('portal:quote_confirm', args=[quote_setup.id])
        resp = client.get(url)
        assert resp.status_code == 405

    def test_confirm_bloccata_con_anagrafica_incompleta(self, client, user_sponsor, quote_setup):
        """Gate anagrafica: senza dati completi la conferma rimanda a 'I miei dati'
        e il preventivo resta SENT (il contratto va compilato con dati completi)."""
        sponsor = quote_setup.sponsor
        sponsor.pec_email = ''
        sponsor.sdi_code = ''
        sponsor.save()
        client.force_login(user_sponsor)
        resp = client.post(reverse('portal:quote_confirm', args=[quote_setup.id]))
        assert resp.status_code == 302
        assert '/portal/profilo/' in resp.url
        quote_setup.refresh_from_db()
        assert quote_setup.status == ContractStatus.SENT

    def test_confirm_page_bloccata_con_anagrafica_incompleta(self, client, user_sponsor, quote_setup):
        """Anche la pagina di conferma rimanda a 'I miei dati' se mancano campi."""
        sponsor = quote_setup.sponsor
        sponsor.pec_email = ''
        sponsor.save()
        client.force_login(user_sponsor)
        resp = client.get(reverse('portal:quote_confirm_page', args=[quote_setup.id]))
        assert resp.status_code == 302
        assert '/portal/profilo/' in resp.url

    def test_confirm_bloccata_farmaceutica_senza_sis(self, client, user_sponsor, quote_setup):
        """Azienda farmaceutica senza Codice SIS: conferma bloccata dal gate."""
        sponsor = quote_setup.sponsor
        sponsor.is_pharma_company = True
        sponsor.sis_code = ''
        sponsor.save()
        client.force_login(user_sponsor)
        resp = client.post(reverse('portal:quote_confirm', args=[quote_setup.id]))
        assert resp.status_code == 302
        assert '/portal/profilo/' in resp.url
        quote_setup.refresh_from_db()
        assert quote_setup.status == ContractStatus.SENT

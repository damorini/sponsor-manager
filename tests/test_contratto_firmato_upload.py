"""Restituzione del contratto firmato (versione 'upload nel portale').

Alla conferma del preventivo (contratti MAIN) viene creata la scadenza
'contratto_firmato' (+10 giorni): il cliente carica la copia firmata nella
sezione Materiali; all'upload la scadenza va in RECEIVED e parte l'email
di avviso all'amministrazione. La scadenza entra nel giro standard di
reminder/solleciti.
"""
import pytest
from datetime import date, timedelta
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from tests.test_quote_confirm import quote_setup, _completa_anagrafica  # noqa: F401


@pytest.mark.django_db
class TestContrattoFirmato:
    def _conferma(self, client, user_sponsor, contract):
        client.force_login(user_sponsor)
        resp = client.post(reverse('portal:quote_confirm', args=[contract.id]))
        assert resp.status_code == 302
        contract.refresh_from_db()
        return contract

    def test_conferma_crea_scadenza_contratto_firmato(self, client, user_sponsor, quote_setup):
        from events.models import EventType
        quote_setup.event.event_type = EventType.NON_ECM
        quote_setup.event.save(update_fields=['event_type'])

        contract = self._conferma(client, user_sponsor, quote_setup)

        d = contract.deadlines.get(deadline_type='contratto_firmato')
        assert d.title == 'Invio contratto firmato'
        assert d.due_date == contract.signed_date + timedelta(days=10)

    def test_ecm_scadenza_si_chiama_domanda_firmata(self, client, user_sponsor, quote_setup):
        from events.models import EventType
        quote_setup.event.event_type = EventType.ECM
        quote_setup.event.save(update_fields=['event_type'])

        contract = self._conferma(client, user_sponsor, quote_setup)

        d = contract.deadlines.get(deadline_type='contratto_firmato')
        assert d.title == 'Invio domanda di ammissione firmata'

    def test_upload_firmato_riceve_e_avvisa_amministrazione(self, client, user_sponsor, quote_setup):
        from events.models import EventType
        from contracts.models import DeadlineStatus
        from shared.models import Document
        from django.contrib.contenttypes.models import ContentType
        from contracts.models import Deadline

        quote_setup.event.event_type = EventType.NON_ECM
        quote_setup.event.save(update_fields=['event_type'])
        contract = self._conferma(client, user_sponsor, quote_setup)
        d = contract.deadlines.get(deadline_type='contratto_firmato')

        mail.outbox.clear()
        pdf = SimpleUploadedFile(
            'contratto_firmato.pdf', b'%PDF-1.4 finto ma valido per il test',
            content_type='application/pdf')
        resp = client.post(reverse('portal:material_upload', args=[d.id]),
                           {'files': pdf})
        assert resp.status_code == 302

        d.refresh_from_db()
        assert d.status == DeadlineStatus.RECEIVED

        # il file e' registrato come Document della scadenza
        ct = ContentType.objects.get_for_model(Deadline)
        assert Document.objects.filter(
            content_type=ct, object_id=d.id, deleted_at__isnull=True).exists()

        # l'amministrazione riceve l'avviso
        # send_email antepone il nome sponsor all'oggetto
        avvisi = [m for m in mail.outbox
                  if 'Contratto firmato ricevuto' in m.subject]
        assert avvisi, "manca l'email di avviso all'amministrazione"
        assert 'amministrazione@valet.it' in avvisi[0].to

    def test_scadenza_non_creata_per_addon(self, db, user_sponsor, sponsor):
        """I contratti ADDON (ecommerce) non richiedono contratto firmato."""
        from datetime import date as _date
        from events.models import Event
        from contracts.models import Contract, ContractKind, ContractStatus
        _completa_anagrafica(sponsor)
        event = Event.objects.create(
            name={'it': 'Addon Ev', 'en': 'Addon Ev'}, code='AD',
            start_date=_date(2026, 12, 1), end_date=_date(2026, 12, 2),
        )
        addon = Contract.objects.create(
            sponsor=sponsor, event=event, contract_kind=ContractKind.ADDON,
            status=ContractStatus.PENDING_PAYMENT, contract_number='AD-26-001',
        )
        addon.mark_as_signed()
        assert not addon.deadlines.filter(deadline_type='contratto_firmato').exists()

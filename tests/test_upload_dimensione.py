"""Dimensione massima dei file caricati dal portale, per scadenza."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from tests.test_quote_confirm import quote_setup, _completa_anagrafica  # noqa: F401


def _pdf(mb):
    return SimpleUploadedFile('banner.pdf', b'%PDF-1.4 ' + b'0' * int(mb * 1024 * 1024),
                              content_type='application/pdf')


@pytest.mark.django_db
def test_limite_per_scadenza(client, user_sponsor, quote_setup):
    from catalog.models import DeadlineTemplate, Service
    from contracts.models import Deadline, DeadlineStatus
    from events.models import EventType
    from portal.views.materials import max_upload_mb

    quote_setup.event.event_type = EventType.NON_ECM
    quote_setup.event.save(update_fields=['event_type'])
    client.force_login(user_sponsor)
    client.post(reverse('portal:quote_confirm', args=[quote_setup.id]))
    d = quote_setup.deadlines.get(deadline_type='contratto_firmato')
    assert max_upload_mb(d) == 20

    servizio = Service.objects.create(event=quote_setup.event, code="BANNER",
                                      name={"it": "Banner"}, base_price=0)
    t = DeadlineTemplate.objects.create(service=servizio, deadline_type='tecnica',
                                        title="INVIO BANNER", days_before_event=50,
                                        max_file_size_mb=1)
    Deadline.objects.filter(pk=d.pk).update(deadline_template=t)
    d.refresh_from_db()
    assert max_upload_mb(d) == 1

    client.post(reverse('portal:material_upload', args=[d.id]), {'files': _pdf(1.5)})
    d.refresh_from_db()
    assert d.status != DeadlineStatus.RECEIVED      # troppo grande: rifiutato

    DeadlineTemplate.objects.filter(pk=t.pk).update(max_file_size_mb=100)
    client.post(reverse('portal:material_upload', args=[d.id]), {'files': _pdf(1.5)})
    d.refresh_from_db()
    assert d.status == DeadlineStatus.RECEIVED      # con 100 MB passa

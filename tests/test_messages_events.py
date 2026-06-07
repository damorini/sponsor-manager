"""
Messaggi portale legati all'evento:
- il messaggio radice richiede l'evento;
- le risposte ereditano l'evento del thread;
- archiviando l'evento, i suoi messaggi finiscono nell'archivio.
"""
import pytest
from datetime import date, timedelta
from django.core.exceptions import ValidationError

from events.models import Event, EventStatus
from sponsors.models import PortalMessage, MessageSender


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Msg', 'en': 'Ev Msg'}, code='EVM',
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=21),
        status=EventStatus.SELLING,
    )


@pytest.mark.django_db
def test_radice_senza_evento_non_valida(sponsor):
    m = PortalMessage(sponsor=sponsor, sender=MessageSender.OPERATOR, body='x')
    with pytest.raises(ValidationError):
        m.full_clean()


@pytest.mark.django_db
def test_risposta_eredita_evento(sponsor, evento):
    root = PortalMessage.objects.create(
        sponsor=sponsor, sender=MessageSender.OPERATOR, event=evento, body='radice')
    rep = PortalMessage.objects.create(
        sponsor=sponsor, sender=MessageSender.SPONSOR, parent=root, body='risposta')
    assert rep.event_id == evento.id


@pytest.mark.django_db
def test_archivio_evento_archivia_messaggi(sponsor, evento):
    root = PortalMessage.objects.create(
        sponsor=sponsor, sender=MessageSender.OPERATOR, event=evento, body='m')
    rep = PortalMessage.objects.create(
        sponsor=sponsor, sender=MessageSender.SPONSOR, parent=root, body='r')
    assert root.archived_at is None
    evento.status = EventStatus.ARCHIVED
    evento.save(update_fields=['status'])
    root.refresh_from_db(); rep.refresh_from_db()
    assert root.archived_at is not None
    assert rep.archived_at is not None

"""
Archiviazione evento: sparisce dalle aree attive del portale, compare in
'Archivio eventi', e non è più acquistabile.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from events.models import Event, EventStatus
from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractStatus


@pytest.fixture
def evento_con_contratto(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Evento Archiviabile', 'en': 'Archivable'},
        code='ARCH', start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=31),
        status=EventStatus.SELLING,
    )
    Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='ARCH-26-001',
    )
    return event


@pytest.mark.django_db
def test_evento_attivo_in_lista_non_in_archivio(client, user_sponsor, sponsor, contact, evento_con_contratto):
    client.force_login(user_sponsor)
    nome = evento_con_contratto.get_name()
    assert nome in client.get(reverse('portal:events')).content.decode()
    assert nome not in client.get(reverse('portal:events_archived')).content.decode()


@pytest.mark.django_db
def test_evento_archiviato_sparisce_e_va_in_archivio(client, user_sponsor, sponsor, contact, evento_con_contratto):
    evento_con_contratto.status = EventStatus.ARCHIVED
    evento_con_contratto.save(update_fields=['status'])
    client.force_login(user_sponsor)
    nome = evento_con_contratto.get_name()
    assert nome not in client.get(reverse('portal:events')).content.decode()
    assert nome in client.get(reverse('portal:events_archived')).content.decode()


@pytest.mark.django_db
def test_catalogo_evento_archiviato_vietato(client, user_sponsor, sponsor, contact, evento_con_contratto):
    evento_con_contratto.status = EventStatus.ARCHIVED
    evento_con_contratto.save(update_fields=['status'])
    client.force_login(user_sponsor)
    r = client.get(reverse('portal:catalog_event', args=[evento_con_contratto.id]))
    assert r.status_code == 403


@pytest.mark.django_db
def test_archiviazione_chiude_le_scadenze_aperte(evento_con_contratto):
    from contracts.models import Deadline, DeadlineStatus
    c = Contract.objects.get(event=evento_con_contratto)
    d_open = Deadline.objects.create(
        contract=c, deadline_type='materiale', title='Invia logo',
        due_date=date.today() + timedelta(days=5), status=DeadlineStatus.PENDING)
    d_done = Deadline.objects.create(
        contract=c, deadline_type='materiale', title='Già fatto',
        due_date=date.today(), status=DeadlineStatus.RECEIVED)

    evento_con_contratto.status = EventStatus.ARCHIVED
    evento_con_contratto.save(update_fields=['status'])

    d_open.refresh_from_db()
    d_done.refresh_from_db()
    assert d_open.status == DeadlineStatus.WAIVED   # aperta -> annullata
    assert d_done.status == DeadlineStatus.RECEIVED  # già chiusa: invariata


@pytest.mark.django_db
def test_servizi_acquistabili_vuoti_se_archiviato(evento_con_contratto):
    from portal.views.catalog import _get_purchasable_services
    Service.objects.create(
        event=evento_con_contratto, code='X', name={'it': 'Srv', 'en': 'Srv'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
        is_active=True, is_self_purchasable=True,
    )
    # attivo: c'è il servizio
    assert len(list(_get_purchasable_services(evento_con_contratto))) == 1
    # archiviato: nessun servizio acquistabile
    evento_con_contratto.status = EventStatus.ARCHIVED
    evento_con_contratto.save(update_fields=['status'])
    assert list(_get_purchasable_services(evento_con_contratto)) == []

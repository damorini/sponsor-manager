"""Etichetta dedicata dell'area di caricamento file (richiesta 29/08):
definita sul Template scadenza, fotografata sulla Deadline alla firma e
mostrata dentro il riquadro di upload nel portale."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import DeadlineTemplate, Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from events.models import Event


@pytest.mark.django_db
def test_etichetta_fotografata_e_visibile_nel_portale(
        client, sponsor, user_sponsor, contact):
    ev = Event.objects.create(
        name={'it': 'Ev Etichetta', 'en': 'Ev Etichetta'}, code='ETI',
        start_date=date(2027, 9, 1), end_date=date(2027, 9, 2))
    srv = Service.objects.create(
        event=ev, code='LIVE', name={'it': 'Live on stage', 'en': 'Live'},
        base_price=Decimal('1000.00'), triggers_deadlines=True)
    DeadlineTemplate.objects.create(
        service=srv, deadline_type='tecnica', title='Documenti del medico',
        submission_kind='file', days_before_event=60,
        file_area_label='📎 Dichiarazione del medico in PDF')
    ct = Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='ETI-27-001')
    ContractLine.objects.create(contract=ct, service=srv, quantity=1,
                                unit_price=Decimal('1000.00'))
    ct.mark_as_signed()

    dl = ct.deadlines.filter(deadline_type='tecnica').first()
    assert dl is not None
    assert dl.file_area_label == '📎 Dichiarazione del medico in PDF'

    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:materials_list', args=[ct.pk]))
    assert resp.status_code == 200
    assert '📎 Dichiarazione del medico in PDF' in resp.content.decode()

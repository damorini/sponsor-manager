"""Regressione: la colonna 'Fatturato' nella lista eventi (Django admin) e'
IVA ESCLUSA (subtotal), non IVA inclusa (total) - per non sommare aziende
con e senza IVA applicata su basi diverse."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event
from users.models import UserRole


@pytest.fixture
def staff_user(db):
    User = get_user_model()
    u = User.objects.create_user(
        username='fatturato_admin', email='fatturato_admin@test.it',
        password='x', is_active=True, is_staff=True, is_superuser=True,
    )
    u.role = UserRole.ADMIN
    u.save()
    return u


@pytest.mark.django_db
def test_fatturato_evento_e_iva_esclusa(client, staff_user, sponsor):
    event = Event.objects.create(
        name={'it': 'Evento Fatturato', 'en': 'Revenue Event'}, code='FATT',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )
    Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='FATT-26-001',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'), total=Decimal('1220.00'),
    )

    client.force_login(staff_user)
    resp = client.get(reverse('admin:events_event_changelist'))
    assert resp.status_code == 200

    ev_annotata = resp.context['cl'].queryset.get(pk=event.id)
    assert ev_annotata._revenue == Decimal('1000.00')

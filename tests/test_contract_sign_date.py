"""
Azione admin "Marca come firmato":
- senza data confermata mostra pagina intermedia con campo signed_date;
- con data confermata chiama mark_as_signed(signed_date=...) con la data fornita.
"""
import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse


@pytest.fixture
def staff_user(db):
    from django.contrib.auth import get_user_model
    from users.models import UserRole
    User = get_user_model()
    u = User.objects.create_user(
        username='staff_sd', email='staff_sd@test.it',
        password='x', is_active=True, is_staff=True, is_superuser=True,
    )
    u.role = UserRole.ADMIN
    u.save()
    return u


@pytest.fixture
def contratto_da_firmare(db, sponsor):
    from events.models import Event
    from contracts.models import Contract, ContractStatus, ContractKind
    ev = Event.objects.create(
        name={'it': 'SD Ev', 'en': 'SD Ev'}, code='SD1',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='SD1-26-001',
        total=Decimal('1000.00'), deposit_percent=Decimal('30'),
    )


@pytest.mark.django_db
def test_action_firma_senza_data_mostra_form(client, staff_user, contratto_da_firmare):
    """L'azione mark_as_signed senza conferma mostra la pagina intermedia."""
    client.force_login(staff_user)
    url = reverse('admin:contracts_contract_changelist')
    resp = client.post(url, {
        'action': 'action_mark_as_signed',
        '_selected_action': [str(contratto_da_firmare.id)],
    })
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'signed_date' in html or 'data firma' in html.lower()


@pytest.mark.django_db
def test_action_firma_con_data_usa_data_fornita(client, staff_user, contratto_da_firmare):
    """L'azione mark_as_signed con data confermata usa la data fornita."""
    from contracts.models import ContractStatus
    client.force_login(staff_user)
    url = reverse('admin:contracts_contract_changelist')
    firma_date = date(2026, 5, 15)
    resp = client.post(url, {
        'action': 'action_mark_as_signed',
        '_selected_action': [str(contratto_da_firmare.id)],
        '_firma_confermata': '1',
        'signed_date': firma_date.isoformat(),
    })
    assert resp.status_code in (200, 302)
    contratto_da_firmare.refresh_from_db()
    assert contratto_da_firmare.status == ContractStatus.SIGNED
    assert contratto_da_firmare.signed_date == firma_date

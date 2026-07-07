"""Eliminazione dall'admin di un contratto principale con figli nel cestino.

I contratti ADDON puntano al MAIN con FK on_delete=PROTECT: il collector
dell'admin (che lavora a livello DB) contava anche i figli GIA'
soft-cancellati e bloccava l'eliminazione elencando contratti che per
l'utente "non esistono piu'". Essendo l'eliminazione SOFT, se tutti i
figli sono nel cestino il blocco viene tolto e Django mostra la normale
pagina di conferma; con figli ancora attivi il blocco resta.
"""
import pytest
from datetime import date
from django.urls import reverse


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        username='boss', email='boss@test.it', password='AdminPass123!')


@pytest.fixture
def main_con_figlio(db, sponsor):
    from events.models import Event
    from contracts.models import Contract, ContractKind, ContractStatus
    event = Event.objects.create(
        name={'it': 'Del Ev', 'en': 'Del Ev'}, code='DEL',
        start_date=date(2026, 12, 10), end_date=date(2026, 12, 11),
    )
    main = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='DEL-26-001',
    )
    addon = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.ADDON,
        status=ContractStatus.PENDING_PAYMENT, contract_number='DEL-26-002',
        parent_contract=main,
    )
    return main, addon


@pytest.mark.django_db
def test_figli_nel_cestino_non_bloccano_la_conferma(client, admin_user, main_con_figlio):
    main, addon = main_con_figlio
    addon.delete()  # soft: finisce nel cestino ma la riga resta in DB
    client.force_login(admin_user)

    url = reverse('admin:contracts_contract_delete', args=[main.id])
    resp = client.get(url)
    assert resp.status_code == 200
    assert not resp.context['protected'], \
        "i figli nel cestino non devono piu' bloccare l'eliminazione"

    # la conferma esegue il soft delete del principale
    resp = client.post(url, {'post': 'yes'})
    assert resp.status_code == 302
    from contracts.models import Contract
    main_db = Contract.all_objects.get(pk=main.pk)
    assert main_db.deleted_at is not None


@pytest.mark.django_db
def test_figli_attivi_bloccano_ancora(client, admin_user, main_con_figlio):
    main, addon = main_con_figlio  # addon ATTIVO
    client.force_login(admin_user)

    url = reverse('admin:contracts_contract_delete', args=[main.id])
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context['protected'], \
        "con figli attivi il blocco deve restare"


@pytest.mark.django_db
def test_elenco_bloccanti_mostra_solo_i_vivi(client, admin_user, main_con_figlio, sponsor):
    """Con un figlio attivo e uno nel cestino, l'elenco dei bloccanti
    mostra SOLO quello attivo (niente 'fantasmi' gia' cancellati)."""
    from contracts.models import Contract, ContractKind, ContractStatus
    main, addon_vivo = main_con_figlio
    addon_cestinato = Contract.objects.create(
        sponsor=sponsor, event=main.event, contract_kind=ContractKind.ADDON,
        status=ContractStatus.PENDING_PAYMENT, contract_number='DEL-26-003',
        parent_contract=main,
    )
    addon_cestinato.delete()  # soft
    client.force_login(admin_user)

    resp = client.get(reverse('admin:contracts_contract_delete', args=[main.id]))
    protetti = ' '.join(str(p) for p in resp.context['protected'])
    assert 'DEL-26-002' in protetti, "il figlio attivo deve comparire"
    assert 'DEL-26-003' not in protetti, "il figlio nel cestino NON deve comparire"


@pytest.mark.django_db
def test_pagamento_su_figlio_cestinato_non_blocca(client, admin_user, main_con_figlio):
    """Un Payment (senza cestino, FK PROTECT) su un figlio gia' cestinato
    non deve bloccare il soft delete: la riga pagamento resta comunque in DB."""
    from decimal import Decimal
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice
    main, addon = main_con_figlio
    Payment.objects.create(
        contract=addon, status=PaymentStatus.SUCCEEDED,
        payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=Decimal('1.22'), currency='EUR')
    addon.delete()  # soft: nel cestino, ma il pagamento resta collegato
    client.force_login(admin_user)

    url = reverse('admin:contracts_contract_delete', args=[main.id])
    resp = client.get(url)
    assert not resp.context['protected'], \
        "pagamenti e figli nel cestino non devono bloccare"

    resp = client.post(url, {'post': 'yes'})
    assert resp.status_code == 302
    from contracts.models import Contract
    assert Contract.all_objects.get(pk=main.pk).deleted_at is not None
    # il pagamento e' ancora in DB (nessuna cancellazione reale)
    assert Payment.objects.filter(contract=addon).exists()

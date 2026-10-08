"""«Rigenera PDF» su un contratto di sponsorizzazione (MAIN, evento non-ECM)
deve rigenerare il contratto completo, non il modello generico."""
from datetime import date

import pytest


@pytest.fixture
def admin_client_rigenera(db, client):
    from django.contrib.auth import get_user_model
    utente = get_user_model().objects.create_superuser(
        username='boss_rig', email='boss.rig@test.it', password='AdminPass123!')
    client.force_login(utente)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize('tipo_evento, atteso', [('NON_ECM', 'sponsor'), ('ECM', 'generico')])
def test_rigenera_usa_il_modello_giusto(admin_client_rigenera, sponsor, monkeypatch,
                                        tipo_evento, atteso):
    from contracts.models import Contract, ContractKind
    from contracts.services import pdf_generator
    from events.models import Event

    ev = Event.objects.create(name={'it': 'Ev'}, code='RIG', event_type=tipo_evento,
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN, status='signed')
    chiamati = []
    monkeypatch.setattr(pdf_generator, 'generate_sponsor_contract_pdf',
                        lambda contratto: chiamati.append('sponsor') or object())
    monkeypatch.setattr(pdf_generator, 'generate_contract_pdf',
                        lambda contratto: chiamati.append('generico') or object())

    r = admin_client_rigenera.post('/admin/contracts/contract/', {
        'action': 'action_rigenera_pdf_contratto', '_selected_action': [str(c.pk)]})
    assert r.status_code == 302
    assert chiamati == [atteso]

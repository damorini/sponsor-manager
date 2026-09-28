"""Invio di piu' preventivi dello stesso sponsor in un colpo solo."""
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event

LISTA = '/admin/contracts/contract/'


class _Finto:
    def __init__(self, string, base_url=None):
        pass

    def write_pdf(self):
        return b'%PDF-1.4 finto'


@pytest.fixture
def regia(client, db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    u = get_user_model().objects.create_superuser(
        username='regia', email='regia@test.it', password='AdminPass123!')
    client.force_login(u)
    return client


@pytest.fixture
def due(db, sponsor, contact):
    ev = Event.objects.create(name={'it': 'Ev Due'}, code='DUE',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    return [Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                    contract_kind=ContractKind.MAIN,
                                    status=ContractStatus.DRAFT) for _ in range(2)]


def test_due_preventivi_stesso_sponsor(regia, due):
    r = regia.post(LISTA, {'action': 'action_send_quote',
                           '_selected_action': [c.pk for c in due]})
    assert r.status_code == 302 and 'invia-preventivi/?ids=' in r['Location']
    pagina = regia.get(r['Location'])
    assert '2 preventivi' in pagina.content.decode()
    ids = r['Location'].split('ids=')[1]
    with mock.patch('weasyprint.HTML', _Finto):
        r2 = regia.post(r['Location'], {'ids': ids, 'recipients': ['contact@test.it']})
    assert r2.status_code == 302
    assert len(mail.outbox) == 2
    assert {m.attachments[0][2] for m in mail.outbox} == {'application/pdf'}
    for c in due:
        c.refresh_from_db()
        assert c.status == ContractStatus.SENT


def test_sponsor_diversi_rifiutati(regia, due, db):
    from sponsors.models import Sponsor
    altro = Sponsor.objects.create(legal_name='Altro Srl', vat_number='11111111111',
                                   address_country='IT')
    due[1].sponsor = altro
    due[1].save()
    r = regia.post(LISTA, {'action': 'action_send_quote',
                           '_selected_action': [c.pk for c in due]}, follow=True)
    assert 'STESSO' in r.content.decode()
    assert not mail.outbox

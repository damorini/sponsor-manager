"""Chi e' trasferito ad altra azienda non riceve piu' comunicazioni e non
compare piu' nei documenti della VECCHIA azienda (review finale F1)."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def scenario(db):
    from sponsors.models import Contact, ContactRole, Sponsor
    from sponsors.rubrica import trasferisci_contatto
    vecchia = Sponsor.objects.create(legal_name='Vecchia Srl', address_country='IT')
    nuova = Sponsor.objects.create(legal_name='Nuova Spa', address_country='IT')
    uscito = Contact.objects.create(
        sponsor=vecchia, first_name='Mario', last_name='Rossi', email='mario@vecchia.it',
        roles=[ContactRole.OPERATIONAL, ContactRole.MARKETING], is_primary=True, is_signer=True)
    trasferisci_contatto(uscito, nuova, 'mario@nuova.it')
    uscito.refresh_from_db()
    return SimpleNamespace(vecchia=vecchia, nuova=nuova, uscito=uscito)


@pytest.fixture
def staff_client(client, db):
    from users.models import User
    u = User.objects.create_superuser(username='staff', email='staff@test.it', password='x')
    client.force_login(u)
    return client


def _contratto(sponsor, signer=None):
    return SimpleNamespace(sponsor=sponsor, sponsor_signer_contact=signer)


@pytest.mark.django_db
class TestTrasferimentoAzzeraRuoli:
    def test_vecchio_contatto_senza_ruoli_ne_firmatario(self, scenario):
        assert scenario.uscito.roles == []
        assert scenario.uscito.is_signer is False


@pytest.mark.django_db
class TestUscitoEscluso:
    def _rimetti_ruoli(self, c):
        # dati "sporchi" (es. ruoli rimessi a mano dopo il trasferimento):
        # il filtro su left_company_at deve bastare da solo
        from sponsors.models import ContactRole, Contact
        Contact.all_objects.filter(pk=c.pk).update(
            roles=[ContactRole.OPERATIONAL], is_primary=True, is_signer=True)

    def test_recipients_per_ruolo_e_fallback(self, scenario):
        from contracts.services.email_sender import get_recipients_for_contract
        self._rimetti_ruoli(scenario.uscito)
        c = _contratto(scenario.vecchia)
        assert 'mario@vecchia.it' not in get_recipients_for_contract(c, roles=['operational'])
        assert 'mario@vecchia.it' not in get_recipients_for_contract(c, roles=None)

    def test_recipients_con_altro_contatto_attivo(self, scenario):
        from contracts.services.email_sender import get_recipients_for_contract
        from sponsors.models import Contact
        Contact.objects.create(sponsor=scenario.vecchia, first_name='Anna',
                               last_name='Verdi', email='anna@vecchia.it')
        self._rimetti_ruoli(scenario.uscito)
        c = _contratto(scenario.vecchia)
        assert get_recipients_for_contract(c, roles=['operational']) == ['anna@vecchia.it']

    def test_primary_contact_e_contatti_per_ruolo(self, scenario):
        self._rimetti_ruoli(scenario.uscito)
        assert scenario.vecchia.primary_contact is None
        assert list(scenario.vecchia.get_contacts_with_role('operational')) == []

    def test_pdf_firmatario_e_referente(self, scenario):
        from contracts.services.pdf_generator import _get_referente_contact, _get_signer_contact
        self._rimetti_ruoli(scenario.uscito)
        c = _contratto(scenario.vecchia)
        assert _get_signer_contact(c) is None
        assert _get_referente_contact(c) is None

    def test_firmatario_scelto_sul_contratto_resta(self, scenario):
        """Il contratto firmato da chi poi e' uscito resta intestato a lui."""
        from contracts.services.pdf_generator import _get_signer_contact
        c = _contratto(scenario.vecchia, signer=scenario.uscito)
        assert _get_signer_contact(c) == scenario.uscito

    def test_righe_conferma_contratto(self, scenario):
        from django.contrib import admin
        from contracts.models import Contract
        self._rimetti_ruoli(scenario.uscito)
        rows = admin.site._registry[Contract]._contact_rows(_contratto(scenario.vecchia))
        assert [r['email'] for r in rows] == []

    def test_compose_email_non_elenca_uscito(self, scenario, staff_client):
        from django.urls import reverse
        from sponsors.models import Contact
        Contact.objects.create(sponsor=scenario.vecchia, first_name='Anna',
                               last_name='Verdi', email='anna@vecchia.it')
        r = staff_client.get(reverse('admin:sponsors_sponsor_compose_email',
                                     args=[scenario.vecchia.pk]))
        assert r.status_code == 200
        emails = [c.email for c in r.context['contacts']]
        assert emails == ['anna@vecchia.it']


@pytest.mark.django_db
def test_signer_email_ignora_anonimizzati(db):
    from contracts.services.email_sender import get_signer_email
    signer = SimpleNamespace(email='anonimizzato-12@invalid.invalid')
    assert get_signer_email(_contratto(None, signer)) is None
    assert get_signer_email(_contratto(None, SimpleNamespace(email='a@b.it'))) == 'a@b.it'

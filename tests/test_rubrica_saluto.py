"""Il nome nel SALUTO dei messaggi non deve essere di chi e' uscito.

F1 aveva sistemato i DESTINATARI: chi e' trasferito non riceve piu' email
per la vecchia azienda. Restava che in alcuni punti il nome da scrivere nel
saluto ("Gentile Mario...") veniva preso con `contacts.first()`, senza
escludere gli usciti: l'email arrivava alla persona giusta ma poteva
nominare chi non c'e' piu'.

I test rimettono a mano ruoli e `is_primary` sul contatto uscito (dati
"sporchi", come dopo un trasferimento corretto a posteriori): cosi' il
filtro su `left_company_at` e' verificato da solo.
"""
from datetime import date
from types import SimpleNamespace

import pytest


@pytest.fixture
def scenario(db):
    from sponsors.models import Contact, ContactRole, Sponsor
    from sponsors.rubrica import trasferisci_contatto
    vecchia = Sponsor.objects.create(legal_name='Vecchia Srl', address_country='IT')
    nuova = Sponsor.objects.create(legal_name='Nuova Spa', address_country='IT')
    uscito = Contact.objects.create(
        sponsor=vecchia, first_name='Mario', last_name='Rossi',
        email='mario@vecchia.it', preferred_language='en',
        roles=[ContactRole.OPERATIONAL], is_primary=True)
    trasferisci_contatto(uscito, nuova, 'mario@nuova.it')
    uscito.refresh_from_db()
    # dati sporchi: il filtro su left_company_at deve bastare da solo
    Contact.all_objects.filter(pk=uscito.pk).update(
        roles=[ContactRole.OPERATIONAL], is_primary=True)
    return SimpleNamespace(vecchia=vecchia, nuova=nuova, uscito=uscito)


def _resta(scenario, **kwargs):
    """Aggiunge all'azienda vecchia un contatto ancora in forze."""
    from sponsors.models import Contact
    campi = dict(sponsor=scenario.vecchia, first_name='Anna', last_name='Bianchi',
                 email='anna@vecchia.it')
    campi.update(kwargs)
    return Contact.objects.create(**campi)


@pytest.mark.django_db
class TestContattoDiRiferimento:
    """L'helper che tutti i punti del saluto devono usare."""

    def test_non_sceglie_chi_e_uscito(self, scenario):
        assert scenario.vecchia.contatto_di_riferimento is None

    def test_sceglie_chi_e_rimasto(self, scenario):
        anna = _resta(scenario)
        assert scenario.vecchia.contatto_di_riferimento == anna

    def test_preferisce_il_principale_fra_quelli_rimasti(self, scenario):
        _resta(scenario)
        carla = _resta(scenario, first_name='Carla', email='carla@vecchia.it',
                       is_primary=True)
        assert scenario.vecchia.contatto_di_riferimento == carla

    def test_nella_nuova_azienda_c_e_la_scheda_nuova(self, scenario):
        assert scenario.nuova.contatto_di_riferimento.email == 'mario@nuova.it'


@pytest.mark.django_db
class TestSalutoNelleEmail:

    def test_il_contesto_comune_non_nomina_l_uscito(self, scenario):
        from contracts.services.email_sender import build_common_context
        ctx = build_common_context({'sponsor': scenario.vecchia})
        assert ctx.get('contact') is None

    def test_il_contesto_comune_nomina_chi_e_rimasto(self, scenario):
        from contracts.services.email_sender import build_common_context
        anna = _resta(scenario)
        ctx = build_common_context({'sponsor': scenario.vecchia})
        assert ctx['contact'] == anna


@pytest.mark.django_db
class TestLinguaDelContratto:
    """La lingua del contratto si eredita dal cliente: non da chi e' uscito."""

    def _evento(self, codice):
        from events.models import Event
        return Event.objects.create(
            name={'it': 'Ev'}, code=codice,
            start_date=date(2026, 11, 1), end_date=date(2026, 11, 2))

    def test_non_eredita_la_lingua_dell_uscito(self, scenario):
        from contracts.models import Contract
        c = Contract.objects.create(
            sponsor=scenario.vecchia, event=self._evento('SAL1'),
            contract_number='SAL-001', language='it')
        assert c.language == 'it'

    def test_eredita_la_lingua_di_chi_e_rimasto(self, scenario):
        from contracts.models import Contract
        _resta(scenario, preferred_language='en')
        c = Contract.objects.create(
            sponsor=scenario.vecchia, event=self._evento('SAL2'),
            contract_number='SAL-002', language='it')
        assert c.language == 'en'


@pytest.mark.django_db
class TestRicercaDalCruscotto:
    """La ricerca cliente non mostra come referente chi e' uscito."""

    def test_non_mostra_l_uscito_come_referente(self, scenario, client):
        from django.urls import reverse
        from users.models import User
        u = User.objects.create_superuser(
            username='op', email='op@test.it', password='x')
        client.force_login(u)
        r = client.get(reverse('core:cruscotto_cerca'), {'q': 'Vecchia'})
        assert r.status_code == 200
        assert 'mario@vecchia.it' not in r.content.decode()

    def test_mostra_chi_e_rimasto(self, scenario, client):
        from django.urls import reverse
        from users.models import User
        _resta(scenario)
        u = User.objects.create_superuser(
            username='op2', email='op2@test.it', password='x')
        client.force_login(u)
        r = client.get(reverse('core:cruscotto_cerca'), {'q': 'Vecchia'})
        assert 'anna@vecchia.it' in r.content.decode()


@pytest.mark.django_db
class TestExportExcel:
    """Nell'export anagrafiche il referente non e' chi e' uscito."""

    def test_il_referente_esportato_non_e_l_uscito(self, scenario):
        from catalog.utils.excel_template import export_sponsor_workbook
        from sponsors.models import Sponsor
        _resta(scenario)
        wb = export_sponsor_workbook(Sponsor.objects.filter(pk=scenario.vecchia.pk))
        valori = [str(c.value) for row in wb.active.iter_rows() for c in row]
        assert 'mario@vecchia.it' not in valori
        assert 'anna@vecchia.it' in valori

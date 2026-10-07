"""Chi riceve una campagna per aree di interesse."""
import pytest
from datetime import date


@pytest.fixture
def aree(db):
    from sponsors.models import InterestArea
    return {n: InterestArea.objects.create(name=n) for n in ('Cardiologia', 'Oncologia')}


def _contatto(azienda, email, nome='Mario Rossi', aree=()):
    from sponsors.models import Sponsor, Contact
    sponsor, _ = Sponsor.objects.get_or_create(legal_name=azienda, defaults={'address_country': 'IT'})
    c = Contact.objects.create(sponsor=sponsor, full_name=nome, email=email)
    c.interest_areas.set(aree)
    return c


@pytest.mark.django_db
class TestDestinatari:
    def test_solo_chi_segue_le_aree_scelte(self, aree):
        from sponsors.rubrica import destinatari_per_aree
        _contatto('A Srl', 'cardio@a.it', aree=[aree['Cardiologia']])
        _contatto('A Srl', 'onco@a.it', nome='Anna Bianchi', aree=[aree['Oncologia']])
        _contatto('A Srl', 'nessuna@a.it', nome='Luca Verdi')
        emails = [c.email for c in destinatari_per_aree([aree['Cardiologia']])]
        assert emails == ['cardio@a.it']

    def test_una_email_una_volta_anche_con_piu_aree_e_aziende(self, aree):
        from sponsors.rubrica import destinatari_per_aree
        _contatto('A Srl', 'mario@x.it', aree=list(aree.values()))
        _contatto('B Srl', 'MARIO@x.it', aree=[aree['Cardiologia']])  # stessa persona, altra azienda
        assert len(destinatari_per_aree(list(aree.values()))) == 1

    def test_esclude_disiscritti(self, aree):
        from sponsors.models import SuppressedEmail
        from sponsors.rubrica import destinatari_per_aree
        _contatto('A Srl', 'via@a.it', aree=[aree['Cardiologia']])
        SuppressedEmail.add('VIA@a.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert destinatari_per_aree([aree['Cardiologia']]) == []

    def test_esclude_usciti_cestinati_e_aziende_cestinate(self, aree):
        from sponsors.rubrica import destinatari_per_aree
        uscito = _contatto('A Srl', 'uscito@a.it', aree=[aree['Cardiologia']])
        uscito.left_company_at = date(2026, 1, 1)
        uscito.save()
        _contatto('A Srl', 'cestinato@a.it', nome='Anna Bianchi', aree=[aree['Cardiologia']]).delete()
        c = _contatto('Chiusa Srl', 'chiusa@c.it', nome='Luca Verdi', aree=[aree['Cardiologia']])
        c.sponsor.delete()
        assert destinatari_per_aree([aree['Cardiologia']]) == []


@pytest.mark.django_db
class TestCampagneEventoRispettanoEsclusioni:
    def test_campagna_evento_esclude_email_disiscritta_globalmente(self):
        from contracts.models import Contract, ContractKind, ContractStatus
        from events.models import Event, PromotionalCampaign
        from sponsors.models import SuppressedEmail
        ev = Event.objects.create(name={'it': 'Ev'}, code='EVRUB',
                                  start_date=date(2026, 11, 1), end_date=date(2026, 11, 2))
        c = _contatto('Firmato Srl', 'firmato@f.it')
        Contract.objects.create(sponsor=c.sponsor, event=ev, contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SIGNED, contract_number='RUB-001')
        camp = PromotionalCampaign.objects.create(event=ev, name='x', subject={'it': 's'}, body={'it': 'b'})
        assert camp.eligible_contacts_queryset().count() == 1
        SuppressedEmail.add('firmato@f.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert camp.eligible_contacts_queryset().count() == 0

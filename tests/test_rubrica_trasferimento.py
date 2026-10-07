"""Cambio azienda e cancellazione GDPR di un contatto."""
import pytest
from datetime import date
from django.core.exceptions import ValidationError


@pytest.fixture
def due_aziende(db):
    from sponsors.models import Sponsor
    return (Sponsor.objects.create(legal_name='Vecchia Srl', address_country='IT'),
            Sponsor.objects.create(legal_name='Nuova Spa', address_country='IT'))


@pytest.fixture
def rossi(due_aziende):
    from sponsors.models import Contact, InterestArea
    c = Contact.objects.create(sponsor=due_aziende[0], first_name='Mario', last_name='Rossi',
                               email='mario@vecchia.it', phone='333', job_title='PM',
                               is_primary=True)
    c.interest_areas.set([InterestArea.objects.create(name='Cardiologia')])
    return c


@pytest.mark.django_db
class TestTrasferimento:
    def test_crea_nuovo_contatto_e_segna_il_vecchio(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        nuovo = trasferisci_contatto(rossi, due_aziende[1], 'mario@nuova.it', date(2026, 10, 1))
        rossi.refresh_from_db()
        assert nuovo.pk != rossi.pk
        assert nuovo.sponsor == due_aziende[1]
        assert (nuovo.full_name, nuovo.email, nuovo.phone) == ('Mario Rossi', 'mario@nuova.it', '333')
        assert list(nuovo.interest_areas.values_list('name', flat=True)) == ['Cardiologia']
        assert rossi.sponsor == due_aziende[0]          # MAI spostato: i contratti restano giusti
        assert rossi.left_company_at == date(2026, 10, 1)
        assert rossi.is_primary is False

    def test_senza_nuova_email_tiene_la_vecchia(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        assert trasferisci_contatto(rossi, due_aziende[1]).email == 'mario@vecchia.it'

    def test_stessa_azienda_rifiutato(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        with pytest.raises(ValidationError):
            trasferisci_contatto(rossi, due_aziende[0])

    def test_gia_uscito_rifiutato(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        trasferisci_contatto(rossi, due_aziende[1])
        with pytest.raises(ValidationError):
            trasferisci_contatto(rossi, due_aziende[1])


@pytest.mark.django_db
class TestAnonimizzazione:
    def test_anonimizza_tutte_le_schede_della_persona(self, rossi, due_aziende):
        from sponsors.models import Contact, SuppressedEmail
        from sponsors.rubrica import anonimizza_persona, trasferisci_contatto
        trasferisci_contatto(rossi, due_aziende[1])     # stessa email su due aziende
        assert anonimizza_persona('MARIO@vecchia.it') == 2
        for c in Contact.all_objects.filter(sponsor__in=due_aziende):
            assert c.full_name == 'Anonimizzato'
            assert c.email.endswith('@invalid.invalid')
            assert (c.phone, c.job_title, c.notes) == ('', '', '')
            assert c.deleted_at is not None
            assert c.interest_areas.count() == 0
        assert SuppressedEmail.objects.get().reason == SuppressedEmail.Reason.ANONYMIZED

    def test_scollega_utente_portale_senza_toccarne_email(self, rossi):
        from users.models import User
        from sponsors.rubrica import anonimizza_persona
        u = User.objects.create_user(username='mr', email='mario@vecchia.it', password='x')
        rossi.portal_user = u
        rossi.has_portal_access = True
        rossi.save()
        anonimizza_persona('mario@vecchia.it')
        rossi.refresh_from_db()
        assert rossi.portal_user is None and rossi.has_portal_access is False

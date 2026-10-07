"""Rubrica: aree di interesse, email escluse dal marketing."""
import pytest
from django.db import IntegrityError


@pytest.mark.django_db
class TestInterestArea:
    def test_nome_unico_senza_distinzione_maiuscole(self):
        from sponsors.models import InterestArea
        InterestArea.objects.create(name='Cardiologia')
        with pytest.raises(IntegrityError):
            InterestArea.objects.create(name='cardiologia')

    def test_contatto_con_piu_aree(self, contact):
        from sponsors.models import InterestArea
        a = InterestArea.objects.create(name='Cardiologia')
        b = InterestArea.objects.create(name='Oncologia')
        contact.interest_areas.set([a, b])
        assert set(contact.interest_areas.values_list('name', flat=True)) == {'Cardiologia', 'Oncologia'}


@pytest.mark.django_db
class TestSuppressedEmail:
    def test_add_normalizza_e_non_duplica(self):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('  Mario.Rossi@Esempio.IT ', SuppressedEmail.Reason.UNSUBSCRIBED)
        SuppressedEmail.add('mario.rossi@esempio.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert SuppressedEmail.objects.count() == 1
        assert SuppressedEmail.objects.get().email == 'mario.rossi@esempio.it'

    def test_is_suppressed_case_insensitive(self):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert SuppressedEmail.is_suppressed('A@B.IT')
        assert not SuppressedEmail.is_suppressed('altro@b.it')

    def test_anonimizzazione_prevale_su_disiscrizione(self):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.ANONYMIZED)
        assert SuppressedEmail.objects.get().reason == SuppressedEmail.Reason.ANONYMIZED
        # una disiscrizione successiva NON declassa l'anonimizzazione
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert SuppressedEmail.objects.get().reason == SuppressedEmail.Reason.ANONYMIZED

    def test_add_email_vuota_non_crea_nulla(self):
        from sponsors.models import SuppressedEmail
        assert SuppressedEmail.add('  ', SuppressedEmail.Reason.UNSUBSCRIBED) is None
        assert SuppressedEmail.objects.count() == 0

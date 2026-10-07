"""Pagine admin della rubrica (si aprono, mostrano i campi nuovi)."""
import pytest
from django.urls import reverse


@pytest.fixture
def staff_client(client, db):
    from users.models import User
    u = User.objects.create_superuser(username='staff', email='staff@test.it', password='x')
    client.force_login(u)
    return client


@pytest.mark.django_db
class TestAdminRubrica:
    def test_lista_aree(self, staff_client):
        from sponsors.models import InterestArea
        InterestArea.objects.create(name='Cardiologia')
        resp = staff_client.get(reverse('admin:sponsors_interestarea_changelist'))
        assert resp.status_code == 200 and b'Cardiologia' in resp.content

    def test_scheda_contatto_ha_aree_e_uscita(self, staff_client, contact):
        resp = staff_client.get(reverse('admin:sponsors_contact_change', args=[contact.pk]))
        assert resp.status_code == 200
        assert b'interest_areas' in resp.content
        assert b'Non pi' in resp.content            # "Non più in azienda dal"

    def test_filtro_lista_contatti_per_area(self, staff_client, contact):
        from sponsors.models import InterestArea
        a = InterestArea.objects.create(name='Cardiologia')
        contact.interest_areas.set([a])
        from sponsors.models import Contact, Sponsor
        altro_sp = Sponsor.objects.create(legal_name='Altra Azienda S.p.A.',
                                          vat_number='10987654321', address_country='IT')
        Contact.objects.create(sponsor=altro_sp, full_name='Altro Contatto',
                               email='altro@test.it')
        resp = staff_client.get(reverse('admin:sponsors_contact_changelist')
                                + f'?interest_areas__id__exact={a.pk}')
        assert resp.status_code == 200
        assert contact.email.encode() in resp.content
        assert b'altro@test.it' not in resp.content

    def test_filtro_uscito_si_apre(self, staff_client, contact):
        resp = staff_client.get(reverse('admin:sponsors_contact_changelist')
                                + '?left_company_at__isempty=1')
        assert resp.status_code == 200

    def test_lista_email_escluse(self, staff_client):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('via@x.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        resp = staff_client.get(reverse('admin:sponsors_suppressedemail_changelist'))
        assert resp.status_code == 200 and b'via@x.it' in resp.content

    def test_rotte_provvisorie_registrate(self, staff_client, contact):
        for name, args in (('importa_rubrica', []), ('trasferisci', [contact.pk]),
                           ('anonimizza', [contact.pk])):
            assert reverse(f'admin:sponsors_contact_{name}', args=args)

    def test_scheda_azienda_mostra_aree_dai_contatti(self, staff_client, contact):
        from sponsors.models import InterestArea
        contact.interest_areas.set([InterestArea.objects.create(name='Oncologia')])
        resp = staff_client.get(reverse('admin:sponsors_sponsor_change', args=[contact.sponsor_id]))
        assert resp.status_code == 200 and b'Oncologia' in resp.content


@pytest.mark.django_db
class TestPermessiEmailEscluse:
    def _riga(self, reason, email='del@x.it'):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add(email, reason)
        return SuppressedEmail.objects.get(email=email)

    def test_superuser_cancella_disiscrizione(self, staff_client):
        from sponsors.models import SuppressedEmail
        r = self._riga(SuppressedEmail.Reason.UNSUBSCRIBED)
        url = reverse('admin:sponsors_suppressedemail_delete', args=[r.pk])
        assert staff_client.get(url).status_code == 200
        staff_client.post(url, {'post': 'yes'})
        assert not SuppressedEmail.objects.filter(pk=r.pk).exists()

    def test_superuser_non_cancella_anonimizzazione(self, staff_client):
        from sponsors.models import SuppressedEmail
        r = self._riga(SuppressedEmail.Reason.ANONYMIZED)
        url = reverse('admin:sponsors_suppressedemail_delete', args=[r.pk])
        assert staff_client.get(url).status_code == 403
        assert SuppressedEmail.objects.filter(pk=r.pk).exists()

    def test_staff_solo_view_non_cancella(self, client, db):
        from django.contrib.auth.models import Permission
        from sponsors.models import SuppressedEmail
        from users.models import User
        u = User.objects.create_user(username='viewer', email='v@test.it',
                                     password='x', is_staff=True)
        u.user_permissions.add(Permission.objects.get(codename='view_suppressedemail'))
        client.force_login(u)
        r = self._riga(SuppressedEmail.Reason.UNSUBSCRIBED)
        url = reverse('admin:sponsors_suppressedemail_delete', args=[r.pk])
        assert client.post(url, {'post': 'yes'}).status_code == 403
        assert SuppressedEmail.objects.filter(pk=r.pk).exists()


@pytest.mark.django_db
class TestImportAdmin:
    URL = 'admin:sponsors_contact_importa_rubrica'

    def _csv(self, testo):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('r.csv', testo.encode('utf-8'))

    def test_pulsante_in_lista_contatti(self, staff_client):
        resp = staff_client.get(reverse('admin:sponsors_contact_changelist'))
        assert reverse(self.URL).encode() in resp.content

    def test_anteprima_non_scrive_nulla(self, staff_client):
        from sponsors.models import Contact
        resp = staff_client.post(reverse(self.URL), {'file': self._csv(
            'company;referente;email\nAlfa Srl;Mario Rossi;mario@alfa.it\n')})
        assert resp.status_code == 200
        assert b'mario@alfa.it' in resp.content and b'Nuova azienda' in resp.content
        assert not Contact.objects.filter(email='mario@alfa.it').exists()

    def test_conferma_scrive(self, staff_client):
        from sponsors.models import Contact
        resp = staff_client.post(reverse(self.URL), {'file': self._csv(
            'company;referente;email\nAlfa Srl;Mario Rossi;mario@alfa.it\n')})
        dati = resp.context['dati']
        resp = staff_client.post(reverse(self.URL), {'conferma': '1', 'dati': dati})
        assert resp.status_code == 302
        assert Contact.objects.filter(email='mario@alfa.it').exists()

    def test_dati_manomessi_rifiutati(self, staff_client):
        from sponsors.models import Contact
        resp = staff_client.post(reverse(self.URL), {'conferma': '1', 'dati': 'falso'})
        assert resp.status_code == 302
        assert Contact.objects.count() == 0

    def test_file_senza_colonne_mostra_errore(self, staff_client):
        resp = staff_client.post(reverse(self.URL), {'file': self._csv('a;b\n1;2\n')})
        assert resp.status_code == 200 and b'Colonne mancanti' in resp.content

    def test_import_negato_senza_permessi(self, client, db):
        from django.contrib.auth.models import Permission
        from users.models import User
        u = User.objects.create_user(username='viewer2', email='v2@test.it',
                                     password='x', is_staff=True)
        u.user_permissions.add(Permission.objects.get(
            codename='view_contact', content_type__app_label='sponsors'))
        client.force_login(u)
        assert client.get(reverse(self.URL)).status_code == 403

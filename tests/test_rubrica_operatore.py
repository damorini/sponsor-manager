"""Cose che l'operatore percepirebbe come rotte (review finale F5)."""
import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse


def _utente(username, perms=(), role='operator', **kw):
    from django.contrib.auth.models import Permission
    from users.models import User
    u = User.objects.create_user(username=username, email=f'{username}@valet.it',
                                 password='x', is_staff=True, role=role, **kw)
    for codename in perms:
        u.user_permissions.add(Permission.objects.get(
            content_type__app_label='sponsors', codename=codename))
    return u


@pytest.fixture
def superuser(db):
    from users.models import User
    return User.objects.create_superuser(username='su', email='su@valet.it', password='x')


@pytest.fixture
def campagna(db):
    from sponsors.models import Contact, InterestArea, InterestCampaign, Sponsor
    a = InterestArea.objects.create(name='Cardiologia')
    s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
    Contact.objects.create(sponsor=s, full_name='Mario Rossi',
                           email='mario@alfa.it').interest_areas.set([a])
    Contact.objects.create(sponsor=s, full_name='John Smith', email='john@alfa.it',
                           preferred_language='en').interest_areas.set([a])
    c = InterestCampaign.objects.create(name='Congresso', subject={'it': 'Novità'},
                                        body={'it': '<p>Ciao</p>'})
    c.interest_areas.set([a])
    return c


# ---------------------------------------------------------------- (a) import
@pytest.mark.django_db
def test_import_solo_intestazione_mostra_messaggio(client, superuser):
    client.force_login(superuser)
    f = SimpleUploadedFile('r.csv', b'company;referente;email;ruolo;tel;interessi\n')
    r = client.post(reverse('admin:sponsors_contact_importa_rubrica'), {'file': f})
    assert r.status_code == 200
    assert 'Nessuna riga trovata nel file.' in r.content.decode()


# ---------------------------------------------------------- (b) pulsanti 403
@pytest.mark.django_db
class TestPulsantiSoloAChiPuo:
    def test_link_importa_solo_con_add_e_change(self, client, superuser):
        url = reverse('admin:sponsors_contact_changelist')
        importa = reverse('admin:sponsors_contact_importa_rubrica')
        client.force_login(_utente('vede', ['view_contact', 'change_contact']))
        assert importa not in client.get(url).content.decode()
        client.force_login(superuser)
        assert importa in client.get(url).content.decode()

    def _scheda(self, client, user, contact):
        client.force_login(user)
        r = client.get(reverse('admin:sponsors_contact_change', args=[contact.pk]))
        assert r.status_code == 200
        return r.content.decode()

    def test_solo_lettura_nessun_pulsante(self, client, contact):
        html = self._scheda(client, _utente('lettore', ['view_contact']), contact)
        assert 'Trasferisci in altra azienda' not in html
        assert 'Cancella dati (GDPR)' not in html

    def test_operatore_con_modifica_trasferisce_ma_non_cancella(self, client, contact):
        html = self._scheda(client, _utente('op', ['view_contact', 'change_contact']), contact)
        assert 'Trasferisci in altra azienda' in html
        assert 'Cancella dati (GDPR)' not in html

    def test_ruolo_admin_vede_anche_gdpr(self, client, contact):
        html = self._scheda(client, _utente('amm', ['view_contact', 'change_contact'],
                                            role='admin'), contact)
        assert 'Cancella dati (GDPR)' in html

    def test_superuser_vede_tutto(self, client, superuser, contact):
        html = self._scheda(client, superuser, contact)
        assert 'Trasferisci in altra azienda' in html and 'Cancella dati (GDPR)' in html


# ------------------------------------------------------------- (c) menu admin
@pytest.mark.django_db
def test_menu_rubrica_nel_gruppo_sponsor(rf, superuser):
    from django.contrib import admin
    req = rf.get('/admin/')
    req.user = superuser
    gruppo = next(a for a in admin.site.get_app_list(req) if 'Sponsor' in a['name'])
    nomi = {m['object_name'] for m in gruppo['models']}
    assert {'InterestArea', 'InterestCampaign', 'SuppressedEmail'} <= nomi


# -------------------------------------------------------- (d) action_invia
@pytest.mark.django_db
class TestAzioneInvia:
    URL = 'admin:sponsors_interestcampaign_changelist'

    def _invia(self, client, superuser, campagna):
        client.force_login(superuser)
        return client.post(reverse(self.URL),
                           {'action': 'action_invia', '_selected_action': [campagna.pk]},
                           follow=True)

    def test_senza_destinatari_avvisa_e_non_segna_inviata(self, client, superuser, campagna):
        campagna.interest_areas.clear()
        r = self._invia(client, superuser, campagna)
        campagna.refresh_from_db()
        assert campagna.sent_at is None and campagna.sent_by is None
        msgs = [(m.level_tag, str(m)) for m in r.context['messages']]
        assert any(t == 'warning' and 'destinatari' in s for t, s in msgs)

    def test_coda_non_raggiungibile_ripristina(self, client, superuser, campagna, monkeypatch):
        from contracts.tasks import notifications

        def esplode(*a, **k):
            raise ConnectionError('redis giu')
        monkeypatch.setattr(notifications.send_interest_campaign, 'delay', esplode)
        r = self._invia(client, superuser, campagna)
        campagna.refresh_from_db()
        assert campagna.sent_at is None and campagna.sent_by is None
        msgs = [(m.level_tag, str(m)) for m in r.context['messages']]
        assert any(t == 'error' for t, _ in msgs)


# ------------------------------------------- (e) template oggetto/corpo rotti
@pytest.mark.django_db
class TestTemplateRotti:
    def test_oggetto_rotto_in_una_lingua_non_blocca_gli_altri(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        campagna.subject = {'it': 'Novità', 'en': 'News {% if %}'}
        campagna.body = {'it': '<p>Ciao</p>', 'en': '<p>Hi</p>'}
        campagna.save()
        assert send_interest_campaign(campagna.pk) == 1
        assert [m.to for m in mail.outbox] == [['mario@alfa.it']]

    def _form(self, **campi):
        from sponsors.admin import InterestCampaignForm
        from sponsors.models import InterestArea
        area = InterestArea.objects.create(name='Cardiologia')
        dati = {'name': 'X', 'interest_areas': [area.pk], 'subject_0': 'Novità', 'subject_1': '',
                'body_0': '<p>Ciao</p>', 'body_1': ''}
        dati.update(campi)
        return InterestCampaignForm(data=dati)

    def test_form_valido(self, db):
        f = self._form()
        assert f.is_valid(), f.errors

    @pytest.mark.parametrize('campo,valore', [
        ('subject_0', 'Novità {% if %}'),
        ('subject_1', 'News {{ contact.full_name|nonesiste }}'),
        ('body_0', '<p>{% for %}</p>'),
        ('body_1', '<p>{% endif %}</p>'),
    ])
    def test_form_rifiuta_template_che_non_compila(self, db, campo, valore):
        f = self._form(**{campo: valore})
        assert not f.is_valid()
        campo_modello = campo.split('_')[0]
        assert campo_modello in f.errors
        assert 'non è valido' in ' '.join(f.errors[campo_modello])


# ---------------------------------------------------- aree disattivate nei widget
@pytest.mark.django_db
class TestAreeDisattivate:
    def test_contatto_offre_attive_piu_gia_scelte(self, client, superuser, contact):
        from sponsors.models import InterestArea
        attiva = InterestArea.objects.create(name='Cardiologia')
        spenta_scelta = InterestArea.objects.create(name='Oncologia', is_active=False)
        spenta = InterestArea.objects.create(name='Dermatologia', is_active=False)
        contact.interest_areas.set([spenta_scelta])
        client.force_login(superuser)
        r = client.get(reverse('admin:sponsors_contact_change', args=[contact.pk]))
        qs = r.context['adminform'].form.fields['interest_areas'].queryset
        assert set(qs) == {attiva, spenta_scelta}
        assert spenta not in qs

    def test_campagna_nuova_offre_solo_attive(self, client, superuser):
        from sponsors.models import InterestArea
        attiva = InterestArea.objects.create(name='Cardiologia')
        InterestArea.objects.create(name='Dermatologia', is_active=False)
        client.force_login(superuser)
        r = client.get(reverse('admin:sponsors_interestcampaign_add'))
        assert list(r.context['adminform'].form.fields['interest_areas'].queryset) == [attiva]

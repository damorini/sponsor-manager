"""Salvare l'HTML di una newsletter non deve dare un «Bad Request» muto.

Daniele ha incollato l'HTML di una newsletter nella campagna e ha ricevuto
quattro volte una pagina bianca con scritto «Bad Request (400)», senza
nessuna spiegazione. Nei log: RequestDataTooBig, cioe' il corpo della
richiesta superava DATA_UPLOAD_MAX_MEMORY_SIZE (2,5 MB di serie). Django
sceglie di rifiutare PRIMA di leggere i dati, quindi non c'e' form, non
c'e' messaggio, non c'e' niente: solo 400.

Tre cose, qui verificate:
1. il limite e' alzato quanto basta per una newsletter vera;
2. se un 400 succede lo stesso, la pagina spiega cosa fare;
3. le immagini incorporate (data:) vengono rifiutate dal form con un
   messaggio chiaro: sono la causa quasi sempre, e comunque produrrebbero
   email che molti server rifiutano e molti programmi non mostrano.
"""
import pytest
from django.urls import reverse


@pytest.fixture
def staff_client(client, db):
    from users.models import User
    u = User.objects.create_superuser(
        username='news', email='news@valet.it', password='x')
    client.force_login(u)
    return client


@pytest.fixture
def area(db):
    from sponsors.models import InterestArea
    return InterestArea.objects.create(name='Cardiologia')


class TestIlLimiteEAlzato:

    def test_una_newsletter_vera_ci_sta(self, settings):
        """Una newsletter HTML con CSS in linea sta sotto il mezzo mega;
        il limite deve lasciare margine abbondante."""
        assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE >= 10 * 1024 * 1024


class TestLaPaginaDiErroreSpiega:

    def test_esiste_un_template_400_con_istruzioni(self):
        from django.template.loader import render_to_string
        html = render_to_string('400.html')
        assert 'immagini' in html.lower()
        # deve dire cosa fare, non solo che e' andata male
        assert 'collega' in html.lower() or 'carica' in html.lower()


@pytest.mark.django_db
class TestImmaginiIncorporate:

    def _posta(self, client, area, corpo):
        # il widget multilingua numera i sottocampi (0 = it, 1 = en),
        # non li nomina con il codice lingua
        return client.post(
            reverse('admin:sponsors_interestcampaign_add'),
            {'name': 'Newsletter', 'interest_areas': [str(area.pk)],
             'subject_0': 'Oggetto', 'subject_1': '',
             'body_0': corpo, 'body_1': ''})

    def test_il_corpo_con_data_image_viene_rifiutato(self, staff_client, area):
        from sponsors.models import InterestCampaign
        corpo = ('<p>Ciao</p><img src="data:image/png;base64,'
                 + 'A' * 300 + '">')
        resp = self._posta(staff_client, area, corpo)
        assert resp.status_code == 200, "doveva restare sul form, non salvare"
        assert not InterestCampaign.objects.exists()
        testo = resp.content.decode()
        assert 'incorporat' in testo.lower(), "deve spiegare il problema"

    def test_un_corpo_normale_si_salva(self, staff_client, area):
        from sponsors.models import InterestCampaign
        corpo = ('<p>Ciao</p><img src="https://valet.it/logo.png">'
                 '<p>' + 'testo ' * 500 + '</p>')
        resp = self._posta(staff_client, area, corpo)
        assert resp.status_code == 302, resp.content.decode()[:400]
        assert InterestCampaign.objects.count() == 1

    def test_il_messaggio_dice_cosa_fare(self, staff_client, area):
        corpo = '<img src="data:image/jpeg;base64,' + 'B' * 100 + '">'
        testo = self._posta(staff_client, area, corpo).content.decode().lower()
        # non basta dire di no: deve indicare la strada
        assert 'indirizzo' in testo or 'link' in testo or 'carica' in testo

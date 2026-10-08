"""Un solo import contatti: una regola, due modi di lanciarlo.

C'erano due import con regole diverse: quello delle Utility (scriveva
subito, collegava l'azienda anche per P.IVA, capiva ruoli funzionali,
principale, consenso, lingua e note, ma pretendeva che l'azienda
esistesse) e quello della Rubrica (anteprima prima di scrivere, crea
l'azienda mancante, controlla doppioni e aziende simili, ma ignorava
meta' delle colonne del template).

Ora la regola e' una sola, in sponsors/rubrica_import.py: la usano sia la
pagina con l'anteprima sia il comando `importa_contatti`. Questi test
verificano che l'unificazione non abbia perso nulla di cio' che i due
sapevano fare.
"""
from io import BytesIO, StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command


def _analizza(intestazione, righe):
    from sponsors.rubrica_import import analizza, leggi_file
    testo = ';'.join(intestazione) + '\n'
    for r in righe:
        testo += ';'.join(r) + '\n'
    return analizza(leggi_file(
        SimpleUploadedFile('c.csv', testo.encode('utf-8'))))


def _applica(intestazione, righe):
    from sponsors.rubrica_import import applica, leggi_file
    testo = ';'.join(intestazione) + '\n'
    for r in righe:
        testo += ';'.join(r) + '\n'
    return applica(leggi_file(
        SimpleUploadedFile('c.csv', testo.encode('utf-8'))))


@pytest.fixture
def base(db):
    from sponsors.models import InterestArea, Sponsor
    sp = Sponsor.objects.create(legal_name='Rossi Pharma S.p.A.',
                                vat_number='01234567890',
                                address_country='IT')
    for n in ('Cardiologia', 'Oncologia'):
        InterestArea.objects.create(name=n)
    return sp


# --- cio' che sapeva fare SOLO l'import delle Utility --------------------

@pytest.mark.django_db
class TestCollegamentoPerPartitaIva:

    def test_collega_l_azienda_con_la_sola_partita_iva(self, base):
        righe = _analizza(
            ['sponsor_partita_iva', 'cognome', 'email'],
            [['01234567890', 'Bianchi', 'maria@rossi.it']])
        r = righe[0]
        assert r.esito != 'errore', r.messaggi
        assert r.sponsor_id == base.pk
        assert r.nuova_azienda is False

    def test_la_partita_iva_vince_sul_nome_scritto_male(self, base):
        """Con la P.IVA giusta non deve inventare un'azienda nuova."""
        righe = _analizza(
            ['sponsor_partita_iva', 'company', 'cognome', 'email'],
            [['01234567890', 'Rossi Farma SPA', 'Bianchi', 'maria@rossi.it']])
        r = righe[0]
        assert r.esito != 'errore', r.messaggi
        assert r.sponsor_id == base.pk
        assert r.nuova_azienda is False

    def test_partita_iva_sconosciuta_e_senza_nome_e_un_errore(self, base):
        righe = _analizza(
            ['sponsor_partita_iva', 'cognome', 'email'],
            [['99999999999', 'Bianchi', 'maria@x.it']])
        assert righe[0].esito == 'errore'
        assert any('iva' in m.lower() or 'azienda' in m.lower()
                   for m in righe[0].messaggi), righe[0].messaggi


@pytest.mark.django_db
class TestColonneDelTemplateUtility:

    def test_ruoli_funzionali(self, base):
        from sponsors.models import Contact
        _applica(['company', 'cognome', 'email', 'ruoli_funzionali'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it',
                   'marketing, firmatario']])
        c = Contact.objects.get(email='maria@rossi.it')
        assert sorted(c.roles) == ['marketing', 'signer']

    def test_ruolo_funzionale_sconosciuto_e_segnalato_senza_scartare(self, base):
        righe = _analizza(
            ['company', 'cognome', 'email', 'ruoli_funzionali'],
            [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it',
              'marketing, pinco']])
        r = righe[0]
        assert r.esito != 'errore', r.messaggi
        assert any('pinco' in m for m in r.messaggi), r.messaggi

    def test_principale_declassa_gli_altri(self, base):
        from sponsors.models import Contact
        vecchio = Contact.objects.create(
            sponsor=base, last_name='Vecchio', email='vecchio@rossi.it',
            is_primary=True)
        _applica(['company', 'cognome', 'email', 'principale'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it', 's']])
        vecchio.refresh_from_db()
        assert Contact.objects.get(email='maria@rossi.it').is_primary is True
        assert vecchio.is_primary is False

    def test_lingua(self, base):
        from sponsors.models import Contact
        _applica(['company', 'cognome', 'email', 'lingua'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it', 'en']])
        assert Contact.objects.get(
            email='maria@rossi.it').preferred_language == 'en'

    def test_note(self, base):
        from sponsors.models import Contact
        _applica(['company', 'cognome', 'email', 'note'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it',
                   'Referente fatture']])
        assert Contact.objects.get(
            email='maria@rossi.it').notes == 'Referente fatture'

    def test_nome_completo_dei_file_vecchi(self, base):
        from sponsors.models import Contact
        _applica(['company', 'nome_completo', 'email'],
                 [['Rossi Pharma S.p.A.', 'Maria Bianchi', 'maria@rossi.it']])
        c = Contact.objects.get(email='maria@rossi.it')
        assert (c.first_name, c.last_name) == ('Maria', 'Bianchi')


@pytest.mark.django_db
class TestConsensoMarketing:
    """La colonna, quando c'e', decide. Quando manca resta la regola di
    Daniele: i contatti che carica sono gia' consensati."""

    def test_senza_la_colonna_il_consenso_e_dato(self, base):
        from sponsors.models import Contact
        _applica(['company', 'cognome', 'email'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it']])
        assert Contact.objects.get(
            email='maria@rossi.it').marketing_consent is True

    def test_la_colonna_a_n_nega_il_consenso(self, base):
        from sponsors.models import Contact
        _applica(['company', 'cognome', 'email', 'consenso_marketing'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it', 'n']])
        assert Contact.objects.get(
            email='maria@rossi.it').marketing_consent is False

    def test_la_colonna_a_s_lo_concede(self, base):
        from sponsors.models import Contact
        _applica(['company', 'cognome', 'email', 'consenso_marketing'],
                 [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it', 's']])
        assert Contact.objects.get(
            email='maria@rossi.it').marketing_consent is True


# --- cio' che sapeva fare SOLO l'import della Rubrica -------------------

@pytest.mark.django_db
class TestLeTutelleDellaRubricaValgonoPerTutti:

    def test_crea_l_azienda_mancante(self, base):
        righe = _analizza(['company', 'cognome', 'email'],
                          [['Nuova Medica Srl', 'Verdi', 'luca@nuova.it']])
        assert righe[0].nuova_azienda is True
        assert righe[0].esito != 'errore', righe[0].messaggi

    def test_azienda_simile_ma_non_identica_e_un_errore(self, base):
        righe = _analizza(['company', 'cognome', 'email'],
                          [['Rossi Pharma SPA', 'Verdi', 'luca@rossi.it']])
        assert righe[0].esito == 'errore'
        assert any('simile' in m for m in righe[0].messaggi), righe[0].messaggi

    def test_doppione_nello_stesso_file(self, base):
        righe = _analizza(
            ['company', 'cognome', 'email'],
            [['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it'],
             ['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it']])
        assert righe[1].esito == 'errore'


# --- il comando da riga di comando usa la STESSA regola -----------------

def _xlsx(righe):
    from openpyxl import Workbook
    wb = Workbook()
    for r in righe:
        wb.active.append(r)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.mark.django_db
class TestComandoDaRigaDiComando:

    def test_scrive_le_stesse_cose_della_pagina(self, base, tmp_path):
        from sponsors.models import Contact
        f = tmp_path / 'c.xlsx'
        f.write_bytes(_xlsx([
            ['sponsor_ragione_sociale', 'cognome', 'nome', 'email',
             'aree_interesse', 'ruoli_funzionali'],
            ['Rossi Pharma S.p.A.', 'Bianchi', 'Maria', 'maria@rossi.it',
             'Cardiologia; Oncologia', 'marketing']]))
        call_command('importa_contatti', file=str(f), stdout=StringIO())
        c = Contact.objects.get(email='maria@rossi.it')
        assert sorted(a.name for a in c.interest_areas.all()) == [
            'Cardiologia', 'Oncologia']
        assert c.roles == ['marketing']

    def test_anteprima_non_scrive(self, base, tmp_path):
        from sponsors.models import Contact
        f = tmp_path / 'c.xlsx'
        f.write_bytes(_xlsx([
            ['company', 'cognome', 'email'],
            ['Rossi Pharma S.p.A.', 'Bianchi', 'maria@rossi.it']]))
        out = StringIO()
        call_command('importa_contatti', file=str(f), dry_run=True, stdout=out)
        assert not Contact.objects.filter(email='maria@rossi.it').exists()
        assert 'maria@rossi.it' in out.getvalue()

    def test_applica_le_tutele_della_rubrica(self, base, tmp_path):
        """Il comando non deve essere una scorciatoia che aggira i controlli."""
        from sponsors.models import Contact
        f = tmp_path / 'c.xlsx'
        f.write_bytes(_xlsx([
            ['company', 'cognome', 'email'],
            ['Rossi Pharma SPA', 'Verdi', 'luca@rossi.it']]))
        out = StringIO()
        call_command('importa_contatti', file=str(f), stdout=out)
        assert not Contact.objects.filter(email='luca@rossi.it').exists()
        assert 'simile' in out.getvalue()


@pytest.mark.django_db
class TestLaPaginaDoppiaNonCeLaPiu:
    """Nelle Utility resta il download del modello, ma l'upload porta alla
    pagina unica: due pagine che importano con regole diverse erano la
    trappola da togliere."""

    def test_le_utility_rimandano_alla_pagina_unica(self, client, db):
        from django.urls import reverse
        from users.models import User
        u = User.objects.create_superuser(
            username='u', email='u@valet.it', password='x')
        client.force_login(u)
        r = client.get(reverse('core:cruscotto_utility'))
        assert r.status_code == 200
        html = r.content.decode()
        assert reverse('admin:sponsors_contact_importa_rubrica') in html
        # il modello si scarica ancora da qui
        assert reverse('core:cruscotto_download_template_contatti') in html

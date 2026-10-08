"""Il template dei contatti che si scarica dall'utility deve avere le aree.

Esistono DUE import contatti con nomi di colonna diversi: quello storico
dell'utility (sponsor_ragione_sociale, cognome, ruolo_aziendale,
telefono...) e quello nuovo della Rubrica (company, referente, ruolo,
tel, interessi). Chi scarica il template dall'utility deve poter
assegnare le aree di interesse, e lo stesso file deve essere accettato da
entrambe le pagine: altrimenti si scarica un template e l'altra pagina lo
rifiuta.
"""
from io import BytesIO

import pytest
from django.core.management import call_command
from django.urls import reverse

INTESTAZIONE_UTILITY = [
    'sponsor_ragione_sociale', 'cognome', 'nome', 'email',
    'telefono', 'ruolo_aziendale', 'aree_interesse',
]


@pytest.fixture
def aziende_e_aree(db):
    from sponsors.models import InterestArea, Sponsor
    sp = Sponsor.objects.create(legal_name='Rossi Pharma S.p.A.',
                                address_country='IT')
    for nome in ('Cardiologia', 'Oncologia'):
        InterestArea.objects.create(name=nome)
    return sp


def _xlsx(righe):
    """Crea un file Excel in memoria e lo scrive su disco temporaneo."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in righe:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.fixture
def staff_client(client, db):
    from users.models import User
    u = User.objects.create_superuser(
        username='ut', email='ut@valet.it', password='x')
    client.force_login(u)
    return client


@pytest.mark.django_db
class TestTemplateScaricabile:

    def test_il_template_ha_la_colonna_delle_aree(self, staff_client):
        from openpyxl import load_workbook
        r = staff_client.get(
            reverse('core:cruscotto_download_template_contatti'))
        assert r.status_code == 200
        wb = load_workbook(BytesIO(r.content))
        intest = [c.value for c in next(wb['Contatti'].iter_rows(max_row=1))]
        assert 'aree_interesse' in intest

    def test_la_riga_di_esempio_mostra_come_si_scrive(self, staff_client):
        from openpyxl import load_workbook
        r = staff_client.get(
            reverse('core:cruscotto_download_template_contatti'))
        wb = load_workbook(BytesIO(r.content))
        ws = wb['Contatti']
        intest = [c.value for c in next(ws.iter_rows(max_row=1))]
        col = intest.index('aree_interesse')
        esempi = [ws.cell(row=riga, column=col + 1).value
                  for riga in (2, 3)]
        # almeno un esempio con due aree separate da punto e virgola
        assert any(e and ';' in e for e in esempi), esempi


@pytest.mark.django_db
class TestImportDellUtilityAssegnaLeAree:

    def _importa(self, tmp_path, righe):
        from io import StringIO
        f = tmp_path / 'contatti.xlsx'
        f.write_bytes(_xlsx([INTESTAZIONE_UTILITY] + righe))
        out, err = StringIO(), StringIO()
        call_command('importa_contatti', file=str(f), stdout=out, stderr=err)
        return out.getvalue() + err.getvalue()

    def test_assegna_le_aree_scritte_nella_colonna(
            self, aziende_e_aree, tmp_path):
        from sponsors.models import Contact
        self._importa(tmp_path, [[
            'Rossi Pharma S.p.A.', 'Bianchi', 'Maria', 'maria@rossi.it',
            '051 1', 'Marketing', 'Cardiologia; Oncologia']])
        c = Contact.objects.get(email='maria@rossi.it')
        assert sorted(a.name for a in c.interest_areas.all()) == [
            'Cardiologia', 'Oncologia']

    def test_area_sconosciuta_e_un_errore_di_riga_e_non_importa(
            self, aziende_e_aree, tmp_path):
        from sponsors.models import Contact, InterestArea
        testo = self._importa(tmp_path, [[
            'Rossi Pharma S.p.A.', 'Bianchi', 'Maria', 'maria@rossi.it',
            '', '', 'Cardiolgia']])
        assert 'Cardiolgia' in testo
        assert not Contact.objects.filter(email='maria@rossi.it').exists()
        # e non deve inventare l'area a partire dall'errore di battitura
        assert not InterestArea.objects.filter(name='Cardiolgia').exists()

    def test_senza_la_colonna_funziona_come_prima(
            self, aziende_e_aree, tmp_path):
        """I file vecchi, senza aree, devono continuare a importare."""
        from io import StringIO
        from sponsors.models import Contact
        intest = [c for c in INTESTAZIONE_UTILITY if c != 'aree_interesse']
        f = tmp_path / 'vecchio.xlsx'
        f.write_bytes(_xlsx([intest, [
            'Rossi Pharma S.p.A.', 'Verdi', 'Luca', 'luca@rossi.it',
            '', 'Amministrazione']]))
        call_command('importa_contatti', file=str(f), stdout=StringIO())
        c = Contact.objects.get(email='luca@rossi.it')
        assert c.interest_areas.count() == 0


@pytest.mark.django_db
class TestUnSoloFilePerEntrambeLePagine:
    """Il file scaricato dall'utility deve passare anche da Importa rubrica."""

    def test_l_import_rubrica_accetta_l_intestazione_dell_utility(
            self, aziende_e_aree):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import analizza, leggi_file
        dati = _xlsx([INTESTAZIONE_UTILITY, [
            'Rossi Pharma S.p.A.', 'Bianchi', 'Maria', 'maria@rossi.it',
            '051 1', 'Marketing', 'Cardiologia']])
        righe = analizza(leggi_file(
            SimpleUploadedFile('contatti.xlsx', dati)))
        assert len(righe) == 1
        r = righe[0]
        assert r.esito != 'errore', r.messaggi
        assert r.azienda == 'Rossi Pharma S.p.A.'
        assert r.email == 'maria@rossi.it'
        # l'import rubrica tiene i NOMI delle aree, non gli oggetti
        assert r.aree == ['Cardiologia']
        assert r.ruolo == 'Marketing'
        assert r.telefono == '051 1'


@pytest.mark.django_db
class TestLinkAlTemplateNellaPaginaImport:
    """Chi apre Importa rubrica deve poter scaricare il template da li',
    senza sapere che sta nelle Utility."""

    def test_la_pagina_offre_il_download_del_template(self, staff_client):
        r = staff_client.get(
            reverse('admin:sponsors_contact_importa_rubrica'))
        assert r.status_code == 200
        atteso = reverse('core:cruscotto_download_template_contatti')
        assert atteso in r.content.decode()

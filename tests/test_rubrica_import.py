"""Import rubrica: anteprima riga per riga, poi scrittura delle sole righe buone."""
import io
import pytest


def R(**kw):
    base = {'company': 'Alfa Srl', 'referente': 'Mario Rossi', 'email': 'mario@alfa.it',
            'ruolo': 'PM', 'tel': '333', 'interessi': 'Cardiologia', '_riga': 2}
    base.update(kw)
    return base


@pytest.fixture
def cardio(db):
    from sponsors.models import InterestArea
    return InterestArea.objects.create(name='Cardiologia')


@pytest.mark.django_db
class TestAnalizza:
    def test_nuovo_contatto_e_nuova_azienda(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R()])
        assert r.esito == 'nuovo' and r.nuova_azienda
        assert (r.nome, r.cognome) == ('Mario', 'Rossi')

    def test_colonne_nome_cognome_vincono_su_referente(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R(referente='Rossi Mario', nome='Mario', cognome='Rossi')])
        assert (r.nome, r.cognome) == ('Mario', 'Rossi')

    def test_contatto_esistente_si_aggiorna(self, cardio):
        from sponsors.models import Sponsor, Contact
        from sponsors.rubrica_import import analizza
        s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
        Contact.objects.create(sponsor=s, full_name='Mario Rossi', email='MARIO@alfa.it')
        [r] = analizza([R()])
        assert r.esito == 'aggiorna' and not r.nuova_azienda

    def test_azienda_simile_ma_diversa_e_errore(self, cardio):
        from sponsors.models import Sponsor
        from sponsors.rubrica_import import analizza
        Sponsor.objects.create(legal_name='Alfa S.r.l.', address_country='IT')
        [r] = analizza([R(company='ALFA srl ')])
        assert r.esito == 'errore'
        assert any('Alfa S.r.l.' in m for m in r.messaggi)

    def test_area_sconosciuta_e_errore(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R(interessi='Cardiologia; Cardiolgia')])
        assert r.esito == 'errore'
        assert any('Cardiolgia' in m for m in r.messaggi)

    def test_email_anonimizzata_mai_reinserita(self, cardio):
        from sponsors.models import SuppressedEmail
        from sponsors.rubrica_import import analizza
        SuppressedEmail.add('mario@alfa.it', SuppressedEmail.Reason.ANONYMIZED)
        assert analizza([R()])[0].esito == 'errore'

    def test_email_disiscritta_entra_con_avviso(self, cardio):
        from sponsors.models import SuppressedEmail
        from sponsors.rubrica_import import analizza
        SuppressedEmail.add('mario@alfa.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        [r] = analizza([R()])
        assert r.esito == 'nuovo'
        assert any('disiscritt' in m for m in r.messaggi)

    def test_email_mancante_o_non_valida(self, cardio):
        from sponsors.rubrica_import import analizza
        assert analizza([R(email='')])[0].esito == 'errore'
        assert analizza([R(email='non-una-email')])[0].esito == 'errore'

    def test_stessa_email_altra_persona_e_errore(self, cardio):
        from sponsors.models import Sponsor, Contact
        from sponsors.rubrica_import import analizza
        s = Sponsor.objects.create(legal_name='Beta Spa', address_country='IT')
        Contact.objects.create(sponsor=s, full_name='Anna Bianchi', email='mario@alfa.it')
        assert analizza([R()])[0].esito == 'errore'

    def test_riga_ripetuta_nel_file(self, cardio):
        from sponsors.rubrica_import import analizza
        righe = analizza([R(), R(_riga=3)])
        assert righe[0].esito == 'nuovo' and righe[1].esito == 'errore'


@pytest.mark.django_db
class TestApplica:
    def test_scrive_solo_le_righe_buone(self, cardio):
        from sponsors.models import Contact, Sponsor
        from sponsors.rubrica_import import applica
        esito = applica([R(), R(_riga=3, email='anna@alfa.it', referente='Anna Bianchi'),
                         R(_riga=4, email='', referente='Senza Email')])
        assert esito == {'creati': 2, 'aggiornati': 0, 'aziende_create': 1, 'scartati': 1}
        assert Sponsor.objects.filter(legal_name='Alfa Srl').count() == 1
        c = Contact.objects.get(email='mario@alfa.it')
        assert (c.first_name, c.last_name, c.job_title, c.phone) == ('Mario', 'Rossi', 'PM', '333')
        assert c.marketing_consent is True and c.marketing_consent_at is not None
        assert list(c.interest_areas.values_list('name', flat=True)) == ['Cardiologia']

    def test_aggiornamento_aggiunge_aree_e_non_svuota_campi(self, cardio):
        from sponsors.models import Sponsor, Contact, InterestArea
        from sponsors.rubrica_import import applica
        onco = InterestArea.objects.create(name='Oncologia')
        s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
        c = Contact.objects.create(sponsor=s, full_name='Mario Rossi', email='mario@alfa.it',
                                   phone='999', job_title='Direttore')
        c.interest_areas.set([onco])
        esito = applica([R(tel='', ruolo='')])
        assert esito['aggiornati'] == 1
        c.refresh_from_db()
        assert (c.phone, c.job_title) == ('999', 'Direttore')
        assert set(c.interest_areas.values_list('name', flat=True)) == {'Cardiologia', 'Oncologia'}


@pytest.mark.django_db
class TestLeggiFile:
    def test_csv_con_punto_e_virgola_e_bom(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        testo = '﻿Company;Referente;Email;Ruolo;Tel;Interessi\nAlfa Srl;Mario Rossi;mario@alfa.it;PM;333;Cardiologia\n'
        righe = leggi_file(SimpleUploadedFile('r.csv', testo.encode('utf-8')))
        assert righe[0]['company'] == 'Alfa Srl' and righe[0]['_riga'] == 2

    def test_xlsx(self):
        from openpyxl import Workbook
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        wb = Workbook()
        wb.active.append(['company', 'referente', 'email'])
        wb.active.append(['Alfa Srl', 'Mario Rossi', 'mario@alfa.it'])
        wb.active.append([None, None, None])          # riga vuota: ignorata
        buf = io.BytesIO()
        wb.save(buf)
        righe = leggi_file(SimpleUploadedFile('r.xlsx', buf.getvalue()))
        assert len(righe) == 1 and righe[0]['email'] == 'mario@alfa.it'

    def test_colonna_obbligatoria_mancante(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        with pytest.raises(ValueError, match='email'):
            leggi_file(SimpleUploadedFile('r.csv', b'company;referente\nAlfa;Mario\n'))


@pytest.mark.django_db
class TestRobustezza:
    def test_stessa_email_due_aziende_nello_stesso_file(self, cardio):
        from sponsors.rubrica_import import analizza
        r1, r2 = analizza([R(company='Alfa Srl', email='mario@x.it'),
                           R(company='Beta Spa', email='mario@x.it', _riga=3)])
        assert r1.esito == 'nuovo' and r2.esito == 'errore'
        assert any('Stessa email già usata per un\'altra azienda alla riga 2' in m for m in r2.messaggi)

    def test_campo_troppo_lungo_e_errore(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R(ruolo='x' * 101)])
        assert r.esito == 'errore'
        assert any('Ruolo troppo lungo (101 caratteri, massimo 100)' in m for m in r.messaggi)

    def test_due_grafie_nuova_azienda_nello_stesso_file(self, cardio):
        from sponsors.rubrica_import import analizza
        r1, r2 = analizza([R(company='Gamma Srl'),
                           R(company='Gamma S.r.l.', email='b@g.it', referente='Anna Bianchi', _riga=3)])
        assert r1.esito == 'nuovo' and r2.esito == 'errore'
        assert any('«Gamma Srl» (riga 2)' in m for m in r2.messaggi)

    def test_stessa_grafia_nuova_azienda_resta_valida(self, cardio):
        from sponsors.rubrica_import import analizza
        r1, r2 = analizza([R(company='Gamma Srl'),
                           R(company='gamma srl', email='b@g.it', referente='Anna Bianchi', _riga=3)])
        assert r1.esito == 'nuovo' and r2.esito == 'nuovo'

    def test_applica_non_si_ferma_su_errore_imprevisto(self, cardio, monkeypatch):
        from sponsors.models import Contact, Sponsor
        from sponsors.rubrica_import import applica
        orig = Contact.save

        def finto(self, *a, **k):
            if self.email == 'boom@alfa.it':
                raise RuntimeError('boom')
            return orig(self, *a, **k)
        monkeypatch.setattr(Contact, 'save', finto)
        esito = applica([R(email='boom@alfa.it'),
                         R(_riga=3, email='anna@alfa.it', referente='Anna Bianchi')])
        assert esito['creati'] == 1 and esito['scartati'] == 1
        assert esito['aziende_create'] == 1
        assert Sponsor.objects.filter(legal_name='Alfa Srl').count() == 1
        assert Contact.objects.filter(email='anna@alfa.it').exists()


@pytest.mark.django_db
class TestLeggiFileRobusto:
    def test_csv_excel_cp1252(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        testo = 'company;referente;email\nCittà Srl;Niccolò Rossi;n@c.it\n'
        righe = leggi_file(SimpleUploadedFile('r.csv', testo.encode('cp1252')))
        assert righe[0]['company'] == 'Città Srl' and righe[0]['referente'] == 'Niccolò Rossi'

    def test_xlsx_danneggiato(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        with pytest.raises(ValueError, match='danneggiato'):
            leggi_file(SimpleUploadedFile('r.xlsx', b'not a zip'))

    def test_xls_non_supportato(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        with pytest.raises(ValueError, match='xls'):
            leggi_file(SimpleUploadedFile('r.xls', b'qualcosa'))

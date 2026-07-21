"""Regressione: nel portale, quando lo sponsor marca un contatto come
'legale rappresentante che firma il contratto' (is_signer), devono comparire
E salvarsi i campi anagrafici obbligatori (nato il/a, residenza, documento,
codice fiscale) - sia per un contatto NUOVO che per uno ESISTENTE promosso a
firmatario. Prima di questa modifica il portale non esponeva affatto questi
campi: solo il backoffice poteva impostarli."""
from datetime import date

import pytest
from django.urls import reverse

from sponsors.models import Contact


DATI_FIRMATARIO_POST = {
    'birth_date': '1980-05-20',
    'birth_place': 'Milano',
    'birth_province': 'MI',
    'residence_street': 'Via Roma',
    'residence_street_number': '10',
    'residence_city': 'Milano',
    'residence_zip': '20100',
    'residence_province': 'MI',
    'id_document_type': 'CI',
    'id_document_number': 'AB1234567',
    'signer_tax_code': 'RSSMRA80E20F205X',
}


@pytest.mark.django_db
class TestFirmatarioPortale:
    def test_pagina_espone_i_campi_firmatario_per_nuovo_contatto(self, client_authenticated):
        resp = client_authenticated.get(reverse('portal:profile'))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'nuovo_is_signer' in html
        assert 'nuovo_birth_date' in html
        assert 'nuovo_signer_tax_code' in html

    def test_nuovo_contatto_firmatario_completo_viene_salvato(self, client_authenticated, sponsor):
        data = {
            'azione': 'add_contact',
            'nuovo_full_name': 'Mario Rossi',
            'nuovo_email': 'mario.rossi@test.it',
            'nuovo_is_signer': 'on',
        }
        data.update({f'nuovo_{k}': v for k, v in DATI_FIRMATARIO_POST.items()})
        resp = client_authenticated.post(reverse('portal:profile'), data, follow=True)
        assert resp.status_code == 200

        nuovo = Contact.objects.get(sponsor=sponsor, email='mario.rossi@test.it')
        assert nuovo.is_signer is True
        assert nuovo.dati_firmatario_mancanti() == []
        assert nuovo.signer_tax_code == 'RSSMRA80E20F205X'
        assert str(nuovo.birth_date) == '1980-05-20'

    def test_nuovo_contatto_firmatario_incompleto_avvisa_ma_salva(self, client_authenticated, sponsor):
        """Non blocca il salvataggio del contatto (l'utente potra' tornare a
        completarlo), ma avvisa chiaramente cosa manca."""
        resp = client_authenticated.post(reverse('portal:profile'), {
            'azione': 'add_contact',
            'nuovo_full_name': 'Anna Verdi',
            'nuovo_email': 'anna.verdi@test.it',
            'nuovo_is_signer': 'on',
            # nessun dato anagrafico compilato
        }, follow=True)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'mancano ancora' in html

        nuova = Contact.objects.get(sponsor=sponsor, email='anna.verdi@test.it')
        assert nuova.is_signer is True
        assert len(nuova.dati_firmatario_mancanti()) == len(Contact.FIRMATARIO_CAMPI_OBBLIGATORI)

    def test_contatto_esistente_promosso_a_firmatario(self, client_authenticated, sponsor):
        esistente = Contact.objects.create(
            sponsor=sponsor, full_name='Luigi Bianchi', email='luigi.bianchi@test.it',
            roles=[], is_signer=False,
        )
        data = {
            'azione': 'edit_contact',
            'contact_id': str(esistente.id),
            'mod_full_name': 'Luigi Bianchi',
            'mod_email': 'luigi.bianchi@test.it',
            'mod_roles': ['signer'],
            'mod_is_signer': 'on',
        }
        data.update({f'mod_{k}': v for k, v in DATI_FIRMATARIO_POST.items()})
        resp = client_authenticated.post(reverse('portal:profile'), data, follow=True)
        assert resp.status_code == 200

        esistente.refresh_from_db()
        assert esistente.is_signer is True
        assert esistente.dati_firmatario_mancanti() == []
        assert 'signer' in esistente.roles

    def test_modifica_espone_i_dati_gia_salvati_del_firmatario(self, client_authenticated, sponsor):
        campi = dict(DATI_FIRMATARIO_POST)
        campi['birth_date'] = date(1980, 5, 20)
        Contact.objects.create(
            sponsor=sponsor, full_name='Giulia Neri', email='giulia.neri@test.it',
            is_signer=True, **campi,
        )
        resp = client_authenticated.get(reverse('portal:profile'))
        html = resp.content.decode()
        assert 'RSSMRA80E20F205X' in html
        assert '1980-05-20' in html
        assert 'Firmatario' in html

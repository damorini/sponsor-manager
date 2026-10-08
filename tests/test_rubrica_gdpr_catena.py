"""Cancellazione GDPR: segue la persona lungo i trasferimenti (anche con
email nuova) e non lascia dati residui (review finale F2 + F3)."""
from datetime import date

import pytest
from django.urls import reverse


@pytest.fixture
def aziende(db):
    from sponsors.models import Sponsor
    return [Sponsor.objects.create(legal_name=n, address_country='IT')
            for n in ('Prima Srl', 'Seconda Spa', 'Terza Snc')]


@pytest.fixture
def rossi(aziende):
    from sponsors.models import Contact
    return Contact.objects.create(sponsor=aziende[0], first_name='Mario', last_name='Rossi',
                                  email='mario@prima.it', phone='333')


@pytest.fixture
def staff_client(client, db):
    from users.models import User
    u = User.objects.create_superuser(username='staff', email='staff@test.it', password='x')
    client.force_login(u)
    return client


@pytest.mark.django_db
class TestCatenaTrasferimenti:
    def test_trasferimento_registra_da_chi_viene(self, rossi, aziende):
        from sponsors.rubrica import trasferisci_contatto
        nuovo = trasferisci_contatto(rossi, aziende[1], 'mario@seconda.it')
        assert nuovo.transferred_from == rossi
        assert list(rossi.transferred_to.all()) == [nuovo]

    def test_schede_della_persona_in_entrambe_le_direzioni(self, rossi, aziende):
        from sponsors.rubrica import schede_della_persona, trasferisci_contatto
        b = trasferisci_contatto(rossi, aziende[1], 'mario@seconda.it')
        c = trasferisci_contatto(b, aziende[2], 'mario@terza.it')
        attese = {rossi.pk, b.pk, c.pk}
        for partenza in (rossi, b, c):
            assert {s.pk for s in schede_della_persona(partenza)} == attese

    def test_anonimizza_dalla_scheda_nuova_prende_anche_la_vecchia(self, rossi, aziende):
        from sponsors.models import Contact, SuppressedEmail
        from sponsors.rubrica import anonimizza_persona, trasferisci_contatto
        nuovo = trasferisci_contatto(rossi, aziende[1], 'mario@seconda.it')
        assert anonimizza_persona('mario@seconda.it') == 2
        for pk in (rossi.pk, nuovo.pk):
            c = Contact.all_objects.get(pk=pk)
            assert c.full_name == 'Anonimizzato'
            assert c.email.endswith('@invalid.invalid')
        soppresse = set(SuppressedEmail.objects.values_list('email', flat=True))
        assert soppresse == {'mario@prima.it', 'mario@seconda.it'}
        assert set(SuppressedEmail.objects.values_list('reason', flat=True)) == {
            SuppressedEmail.Reason.ANONYMIZED}

    def test_pagina_conferma_elenca_tutta_la_catena(self, rossi, aziende, staff_client):
        from sponsors.rubrica import trasferisci_contatto
        nuovo = trasferisci_contatto(rossi, aziende[1], 'mario@seconda.it')
        r = staff_client.get(reverse('admin:sponsors_contact_anonimizza', args=[nuovo.pk]))
        assert r.status_code == 200
        assert b'Prima Srl' in r.content and b'Seconda Spa' in r.content

    def test_conferma_admin_anonimizza_tutta_la_catena(self, rossi, aziende, staff_client):
        from sponsors.models import Contact
        from sponsors.rubrica import trasferisci_contatto
        nuovo = trasferisci_contatto(rossi, aziende[1], 'mario@seconda.it')
        r = staff_client.post(reverse('admin:sponsors_contact_anonimizza', args=[nuovo.pk]),
                              {'conferma': '1'})
        assert r.status_code == 302
        assert Contact.all_objects.get(pk=rossi.pk).full_name == 'Anonimizzato'


@pytest.mark.django_db
class TestDatiResidui:
    def test_azzera_privacy_ruoli_documento_benvenuto(self, rossi):
        from django.utils import timezone
        from sponsors.models import Contact
        from sponsors.rubrica import anonimizza_persona
        Contact.objects.filter(pk=rossi.pk).update(
            roles=['operational'], id_document_type='PA', privacy_accepted_at=timezone.now(),
            privacy_policy_version='2.0', welcome_seen_at=timezone.now())
        anonimizza_persona('mario@prima.it')
        c = Contact.all_objects.get(pk=rossi.pk)
        assert c.roles == []
        assert c.id_document_type == ''
        assert c.privacy_accepted_at is None
        assert c.privacy_policy_version == ''
        assert c.welcome_seen_at is None

    def _utente(self, email, **kw):
        from users.models import User
        return User.objects.create_user(username=email, email=email, password='Segreta123!',
                                        first_name='Mario', last_name='Rossi', **kw)

    def test_utente_portale_senza_altri_profili_disattivato_e_anonimizzato(self, rossi):
        from sponsors.rubrica import anonimizza_persona
        u = self._utente('mario@prima.it', role='sponsor')
        rossi.portal_user, rossi.has_portal_access = u, True
        rossi.save()
        anonimizza_persona('mario@prima.it')
        u.refresh_from_db()
        assert u.is_active is False
        assert (u.first_name, u.last_name) == ('', '')
        assert u.email == u.username == f'anonimizzato-{u.pk}@invalid.invalid'
        assert not u.has_usable_password()

    def test_utente_staff_solo_scollegato(self, rossi):
        from sponsors.models import Contact
        from sponsors.rubrica import anonimizza_persona
        u = self._utente('mario@prima.it', role='sponsor', is_staff=True)
        rossi.portal_user = u
        rossi.save()
        anonimizza_persona('mario@prima.it')
        u.refresh_from_db()
        assert u.is_active is True and u.email == 'mario@prima.it'
        assert u.has_usable_password()
        assert Contact.all_objects.get(pk=rossi.pk).portal_user_id is None

    def test_utente_con_altri_profili_vivi_non_toccato(self, rossi, aziende):
        from sponsors.models import Contact
        from sponsors.rubrica import anonimizza_persona
        u = self._utente('mario@prima.it', role='sponsor')
        rossi.portal_user = u
        rossi.save()
        # lo stesso login collegato anche a un'altra scheda (fuori catena)
        Contact.objects.filter(pk=Contact.objects.create(
            sponsor=aziende[1], first_name='Luca', last_name='Neri',
            email='luca@seconda.it').pk).update(portal_user=u)
        anonimizza_persona('mario@prima.it')
        u.refresh_from_db()
        assert u.is_active is True and u.email == 'mario@prima.it'


@pytest.mark.django_db
def test_scheda_senza_email_e_senza_catena_non_elenca_altri(aziende, staff_client):
    from sponsors.models import Contact
    senza = Contact.objects.create(sponsor=aziende[0], first_name='Anna', last_name='Bianchi',
                                   email='')
    Contact.objects.create(sponsor=aziende[1], first_name='Paolo', last_name='Gialli', email='')
    r = staff_client.get(reverse('admin:sponsors_contact_anonimizza', args=[senza.pk]))
    assert r.status_code == 200
    assert b'Paolo Gialli' not in r.content
    assert 'senza email'.encode() in r.content.lower()
    assert b'name="conferma"' not in r.content

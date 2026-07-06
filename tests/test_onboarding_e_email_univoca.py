"""1) Dopo l'accettazione privacy il nuovo utente finisce su 'I miei dati'
   (dove trova il messaggio di benvenuto).
2) Email contatto univoca per PERSONA: stessa azienda mai doppioni; azienda
   diversa solo se stessa persona (multi-azienda); persona diversa = blocco.
"""
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from sponsors.models import Sponsor, Contact, ContactRole


@pytest.fixture
def contatto_nuovo(db, user_sponsor, sponsor):
    """Contatto appena creato: privacy NON accettata, benvenuto NON visto."""
    return Contact.objects.create(
        portal_user=user_sponsor, sponsor=sponsor,
        full_name='Nuovo Utente', email='nuovo@test.it',
        roles=[ContactRole.OPERATIONAL],
    )


# ---------------------------------------------------------------- privacy →
@pytest.mark.django_db
def test_dopo_privacy_va_su_i_miei_dati(client, user_sponsor, contatto_nuovo):
    client.force_login(user_sponsor)
    r = client.post(reverse('portal:privacy_consent'), {'privacy': 'on'})
    assert r.status_code == 302
    assert reverse('portal:profile') in r['Location']
    # e sulla pagina trova il benvenuto
    pagina = client.get(reverse('portal:profile')).content.decode()
    assert 'Benvenuto nella tua area riservata' in pagina


@pytest.mark.django_db
def test_dopo_privacy_utente_gia_onboardato_va_in_dashboard(client, user_sponsor, contatto_nuovo):
    from django.utils import timezone
    contatto_nuovo.welcome_seen_at = timezone.now()
    contatto_nuovo.save(update_fields=['welcome_seen_at'])
    client.force_login(user_sponsor)
    r = client.post(reverse('portal:privacy_consent'), {'privacy': 'on'})
    assert r.status_code == 302
    assert reverse('portal:dashboard') in r['Location']


# ------------------------------------------------------- email univoca ----
@pytest.mark.django_db
def test_stessa_azienda_email_doppia_bloccata(sponsor):
    Contact.objects.create(sponsor=sponsor, full_name='Mario Rossi', email='dup@test.it')
    doppione = Contact(sponsor=sponsor, full_name='Luigi Verdi', email='dup@test.it')
    with pytest.raises(ValidationError) as exc:
        doppione.clean()
    assert 'email' in exc.value.message_dict


@pytest.mark.django_db
def test_altra_azienda_persona_diversa_bloccata(sponsor):
    Contact.objects.create(sponsor=sponsor, full_name='Mario Rossi', email='dup2@test.it')
    altra = Sponsor.objects.create(legal_name='Altra Srl', address_country='IT')
    intruso = Contact(sponsor=altra, full_name='Luigi Verdi', email='dup2@test.it')
    with pytest.raises(ValidationError) as exc:
        intruso.clean()
    assert 'Mario Rossi' in str(exc.value)


@pytest.mark.django_db
def test_altra_azienda_stessa_persona_consentita(sponsor):
    """Multi-azienda: stessa persona (nome uguale, case-insensitive) su piu' aziende."""
    Contact.objects.create(sponsor=sponsor, full_name='Mario Rossi', email='multi2@test.it')
    altra = Sponsor.objects.create(legal_name='Seconda Srl', address_country='IT')
    stesso = Contact(sponsor=altra, full_name='MARIO ROSSI', email='multi2@test.it')
    stesso.clean()  # non solleva


@pytest.mark.django_db
def test_portale_aggiungi_contatto_email_doppia_bloccata(client_authenticated, sponsor, contact):
    """Dal portale: aggiungere un contatto con email di un'altra persona -> errore, non creato."""
    Contact.objects.create(sponsor=sponsor, full_name='Persona Esistente', email='occupata@test.it')
    n_prima = Contact.objects.count()
    r = client_authenticated.post(reverse('portal:profile'), {
        'azione': 'add_contact',
        'nuovo_full_name': 'Persona Diversa',
        'nuovo_email': 'occupata@test.it',
    }, follow=True)
    assert Contact.objects.count() == n_prima  # NON creato
    testo = r.content.decode()
    assert 'già' in testo or 'gi&agrave;' in testo  # alert mostrato

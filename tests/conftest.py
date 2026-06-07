"""
Configurazione pytest per il progetto.
"""
import pytest
from django.contrib.auth import get_user_model
from sponsors.models import Sponsor, Contact, ContactRole
from portal.models import Wishlist
from users.models import UserRole

User = get_user_model()


@pytest.fixture(autouse=True)
def _no_auto_translate(settings):
    """I test NON devono chiamare DeepL al salvataggio dei modelli traducibili.
    L'auto-traduzione è testata a parte (mockata) in test_autotranslate.py."""
    settings.AUTO_TRANSLATE_ON_SAVE = False


@pytest.fixture
def user_sponsor(db):
    """Crea un utente sponsor per i test."""
    user = User.objects.create_user(
        username='test_sponsor',
        email='sponsor@test.it',
        password='TestPassword123!',
        is_active=True
    )
    user.role = UserRole.SPONSOR
    user.save()
    return user


@pytest.fixture
def sponsor(db, user_sponsor):
    """Crea uno sponsor collegato all'utente."""
    sponsor = Sponsor.objects.create(
        legal_name='Test Sponsor S.r.l.',
        vat_number='12345678901',
        address_country='IT'
    )
    return sponsor


@pytest.fixture
def contact(db, user_sponsor, sponsor):
    """Crea un contact collegato all'utente.

    Ha il ruolo OPERATIONAL: senza, il gate del portale
    (portal/views/dashboard.py) reindirizza a 'I miei dati'.
    """
    from django.utils import timezone
    from core.models import OrganizerSettings
    contact = Contact.objects.create(
        portal_user=user_sponsor,
        sponsor=sponsor,
        full_name='Test Contact',
        email='contact@test.it',
        phone='+39123456789',
        roles=[ContactRole.OPERATIONAL],
        # presa visione privacy gia' fatta (cliente onboardato): evita il
        # redirect al consenso nei test che esercitano le altre pagine.
        privacy_accepted_at=timezone.now(),
        privacy_policy_version=OrganizerSettings.load().privacy_policy_version or '1.0',
    )
    return contact


@pytest.fixture
def wishlist(db, user_sponsor, contact):
    """Crea una wishlist per l'utente (contact obbligatorio)."""
    wishlist = Wishlist.objects.create(user=user_sponsor)
    return wishlist


@pytest.fixture
def client_authenticated(client, user_sponsor, contact):
    """Client autenticato come sponsor con Contact."""
    client.force_login(user_sponsor)
    return client

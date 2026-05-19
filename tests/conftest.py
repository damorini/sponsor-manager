"""
Configurazione pytest per il progetto.
"""
import pytest
from django.contrib.auth import get_user_model
from sponsors.models import Sponsor, Contact
from portal.models import Wishlist
from users.models import UserRole

User = get_user_model()


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
    """Crea un contact collegato all'utente."""
    contact = Contact.objects.create(
        portal_user=user_sponsor,
        sponsor=sponsor,
        full_name='Test Contact',
        email='contact@test.it',
        phone='+39123456789'
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

"""
Test per le view HTML della wishlist.
"""
import pytest
from django.urls import reverse
from catalog.models import Service
from events.models import Event
from contracts.models import Contract
from datetime import date


@pytest.mark.django_db
class TestWishlistViews:
    """Test per le view HTML della wishlist."""
    
    def test_wishlist_page_empty(self, client_authenticated):
        """Test: pagina wishlist vuota."""
        url = reverse('portal:wishlist_page')
        response = client_authenticated.get(url)
        
        assert response.status_code == 200
        assert 'La mia Wishlist' in response.content.decode()
    
    def test_wishlist_page_with_services(self, client_authenticated, user_sponsor, sponsor, wishlist):
        """Test: pagina wishlist con servizi."""
        event = Event.objects.create(
            name={'it': 'Test Event', 'en': 'Test Event'},
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2)
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Test Service', 'en': 'Test Service'},
            base_price=100.00
        )
        # La pagina wishlist mostra solo servizi di eventi dove lo sponsor ha un
        # contratto non annullato (portal/views/wishlist.py): serve un contratto.
        Contract.objects.create(
            sponsor=sponsor,
            event=event,
            contract_number='WL-TEST-001',
        )

        wishlist.add_service(service)
        
        url = reverse('portal:wishlist_page')
        response = client_authenticated.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Test Service' in content
    
    def test_wishlist_page_requires_authentication(self, client):
        """Test: pagina wishlist richiede autenticazione."""
        url = reverse('portal:wishlist_page')
        response = client.get(url)
        
        assert response.status_code in [302, 403]

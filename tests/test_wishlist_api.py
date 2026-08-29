"""
Test per gli API endpoints della wishlist.
"""
import pytest
from django.urls import reverse
from catalog.models import Service
from events.models import Event
from portal.models import Wishlist, WishlistItem
import json


@pytest.mark.django_db
class TestWishlistAPI:
    """Test per gli endpoint API della wishlist."""
    
    def test_wishlist_view_empty(self, client_authenticated, user_sponsor):
        """Test: visualizzare wishlist vuota."""
        url = reverse('portal:wishlist_view')
        response = client_authenticated.get(url)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['count'] == 0
        assert data['services'] == []
    
    def test_wishlist_add_service(self, client_authenticated, user_sponsor):
        """Test: aggiungere un servizio alla wishlist."""
        # Crea un evento e un servizio
        event = Event.objects.create(
            name={'it': 'Test Event', 'en': 'Test Event'},
            start_date='2026-06-01',
            end_date='2026-06-02'
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Test Service', 'en': 'Test Service'},
            base_price=100.00,
            is_self_purchasable=True,  # solo i servizi acquistabili sono wishlistabili
        )

        # Aggiungi alla wishlist
        url = reverse('portal:wishlist_add')
        response = client_authenticated.post(
            url,
            data=json.dumps({'service_id': str(service.id)}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'added'
        assert data['wishlist_count'] == 1
    
    def test_wishlist_remove_service(self, client_authenticated, user_sponsor, wishlist):
        """Test: rimuovere un servizio dalla wishlist."""
        # Crea servizio e aggiungilo
        event = Event.objects.create(
            name={'it': 'Test Event', 'en': 'Test Event'},
            start_date='2026-06-01',
            end_date='2026-06-02'
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Test Service', 'en': 'Test Service'},
            base_price=100.00
        )
        wishlist.add_service(service)
        
        # Rimuovi dalla wishlist
        url = reverse('portal:wishlist_remove')
        response = client_authenticated.post(
            url,
            data=json.dumps({'service_id': str(service.id)}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'removed'
        assert data['wishlist_count'] == 0
    
    def test_wishlist_check_service(self, client_authenticated, user_sponsor, wishlist):
        """Test: controllare se un servizio è nella wishlist."""
        # Crea servizio
        event = Event.objects.create(
            name={'it': 'Test Event', 'en': 'Test Event'},
            start_date='2026-06-01',
            end_date='2026-06-02'
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Test Service', 'en': 'Test Service'},
            base_price=100.00
        )
        wishlist.add_service(service)
        
        # Controlla se è nella wishlist
        url = reverse('portal:wishlist_check')
        response = client_authenticated.get(f'{url}?service_id={service.id}')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['in_wishlist'] is True
    
    def test_wishlist_requires_authentication(self, client):
        """Test: API richiede autenticazione."""
        url = reverse('portal:wishlist_view')
        response = client.get(url)
        
        # Dovrebbe reindirizzare a login o ritornare 403
        assert response.status_code in [302, 403]

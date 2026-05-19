"""
Test per i modelli Wishlist e WishlistItem.
"""
import pytest
from portal.models import Wishlist, WishlistItem
from catalog.models import Service
from events.models import Event
from datetime import date


@pytest.mark.django_db
class TestWishlistModel:
    """Test per il modello Wishlist."""
    
    def test_create_wishlist(self, user_sponsor):
        """Test: creare una wishlist."""
        wishlist = Wishlist.objects.create(user=user_sponsor)
        
        assert wishlist.user == user_sponsor
        assert wishlist.services.count() == 0
        assert str(wishlist) == f"Wishlist di {user_sponsor.email}"
    
    def test_add_service_to_wishlist(self, user_sponsor, wishlist):
        """Test: aggiungere un servizio alla wishlist."""
        event = Event.objects.create(
            name={'it': 'Event', 'en': 'Event'},
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2)
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Service', 'en': 'Service'},
            base_price=100.00
        )
        
        wishlist.add_service(service)
        
        assert wishlist.services.count() == 1
        assert wishlist.services.first() == service
    
    def test_remove_service_from_wishlist(self, user_sponsor, wishlist):
        """Test: rimuovere un servizio dalla wishlist."""
        event = Event.objects.create(
            name={'it': 'Event', 'en': 'Event'},
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2)
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Service', 'en': 'Service'},
            base_price=100.00
        )
        
        wishlist.add_service(service)
        assert wishlist.services.count() == 1
        
        wishlist.remove_service(service)
        assert wishlist.services.count() == 0
    
    def test_has_service_in_wishlist(self, user_sponsor, wishlist):
        """Test: verificare se un servizio è nella wishlist."""
        event = Event.objects.create(
            name={'it': 'Event', 'en': 'Event'},
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2)
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Service', 'en': 'Service'},
            base_price=100.00
        )
        
        assert wishlist.has_service(service) is False
        
        wishlist.add_service(service)
        assert wishlist.has_service(service) is True
    
    def test_wishlist_item_unique_constraint(self, user_sponsor, wishlist):
        """Test: non permettere duplicati nella wishlist."""
        event = Event.objects.create(
            name={'it': 'Event', 'en': 'Event'},
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2)
        )
        service = Service.objects.create(
            event=event,
            name={'it': 'Service', 'en': 'Service'},
            base_price=100.00
        )
        
        wishlist.add_service(service)
        wishlist.add_service(service)
        
        assert wishlist.services.count() == 1

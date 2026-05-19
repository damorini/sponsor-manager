"""
Test per i filtri del catalogo.
"""
import pytest
from django.urls import reverse
from catalog.models import Service
from events.models import Event
from datetime import date
import json
import uuid


@pytest.mark.django_db
class TestCatalogFilters:
    """Test per gli API filter del catalogo."""
    
    @pytest.fixture
    def setup_services(self):
        """Crea servizi di test con prezzi diversi."""
        event = Event.objects.create(
            name={'it': 'Test Event', 'en': 'Test Event'},
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2)
        )
        
        services = []
        for i, (name, price) in enumerate([
            ('Parete perimetrale', 600.00),
            ('Tavolo', 55.00),
            ('Faretto LED', 40.00),
            ('Corrente extra', 120.00),
        ]):
            service = Service.objects.create(
                event=event,
                code=str(uuid.uuid4()),  # Codice unico per evitare constraint
                name={'it': name, 'en': name},
                base_price=price
            )
            services.append(service)
        
        return event, services
    
    def test_filter_search_by_name(self, client_authenticated, setup_services):
        """Test: filtrare servizi per nome."""
        event, services = setup_services
        
        url = reverse('portal:catalog_api_filter')
        response = client_authenticated.get(
            f'{url}?event_id={event.id}&search=parete'
        )
        
        assert response.status_code == 200
    
    def test_filter_by_min_price(self, client_authenticated, setup_services):
        """Test: filtrare servizi per prezzo minimo."""
        event, services = setup_services
        
        url = reverse('portal:catalog_api_filter')
        response = client_authenticated.get(
            f'{url}?event_id={event.id}&min_price=100'
        )
        
        assert response.status_code == 200
    
    def test_filter_by_max_price(self, client_authenticated, setup_services):
        """Test: filtrare servizi per prezzo massimo."""
        event, services = setup_services
        
        url = reverse('portal:catalog_api_filter')
        response = client_authenticated.get(
            f'{url}?event_id={event.id}&max_price=100'
        )
        
        assert response.status_code == 200
    
    def test_filter_by_price_range(self, client_authenticated, setup_services):
        """Test: filtrare servizi per range di prezzo."""
        event, services = setup_services
        
        url = reverse('portal:catalog_api_filter')
        response = client_authenticated.get(
            f'{url}?event_id={event.id}&min_price=50&max_price=150'
        )
        
        assert response.status_code == 200
    
    def test_filter_combined_search_and_price(self, client_authenticated, setup_services):
        """Test: filtrare per nome e prezzo insieme."""
        event, services = setup_services
        
        url = reverse('portal:catalog_api_filter')
        response = client_authenticated.get(
            f'{url}?event_id={event.id}&search=parete&min_price=500'
        )
        
        assert response.status_code == 200

"""
URL configuration principale.

Routing:
- /admin/         → Django admin (backoffice operatore)
- /portal/       → portale self-service sponsor
- /webhooks/     → webhook PayPal e altri servizi esterni
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView


urlpatterns = [
    path('admin/cruscotto/', include('core.urls', namespace='core')),
    path('admin/', RedirectView.as_view(pattern_name='core:cruscotto_home', permanent=False)),  # /admin/ -> cruscotto (landing dopo login)
    path('admin/', admin.site.urls),
    
    # Portale sponsor self-service
    path('portal/', include('portal.urls')),
    
    # Webhook PayPal (URL pubblica, no autenticazione utente)
    path('webhooks/', include('contracts.urls.webhooks')),
]

if settings.DEBUG:
    # Servire MEDIA in sviluppo (in produzione lo fa nginx)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT:
        urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

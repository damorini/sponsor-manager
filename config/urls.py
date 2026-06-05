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
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Healthcheck per Docker/nginx/load balancer: 200 se DB raggiungibile, 503 altrimenti."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"status": "error", "detail": str(e)}, status=503)


urlpatterns = [
    path('health/', health_check, name='health'),

    path('admin/cruscotto/', include('core.urls', namespace='core')),
    path('admin/', RedirectView.as_view(pattern_name='core:cruscotto_home', permanent=False)),  # /admin/ -> cruscotto (landing dopo login)
    path('admin/', admin.site.urls),
    
    # Portale sponsor self-service
    path('portal/', include('portal.urls')),
    path('i18n/', include('django.conf.urls.i18n')),  # cambio lingua (set_language)
    
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

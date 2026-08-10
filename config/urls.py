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
from django.urls import path, include, re_path
from django.views.generic.base import RedirectView
from django.http import JsonResponse
from django.db import connection

from shared.views import protected_document_media


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

    # Documenti clienti serviti SOLO tramite Django con controllo di
    # proprieta' (in produzione Caddy inoltra qui /media/documents/*;
    # in DEBUG questo pattern vince sul fallback static() piu' sotto).
    re_path(r'^media/documents/(?P<subpath>.+)$', protected_document_media,
            name='protected_document_media'),

    path('admin/cruscotto/', include('core.urls', namespace='core')),
    # Con questo nome registrato, la login dell'admin mostra da sola il link
    # "Password o username dimenticati?": riusa il flusso reset del portale
    # (che invia tramite l'SMTP del pannello e vale per TUTTI gli utenti).
    path('admin/password_reset/',
         RedirectView.as_view(pattern_name='portal:password_reset', permanent=False),
         name='admin_password_reset'),
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

"""
URL routes per checkout PayPal e webhook.

Da includere nel config/urls.py principale come:
    from django.urls import path, include
    
    urlpatterns = [
        # ... esistenti ...
        path('portal/checkout/', include('contracts.urls.checkout', namespace='checkout')),
        path('webhooks/', include('contracts.urls.webhooks')),
    ]

Le URL del portale generale (login, dashboard) saranno definite in altro modulo.
"""
from django.urls import path

from contracts.views import checkout

# Namespace 'portal' per le URL del portale sponsor
app_name = 'portal'

urlpatterns = [
    # PayPal Standard checkout
    path(
        'checkout/start/<uuid:contract_id>/',
        checkout.start_paypal_checkout,
        name='checkout_start_paypal',
    ),

    # Return e cancel URL (PayPal redirige qui)
    path(
        'checkout/return/<uuid:payment_id>/',
        checkout.paypal_return,
        name='checkout_return',
    ),
    path(
        'checkout/cancel/<uuid:payment_id>/',
        checkout.paypal_cancel,
        name='checkout_cancel',
    ),

    # Pagamento con carta diretta (Hosted Fields)
    path(
        'checkout/card/<uuid:contract_id>/',
        checkout.card_checkout_page,
        name='checkout_card',
    ),
    path(
        'checkout/card/capture/<uuid:payment_id>/',
        checkout.card_capture_ajax,
        name='checkout_card_capture',
    ),

    # Pagina success/error
    # (le viste portal:contract_detail e portal:checkout_success
    # saranno definite nel modulo del portale)
]

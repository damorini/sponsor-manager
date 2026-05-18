"""
URLs per webhook esterni (PayPal).

Da includere nel config/urls.py principale come:
    path('webhooks/', include('contracts.urls.webhooks')),

Webhook URL pubblico finale:
    https://gestionale.tuodominio.it/webhooks/paypal/

Configura questo URL su PayPal Developer Dashboard:
    https://developer.paypal.com/dashboard/applications/sandbox  (sandbox)
    https://developer.paypal.com/dashboard/applications/live     (produzione)
"""
from django.urls import path

from contracts.views import checkout

urlpatterns = [
    path('paypal/', checkout.paypal_webhook, name='paypal_webhook'),
]

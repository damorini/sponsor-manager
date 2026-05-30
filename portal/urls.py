"""
URL routing del portale sponsor (versione FINALE con tutte e 3 le parti).

Da SOSTITUIRE al portal/urls.py della parte 2.
"""
from django.urls import path

from portal.views import auth, dashboard, contract, catalog, cart, materials, wishlist, profile
from contracts.views import checkout

app_name = 'portal'

urlpatterns = [
    # Auth
    path('login/', auth.login_view, name='login'),
    path('logout/', auth.logout_view, name='logout'),
    
    # Password reset
    path('password-reset/', auth.password_reset_view, name='password_reset'),
    path('password-reset/done/', auth.password_reset_done_view,
         name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth.password_reset_confirm_view,
         name='password_reset_confirm'),
    path('password-reset/complete/', auth.password_reset_complete_view,
         name='password_reset_complete'),
    
    # Dashboard
    path('', dashboard.dashboard_view, name='dashboard'),
    path('eventi/', dashboard.events_view, name='events'),
    path('eventi/<uuid:event_id>/', dashboard.event_dashboard_view,
         name='event_dashboard'),
    path('eventi/<uuid:event_id>/scadenze/', materials.event_materials_view,
         name='event_materials'),
    path('profilo/', profile.profile_view, name='profile'),
    path('contracts/', dashboard.contracts_list_view, name='contracts_list'),
    path('contracts/<uuid:contract_id>/', contract.contract_detail_view,
         name='contract_detail'),
    
    # Catalogo
    path('catalog/', catalog.catalog_view, name='catalog'),
    path('catalog/event/<uuid:event_id>/', catalog.catalog_event_view,
         name='catalog_event'),
    path('catalog/service/<uuid:service_id>/', catalog.service_detail_view,
         name='service_detail'),
    
    # Carrello
    path('cart/', cart.cart_view, name='cart_view'),
    path('cart/add/', cart.cart_add_view, name='cart_add'),
    path('cart/remove/<uuid:line_id>/', cart.cart_remove_view, name='cart_remove'),
    path('cart/update/<uuid:line_id>/', cart.cart_update_quantity_view,
         name='cart_update_quantity'),
    path('cart/checkout/<uuid:contract_id>/', cart.cart_checkout_view,
         name='cart_checkout'),
    # Wishlist (pagina)
    path('wishlist/', wishlist.wishlist_page, name='wishlist_page'),
    
    # Materiali (parte 3)
    path('contracts/<uuid:contract_id>/materials/', materials.materials_view,
         name='materials_list'),
    path('materials/upload/<uuid:deadline_id>/', materials.material_upload_view,
         name='material_upload'),
    path('materials/content/<uuid:deadline_id>/', materials.material_content_view,
         name='material_content'),
    path('materials/download/<uuid:document_id>/', materials.material_download_view,
         name='material_download'),
    path('materials/delete/<uuid:document_id>/', materials.material_delete_view,
         name='material_delete'),
    
    # Wishlist
    path("api/wishlist/", wishlist.wishlist_view, name="wishlist_view"),
    path("api/wishlist/add/", wishlist.wishlist_add_api, name="wishlist_add"),
    path("api/wishlist/remove/", wishlist.wishlist_remove_api, name="wishlist_remove"),
    path("api/wishlist/check/", wishlist.wishlist_check_api, name="wishlist_check"),

    # Checkout PayPal
    path('checkout/start/<uuid:contract_id>/',
         checkout.start_paypal_checkout, name='checkout_start_paypal'),
    path('checkout/return/<uuid:payment_id>/',
         checkout.paypal_return, name='checkout_return'),
    path('checkout/cancel/<uuid:payment_id>/',
         checkout.paypal_cancel, name='checkout_cancel'),
    path('checkout/card/<uuid:contract_id>/',
         checkout.card_checkout_page, name='checkout_card'),
    path('checkout/card/capture/<uuid:payment_id>/',
         checkout.card_capture_ajax, name='checkout_card_capture'),
    path('checkout/success/<uuid:payment_id>/',
         checkout.paypal_return, name='checkout_success'),
    path('checkout/dev-mark-paid/<uuid:contract_id>/',
         checkout.dev_mark_paid, name='checkout_dev_mark_paid'),
]

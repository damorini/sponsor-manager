"""URL dell'app core: cruscotto."""
from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.cruscotto_home, name='cruscotto_home'),
    path('scadenze-cliente/', views.cruscotto_scadenze_cliente, name='cruscotto_scadenze_cliente'),
    path('scadenze-cliente/file/<uuid:document_id>/', views.cruscotto_scadenza_file, name='cruscotto_scadenza_file'),
    path('scadenze-cliente/<uuid:deadline_id>/', views.cruscotto_scadenza_dettaglio, name='cruscotto_scadenza_dettaglio'),
    path('evento/<uuid:pk>/', views.evento_dettaglio, name='cruscotto_evento'),
    path('evento/<uuid:pk>/servizio/<uuid:service_pk>/', views.servizio_dettaglio, name='cruscotto_servizio'),
    path('evento/<uuid:pk>/da-incassare/', views.da_incassare_evento, name='cruscotto_da_incassare'),
    path('utility/', views.utility_home, name='cruscotto_utility'),
    path('utility/template-catalogo/', views.download_template_catalogo, name='cruscotto_download_template_catalogo'),
    path('utility/importa-catalogo/', views.importa_catalogo_upload, name='cruscotto_importa_catalogo'),
    path('utility/template-servizi/', views.download_template_servizi, name='cruscotto_download_template_servizi'),
    path('utility/template-stand/', views.download_template_stand, name='cruscotto_download_template_stand'),
    path('utility/importa-servizi/', views.importa_servizi_upload, name='cruscotto_importa_servizi'),
    path('utility/importa-stand/', views.importa_stand_upload, name='cruscotto_importa_stand'),
    path('utility/export-servizi/', views.export_servizi, name='cruscotto_export_servizi'),
    path('utility/export-stand/', views.export_stand, name='cruscotto_export_stand'),
    path('utility/template-sponsor/', views.download_template_sponsor, name='cruscotto_download_template_sponsor'),
    path('utility/importa-sponsor/', views.importa_sponsor_upload, name='cruscotto_importa_sponsor'),
    path('utility/template-contatti/', views.download_template_contatti, name='cruscotto_download_template_contatti'),
    path('utility/importa-contatti/', views.importa_contatti_upload, name='cruscotto_importa_contatti'),
    path('traduci/', views.translate_view, name='translate'),
    path('manuale/', views.manuale, name='cruscotto_manuale'),
    path('manuale-operativo/', views.manuale_operativo, name='cruscotto_manuale_operativo'),
    path('catalog-service/<uuid:pk>/dati/', views.catalog_service_data, name='catalog_service_data'),
    path('documento/<uuid:document_id>/apri/', views.documento_apri, name='documento_apri'),
]

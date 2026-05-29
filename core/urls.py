"""URL dell'app core: cruscotto."""
from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.cruscotto_home, name='cruscotto_home'),
    path('evento/<uuid:pk>/', views.evento_dettaglio, name='cruscotto_evento'),
    path('evento/<uuid:pk>/servizio/<uuid:service_pk>/', views.servizio_dettaglio, name='cruscotto_servizio'),
    path('evento/<uuid:pk>/da-incassare/', views.da_incassare_evento, name='cruscotto_da_incassare'),
    path('utility/', views.utility_home, name='cruscotto_utility'),
    path('utility/template-servizi/', views.download_template_servizi, name='cruscotto_download_template_servizi'),
    path('utility/template-stand/', views.download_template_stand, name='cruscotto_download_template_stand'),
    path('utility/importa-servizi/', views.importa_servizi_upload, name='cruscotto_importa_servizi'),
    path('utility/importa-stand/', views.importa_stand_upload, name='cruscotto_importa_stand'),
    path('utility/export-servizi/', views.export_servizi, name='cruscotto_export_servizi'),
    path('utility/export-stand/', views.export_stand, name='cruscotto_export_stand'),
    path('traduci/', views.translate_view, name='translate'),
]

"""URL dell'app core: cruscotto."""
from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.cruscotto_home, name='cruscotto_home'),
    path('evento/<uuid:pk>/', views.evento_dettaglio, name='cruscotto_evento'),
    path('evento/<uuid:pk>/servizio/<uuid:service_pk>/', views.servizio_dettaglio, name='cruscotto_servizio'),
    path('utility/', views.utility_home, name='cruscotto_utility'),
    path('utility/template-servizi/', views.download_template_servizi, name='cruscotto_download_template_servizi'),
    path('utility/template-stand/', views.download_template_stand, name='cruscotto_download_template_stand'),
]

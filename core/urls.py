"""URL dell'app core: cruscotto."""
from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.cruscotto_home, name='cruscotto_home'),
]

"""
ASGI config (async). Per ora non usato; pronto per future estensioni con
Django Channels (websocket per notifiche live).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

application = get_asgi_application()

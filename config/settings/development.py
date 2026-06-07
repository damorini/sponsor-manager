"""
Settings di sviluppo locale.

Si attiva impostando: DJANGO_SETTINGS_MODULE=config.settings.development

Differenze chiave da production:
- DEBUG = True (mostra stack trace in browser)
- Email su console invece che SMTP reale
- django-debug-toolbar attivo
- Sicurezza HTTPS disabilitata
"""
from .base import *  # noqa: F401, F403
from .base import INSTALLED_APPS, MIDDLEWARE, BASE_DIR

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# In sviluppo usiamo solo la porta 8001 (la 8000 è stata dismessa).
# I link nelle email/notifiche puntano qui.
SITE_URL = 'http://localhost:8001'
PORTAL_URL = 'http://localhost:8001/portal/'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

INSTALLED_APPS += [
    'debug_toolbar',
]

MIDDLEWARE += [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

INTERNAL_IPS = ['127.0.0.1']

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

import logging
logging.getLogger('sponsor_manager').setLevel(logging.DEBUG)

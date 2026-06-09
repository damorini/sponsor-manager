"""
Settings base condivise tra ambiente di sviluppo e produzione.

NON importare direttamente questo file: usa settings.development o
settings.production a seconda dell'ambiente.

Variabili d'ambiente lette tramite python-decouple:
- decouple cerca prima nel file .env, poi in os.environ
- config(NAME, default=X) restituisce X se NAME non è settata
- config(NAME) senza default solleva eccezione se la var manca
"""
from pathlib import Path

from decouple import Csv, config

# MIME type per immagini moderne: alcuni sistemi non hanno .webp/.avif in
# /etc/mime.types, quindi il dev server li servirebbe col tipo sbagliato e il
# browser non li mostrerebbe nel tag <img>. Qui li registriamo all'avvio.
import mimetypes
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('image/avif', '.avif')

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')
DEEPL_API_KEY = config('DEEPL_API_KEY', default='')  # traduzione IT->EN (chiave gratuita deepl.com)
# Se True, al salvataggio (admin + import Excel) l'inglese mancante viene
# compilato automaticamente da DeepL partendo dall'italiano.
AUTO_TRANSLATE_ON_SAVE = config('AUTO_TRANSLATE_ON_SAVE', default=True, cast=bool)

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'core',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.postgres',

    'django_extensions',

    'users',
    'events',
    'sponsors',
    'venues',
    'catalog',
    'contracts',
    'shared',
    'portal',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'portal.context_processors.branding',
                'portal.context_processors.cart_count',
                'core.context_processors.admin_badges',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='sponsor_manager'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'portal:login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'portal:login'

LANGUAGE_CODE = 'it'
USE_THOUSAND_SEPARATOR = True
TIME_ZONE = 'Europe/Rome'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('it', 'Italiano'),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

PAYPAL_MODE = config('PAYPAL_MODE', default='sandbox')
PAYPAL_CLIENT_ID = config('PAYPAL_CLIENT_ID', default='')
PAYPAL_CLIENT_SECRET = config('PAYPAL_CLIENT_SECRET', default='')
PAYPAL_WEBHOOK_ID = config('PAYPAL_WEBHOOK_ID', default='')

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')
SERVER_EMAIL = config('SERVER_EMAIL', default='server@example.com')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'sponsor_manager': {
            'handlers': ['console'],
            'level': 'DEBUG' if config('DEBUG', default=False, cast=bool) else 'INFO',
            'propagate': False,
        },
    },
}


# ============================================================================
# Branding (portale + email)
# ============================================================================
ORGANIZER_DISPLAY_NAME = config('ORGANIZER_DISPLAY_NAME', default='VALET S.r.l.')
ORGANIZER_ADDRESS = config('ORGANIZER_ADDRESS',
                            default='Via Dei Fornaciai 29/B, 40129 Bologna')
SUPPORT_EMAIL = config('SUPPORT_EMAIL', default='info@valet.it')
# Dati per il pagamento via bonifico (PLACEHOLDER: sostituire nel .env con quelli reali)
BANK_TRANSFER_HOLDER = config('BANK_TRANSFER_HOLDER', default='Valet S.r.l. (DA CONFIGURARE)')
BANK_TRANSFER_BANK = config('BANK_TRANSFER_BANK', default='Banca di Esempio S.p.A. (DA CONFIGURARE)')
BANK_TRANSFER_IBAN = config('BANK_TRANSFER_IBAN', default='IT00 X000 0000 0000 0000 0000 000')
BANK_TRANSFER_BIC = config('BANK_TRANSFER_BIC', default='')
BRAND_LOGO_URL = config('BRAND_LOGO_URL', default='')
BRAND_PRIMARY_COLOR = config('BRAND_PRIMARY_COLOR', default='#1d6534')

# URL pubblico: se SITE_URL non e' impostato, lo deriva da SITE_ADDRESS (lo
# stesso dominio usato da Caddy per l'HTTPS). Cosi' i link in email/PDF sono
# assoluti e corretti; cambiando dominio basta cambiare SITE_ADDRESS.
SITE_ADDRESS = config('SITE_ADDRESS', default='')
_derived_site_url = (
    f'https://{SITE_ADDRESS}'
    if SITE_ADDRESS and SITE_ADDRESS not in ('localhost', '127.0.0.1')
    else 'http://localhost:8000'
)
SITE_URL = config('SITE_URL', default='') or _derived_site_url
PORTAL_URL = config('PORTAL_URL', default='') or (SITE_URL.rstrip('/') + '/portal/')
SIGNATURE_PLACE = config('SIGNATURE_PLACE', default='Bologna')


# ============================================================================
# Media (upload materiali sponsor)
# ============================================================================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ============================================================================
# Email
# ============================================================================
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL',
                             default='Sponsor Manager <noreply@valet.it>')
EMAIL_BACKEND = config('EMAIL_BACKEND',
                        default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)


# ============================================================================
# Celery (task asincroni)
# ============================================================================
# Default: usa REDIS_URL (così basta impostare REDIS_URL nell'ambiente).
# Sovrascrivibili con CELERY_BROKER_URL / CELERY_RESULT_BACKEND espliciti.
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=config('REDIS_URL', default='redis://localhost:6379/0'))
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=config('REDIS_URL', default='redis://localhost:6379/0'))
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'Europe/Rome'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60


# ============================================================================
# PayPal
# ============================================================================
PAYPAL_MODE = config('PAYPAL_MODE', default='sandbox')
PAYPAL_CLIENT_ID = config('PAYPAL_CLIENT_ID', default='')
PAYPAL_CLIENT_SECRET = config('PAYPAL_CLIENT_SECRET', default='')
PAYPAL_WEBHOOK_ID = config('PAYPAL_WEBHOOK_ID', default='')
PAYPAL_MERCHANT_ID = config('PAYPAL_MERCHANT_ID', default='')

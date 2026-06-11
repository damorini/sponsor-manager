from django.apps import AppConfig


class VenuesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'venues'

    def ready(self):
        from . import signals  # noqa: F401  (registra i signal Stand)

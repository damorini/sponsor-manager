from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Impostazioni'

    def ready(self):
        # Registra i segnali (auto-traduzione IT->EN al salvataggio)
        from . import signals  # noqa: F401

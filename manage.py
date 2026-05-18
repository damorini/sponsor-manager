#!/usr/bin/env python
"""
Django management script.

Default settings: config.settings.development (per non rischiare di girare
in produzione per errore in locale).

Per attivare manualmente la produzione:
    DJANGO_SETTINGS_MODULE=config.settings.production python manage.py migrate
"""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django non sembra installato. "
            "Hai attivato il virtualenv? Hai fatto pip install -r requirements.txt?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

"""
Auto-import dell'app Celery così @shared_task le trova ovunque.
"""
from .celery import app as celery_app

__all__ = ('celery_app',)

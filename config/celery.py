"""
Configurazione Celery completa con scheduling task ricorrenti.

Sostituisce il config/celery.py della v1.

Schedule:
- 07:00 ogni giorno → send_operator_alerts (controlla situazioni urgenti)
- 08:00 ogni giorno → check_upcoming_deadlines (reminder T-10, T-3, T-0)
- 09:00 ogni giorno → check_overdue_deadlines (solleciti scadute)
- 10:00 ogni giorno → check_abandoned_carts (recovery carrelli)

Per cambiare orari: modifica le entries in CELERY_BEAT_SCHEDULE qui sotto.
Le ore sono in TIME_ZONE configurato in settings (default: Europe/Rome).

In development con CELERY_TASK_ALWAYS_EAGER=True, Beat NON gira: i task
schedulati si lanciano a mano per testare:
    from contracts.tasks.scheduled import check_upcoming_deadlines
    check_upcoming_deadlines()
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('sponsor_manager')

# Carica config da Django settings (variabili che iniziano con CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover dei task in tutte le app installate
# Cerca in <app>/tasks.py o <app>/tasks/*.py
app.autodiscover_tasks()


# ============================================================================
# Schedule task ricorrenti
# ============================================================================

app.conf.beat_schedule = {
    # 07:00 — Alert urgenze per operatore
    'send_operator_alerts_daily': {
        'task': 'contracts.tasks.scheduled.send_operator_alerts',
        'schedule': crontab(hour=7, minute=0),
    },

    # 08:00 — Reminder scadenze in arrivo
    'check_upcoming_deadlines_daily': {
        'task': 'contracts.tasks.scheduled.check_upcoming_deadlines',
        'schedule': crontab(hour=8, minute=0),
    },

    # 09:00 — Solleciti scadenze in ritardo
    'check_overdue_deadlines_daily': {
        'task': 'contracts.tasks.scheduled.check_overdue_deadlines',
        'schedule': crontab(hour=9, minute=0),
    },

    # 10:00 — Recovery carrelli abbandonati
    'check_abandoned_carts_daily': {
        'task': 'contracts.tasks.scheduled.check_abandoned_carts',
        'schedule': crontab(hour=10, minute=0),
    },

    # Esempi alternativi (commentati):
    
    # Settimanale lunedì alle 8:00:
    # 'weekly_summary': {
    #     'task': 'contracts.tasks.scheduled.weekly_summary',
    #     'schedule': crontab(hour=8, minute=0, day_of_week=1),
    # },
    
    # Ogni 30 minuti (per testing):
    # 'frequent_check': {
    #     'task': 'contracts.tasks.scheduled.something',
    #     'schedule': crontab(minute='*/30'),
    # },
}


@app.task(bind=True)
def debug_task(self):
    """Task di debug per verificare che Celery funzioni."""
    print(f'Request: {self.request!r}')

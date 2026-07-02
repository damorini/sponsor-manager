"""
Package contenente i task Celery dell'app contracts.

- notifications: task on-demand triggerati da eventi
- scheduled: task ricorrenti gestiti da Celery Beat

IMPORTANTE: importiamo qui i sotto-moduli cosi' che l'autodiscover di Celery
(che importa `contracts.tasks`) esegua i decoratori @shared_task e REGISTRI tutti
i task nel worker. Senza questi import il worker riceve "unregistered task" e il
task viene scartato (es. send_contract_signed_notification non parte).
"""
from . import notifications, scheduled  # noqa: F401


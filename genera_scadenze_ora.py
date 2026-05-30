# Genera subito le scadenze del contratto dai template. Esegui:
#   python manage.py shell < genera_scadenze_ora.py
from contracts.models import Contract

c = Contract.objects.get(contract_number="AITEBCONG-26-008")
print("Prima:", c.deadlines.count(), "scadenze")
try:
    c._generate_deadlines()
except Exception as e:
    print("ERRORE durante la generazione:", repr(e))
print("Dopo :", c.deadlines.count(), "scadenze")
for d in c.deadlines.all():
    print("  -", d.title, "| tipo:", d.deadline_type, "| due:", d.due_date,
          "| richiesta:", d.submission_kind)
print("FATTO")

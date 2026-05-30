# Diagnosi scadenze Workshop. Esegui (sola lettura, non modifica nulla):
#   python manage.py shell < diagnostica_scadenze.py
from contracts.models import Contract

NUM = "AITEBCONG-26-008"
print("=" * 64)
c = Contract.objects.filter(contract_number=NUM).first()
if not c:
    print("CONTRATTO", NUM, "NON TROVATO")
else:
    ev = c.event
    print("Contratto:", c.contract_number, "| stato:", c.status, "| tipo:", c.contract_kind)
    print("Sponsor:", c.sponsor)
    print("Evento:", ev, "| inizio:", getattr(ev, "start_date", None))
    print("Scadenze gia presenti sul contratto:", c.deadlines.count())
    for d in c.deadlines.all():
        print("   - scadenza:", d.title, "| tipo:", d.deadline_type, "| due:", d.due_date)
    print("-" * 64)
    print("RIGHE del contratto e servizi collegati:")
    for line in c.lines.select_related("service").all():
        s = line.service
        if not s:
            print("   - riga SENZA servizio:", line.service_name_snapshot)
            continue
        tmpls = list(s.deadline_templates.all())
        attivi = [t for t in tmpls if t.is_active]
        try:
            nome = s.get_name()
        except Exception:
            nome = s.code
        print("   - servizio:", nome, "(code:", s.code, ")")
        print("        triggers_deadlines (Genera scadenze):", s.triggers_deadlines)
        print("        template totali:", len(tmpls), "| attivi:", len(attivi))
        for t in tmpls:
            try:
                ncampi = t.content_fields.count()
            except Exception:
                ncampi = "?"
            print("          * template:", t.title, "| attivo:", t.is_active,
                  "| tipo:", t.deadline_type, "| giorni_prima:", t.days_before_event,
                  "| campi:", ncampi)
print("=" * 64)
print("FINE DIAGNOSI")

# Diagnosi: perche' il cruscotto servizio mostra 0 prenotazioni. Sola lettura.
#   python manage.py shell < diagnostica_cruscotto_servizio.py
from datetime import date
from contracts.models import Contract, ContractStatus, ContractLine
from catalog.models import Service

NUM = "AITEBCONG-26-008"
c = Contract.objects.filter(contract_number=NUM).first()
if not c:
    print("Contratto", NUM, "non trovato"); raise SystemExit
print("Contratto:", c.contract_number, "| status:", c.status,
      "| kind:", c.contract_kind, "| event_id:", c.event_id)
print("-" * 60)
print("RIGHE del contratto:")
for l in c.lines.all():
    ev_s = None
    if l.service_id:
        try:
            ev_s = l.service.event_id
        except Exception:
            ev_s = "?"
    print("  service_id:", l.service_id, "| snapshot:", l.service_name_snapshot,
          "| service.event_id:", ev_s, "| notes:", repr((l.notes or ''))[:30],
          "| line_total:", l.line_total)
print("-" * 60)
print("SERVIZI 'workshop' per l'evento del contratto:")
ws = list(Service.objects.filter(event_id=c.event_id))
for s in ws:
    print("  Service id:", s.id, "| code:", s.code, "| event_id:", s.event_id)
print("-" * 60)
# replica esatta della pagina cruscotto servizio
contratti_ev = list(Contract.objects.filter(event_id=c.event_id)
                    .exclude(status=ContractStatus.CANCELLED))
CONFIRMED = {ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED}
cats = set()
for x in contratti_ev:
    if x.status in CONFIRMED:
        cats.add(x.id)
print("Contratti evento (no annullati):", len(contratti_ev),
      "| confermati:", len(cats), "| il nostro e' confermato:", c.id in cats)
# per ogni servizio del contratto, conta righe nei contratti confermati
serv_ids = set(l.service_id for l in c.lines.all() if l.service_id)
for sid in serv_ids:
    n = (ContractLine.objects.filter(service_id=sid, contract_id__in=cats)
         .exclude(notes__startswith='stand:').exclude(notes__startswith='block:')
         .count())
    print("  righe per service", sid, "nei confermati:", n)
print("FINE")

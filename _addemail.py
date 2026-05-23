p = "contracts/models.py"
c = open(p, encoding="utf-8").read()
if "send_contract_signed_notification" in c:
    print("gia' presente")
else:
    anc = """        # Genera scadenze concrete dai template
        self._generate_deadlines()

    @transaction.atomic
    def mark_as_pending_payment(self):"""
    new = """        # Genera scadenze concrete dai template
        self._generate_deadlines()

        # Notifica email di conferma (sincrona in dev con EAGER=True).
        try:
            from contracts.tasks.notifications import send_contract_signed_notification
            send_contract_signed_notification.delay(self.id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Invio notifica firma fallito per contract %s", self.id
            )

    @transaction.atomic
    def mark_as_pending_payment(self):"""
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,new,1))
        print("notifica email agganciata")
    else:
        print("ATTENZIONE: ancora non trovata")

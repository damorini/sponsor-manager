p = "contracts/payments.py"
c = open(p, encoding="utf-8").read()
if "send_payment_confirmation_notification" in c:
    print("gia' presente")
else:
    anc = """        # Firma il contratto associato
        self.contract.mark_payment_succeeded()

    def mark_failed(self, reason=''):"""
    new = """        # Firma il contratto associato
        self.contract.mark_payment_succeeded()

        # Email di conferma pagamento (sincrona in dev con EAGER=True).
        try:
            from contracts.tasks.notifications import send_payment_confirmation_notification
            send_payment_confirmation_notification.delay(self.id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Invio conferma pagamento fallito per payment %s", self.id
            )

    def mark_failed(self, reason=''):"""
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,new,1))
        print("notifica pagamento agganciata")
    else:
        print("ATTENZIONE: ancora non trovata")

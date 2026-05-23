# 1) Aggiunge property days_remaining al modello Deadline
MP = "contracts/models.py"
c = open(MP, encoding="utf-8").read()
if "def days_remaining" in c:
    print("[modello] days_remaining gia' presente, salto.")
else:
    ancora = '''    @property
    def days_until_due(self):
        """Giorni mancanti alla scadenza (negativo se in ritardo)."""
        return (self.due_date - timezone.now().date()).days'''
    blocco = ancora + '''

    @property
    def days_remaining(self):
        """Giorni mancanti o di ritardo, sempre positivo (per i template)."""
        return abs((self.due_date - timezone.now().date()).days)'''
    if ancora in c:
        open(MP, "w", encoding="utf-8").write(c.replace(ancora, blocco, 1))
        print("[modello] days_remaining aggiunto.")
    else:
        print("[modello] ATTENZIONE: ancora non trovata.")

# 2) Rimuove dalla view il blocco che sovrascrive is_overdue/days_remaining
VP = "portal/views/contract.py"
c = open(VP, encoding="utf-8").read()
vecchio = '''    # Scadenze operative
    deadlines = contract.deadlines.select_related('deadline_template').order_by('due_date')
    today = date.today()
    for d in deadlines:
        if d.due_date >= today:
            d.days_remaining = (d.due_date - today).days
            d.is_overdue = False
        else:
            d.days_remaining = (today - d.due_date).days
            d.is_overdue = True'''
nuovo = '''    # Scadenze operative (is_overdue e days_remaining sono property del modello)
    deadlines = contract.deadlines.select_related('deadline_template').order_by('due_date')'''
if vecchio in c:
    open(VP, "w", encoding="utf-8").write(c.replace(vecchio, nuovo, 1))
    print("[view] blocco sovrascrittura rimosso.")
elif "is_overdue = True" not in c:
    print("[view] gia' corretto, salto.")
else:
    print("[view] ATTENZIONE: blocco non trovato esatto.")
print("Fatto.")

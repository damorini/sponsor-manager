PATH = "contracts/models.py"
BLOCCO = '''    def _generate_contract_number(self):
        from datetime import date
        anno = date.today().year
        prefix = f"{anno}-N"
        with transaction.atomic():
            ultimo = (
                Contract.all_objects
                .filter(contract_number__startswith=prefix)
                .order_by('-contract_number')
                .values_list('contract_number', flat=True)
                .first()
            )
            if ultimo:
                try:
                    n = int(ultimo.split('-N')[1]) + 1
                except (IndexError, ValueError):
                    n = 1
            else:
                n = 1
            while True:
                candidato = f"{prefix}{n:04d}"
                if not Contract.all_objects.filter(contract_number=candidato).exists():
                    return candidato
                n += 1

    def save(self, *args, **kwargs):
        if not self.contract_number:
            self.contract_number = self._generate_contract_number()
        super().save(*args, **kwargs)

'''
ANCORA = "    def recalculate_totals(self, save=True):"
with open(PATH, encoding="utf-8") as f:
    c = f.read()
if "_generate_contract_number" in c:
    print("Patch GIA' applicata.")
elif ANCORA not in c:
    print("ERRORE: punto di inserimento non trovato.")
else:
    open(PATH, "w", encoding="utf-8").write(c.replace(ANCORA, BLOCCO + ANCORA, 1))
    print("Patch applicata.")

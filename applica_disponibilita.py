#!/usr/bin/env python3
"""
GESTIONE DISPONIBILITA' SERVIZI/STAND.

Regole (decise con Daniele):
  - Ogni Service ha una quantita' totale disponibile (total_available).
  - La disponibilita' si calcola AL VOLO: total_available - (somma quantity
    nelle righe di contratti NON cancellati). Cosi' e' sempre corretta e il
    "torna disponibile alla cancellazione" e' automatico.
  - L'impegno scatta appena la riga e' in un contratto (anche bozza).
  - Quando si aggiunge/modifica una riga che sforerebbe la disponibilita',
    viene bloccata con un errore chiaro.
  - total_available vuoto (None) = illimitato (nessun limite).

Modifiche:
  1. catalog/models.py   -> campo total_available + metodi
     quantity_committed() e quantity_available().
  2. catalog/admin.py     -> mostra total_available e una colonna "Disponibili".
  3. contracts/models.py  -> ContractLine.clean() blocca se si sfora.

Backup di ogni file (.bak_dispon). Idempotente.
DOPO: migrazione
    python manage.py makemigrations catalog
    python manage.py migrate

Lancialo dalla cartella del progetto:
    python applica_disponibilita.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CAT_MODELS = ROOT / "catalog" / "models.py"
CAT_ADMIN = ROOT / "catalog" / "admin.py"
CT_MODELS = ROOT / "contracts" / "models.py"
SUFFIX = ".bak_dispon"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Mi fermo. Eventualmente ripristina dai .bak_dispon.")
    sys.exit(1)


def backup_write(path, content):
    shutil.copy2(path, str(path) + SUFFIX)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] {path.relative_to(ROOT)} aggiornato")


for p in (CAT_MODELS, CAT_ADMIN, CT_MODELS):
    if not p.exists():
        fail(f"Non trovo {p}.")

cat_src = CAT_MODELS.read_text(encoding="utf-8")
if "total_available" in cat_src:
    print("[OK] total_available gia' presente (salto tutto).")
    sys.exit(0)

# ===========================================================================
# 1. CATALOG models — campo + metodi
# ===========================================================================
anchor = (
    "    max_quantity = models.IntegerField(\n"
    "        null=True,\n"
    "        blank=True,\n"
    "        validators=[MinValueValidator(1)],\n"
    '        verbose_name="Quantità massima",\n'
    "    )\n"
)
if anchor not in cat_src:
    fail("Non trovo il campo max_quantity in catalog/models.py.")

new_field = anchor + (
    "    total_available = models.IntegerField(\n"
    "        null=True,\n"
    "        blank=True,\n"
    "        validators=[MinValueValidator(0)],\n"
    '        verbose_name="Quantità totale disponibile",\n'
    '        help_text="Quanti pezzi esistono in totale (es. 1 per uno stand '
    'unico). Vuoto = illimitato.",\n'
    "    )\n"
)
cat_src = cat_src.replace(anchor, new_field, 1)

# Aggiungo i metodi: li inserisco prima di 'def calculate_price'
method_anchor = "    def calculate_price(self, quantity=1):"
if method_anchor not in cat_src:
    fail("Non trovo calculate_price in catalog/models.py per ancorare i metodi.")

methods = (
    "    def quantity_committed(self, exclude_contract_id=None):\n"
    '        """Somma delle quantita\' impegnate in contratti NON cancellati."""\n'
    "        from django.db.models import Sum\n"
    "        qs = self.contract_lines.exclude(contract__status='cancelled')\n"
    "        if exclude_contract_id is not None:\n"
    "            qs = qs.exclude(contract_id=exclude_contract_id)\n"
    "        return qs.aggregate(tot=Sum('quantity'))['tot'] or 0\n"
    "\n"
    "    def quantity_available(self, exclude_contract_id=None):\n"
    '        """Pezzi ancora disponibili. None = illimitato."""\n'
    "        if self.total_available is None:\n"
    "            return None\n"
    "        return self.total_available - self.quantity_committed(exclude_contract_id)\n"
    "\n"
    "    @property\n"
    "    def is_sold_out(self):\n"
    "        avail = self.quantity_available()\n"
    "        return avail is not None and avail <= 0\n"
    "\n"
    + method_anchor
)
cat_src = cat_src.replace(method_anchor, methods, 1)
backup_write(CAT_MODELS, cat_src)

# ===========================================================================
# 2. CATALOG admin — colonna disponibilità + campo in form
# ===========================================================================
adm_src = CAT_ADMIN.read_text(encoding="utf-8")

# 2a. aggiungo un metodo display e lo metto in list_display se esiste
if "availability_display" not in adm_src:
    # trovo la classe admin del Service
    import re
    m = re.search(r"class (\w*Service\w*Admin)\(admin\.ModelAdmin\):\n", adm_src)
    if not m:
        print("[..] Non trovo la classe admin del Service: salto la parte admin "
              "(il campo esistera' comunque nel form di default).")
    else:
        cls_line = m.group(0)
        disp = cls_line + (
            "    @admin.display(description='Disponibili')\n"
            "    def availability_display(self, obj):\n"
            "        av = obj.quantity_available()\n"
            "        if av is None:\n"
            "            return '\u221e (illimitato)'\n"
            "        comm = obj.quantity_committed()\n"
            "        return f'{av} liberi / {obj.total_available} tot ({comm} assegnati)'\n"
            "\n"
        )
        adm_src = adm_src.replace(cls_line, disp, 1)
        # aggiungo alla list_display agganciandomi a 'is_active',
        adm_src = adm_src.replace(
            "        'ecommerce_badge', 'cutoff_display', 'is_active',\n",
            "        'ecommerce_badge', 'cutoff_display', 'is_active', 'availability_display',\n",
            1
        )
    backup_write(CAT_ADMIN, adm_src)
else:
    print("[OK] availability_display gia' presente (salto admin).")

# ===========================================================================
# 3. CONTRACTS models — validazione su ContractLine
# ===========================================================================
ct_src = CT_MODELS.read_text(encoding="utf-8")
if "quantity_available" in ct_src:
    print("[OK] Validazione disponibilita' gia' presente in ContractLine (salto).")
else:
    # aggancio: la definizione della classe ContractLine
    cl_anchor = "class ContractLine(TimeStampedModel):\n"
    if cl_anchor not in ct_src:
        fail("Non trovo class ContractLine in contracts/models.py.")

    clean_method = cl_anchor + (
        "    def clean(self):\n"
        '        """Blocca l\'assegnazione se il servizio e\' esaurito."""\n'
        "        from django.core.exceptions import ValidationError\n"
        "        super_clean = getattr(super(), 'clean', None)\n"
        "        if super_clean:\n"
        "            super_clean()\n"
        "        if not self.service_id:\n"
        "            return\n"
        "        # contratto cui appartiene questa riga (per escluderlo dal conteggio)\n"
        "        contract_id = self.contract_id\n"
        "        avail = self.service.quantity_available(exclude_contract_id=contract_id)\n"
        "        if avail is None:\n"
        "            return  # illimitato\n"
        "        # quanto gia' impegnato da QUESTO contratto per lo stesso servizio\n"
        "        already = 0\n"
        "        if contract_id:\n"
        "            from django.db.models import Sum\n"
        "            already = (self.service.contract_lines\n"
        "                       .filter(contract_id=contract_id)\n"
        "                       .exclude(pk=self.pk)\n"
        "                       .aggregate(t=Sum('quantity'))['t'] or 0)\n"
        "        richiesta = (self.quantity or 0) + already\n"
        "        if richiesta > avail + already:\n"
        "            raise ValidationError(\n"
        "                f\"Servizio '{self.service}' non disponibile in quantita' \"\n"
        "                f\"sufficiente: richiesti {self.quantity}, disponibili {avail}.\"\n"
        "            )\n"
        "\n"
    )
    ct_src = ct_src.replace(cl_anchor, clean_method, 1)
    backup_write(CT_MODELS, ct_src)

print("\n=== CODICE APPLICATO. ===")
print("Ora la migrazione:")
print("    python manage.py makemigrations catalog")
print("    python manage.py migrate")

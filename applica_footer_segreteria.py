#!/usr/bin/env python3
"""
TAPPA 2 — Pannello "Impostazioni segreteria" + footer email.

Fa queste modifiche:
  1. core/models.py -> nuovo modello OrganizerSettings (singleton) con:
     nome, indirizzo, email, telefono, sito web, P.IVA, REA, logo (FileField).
  2. core/admin.py  -> registra il pannello nell'admin (una sola scheda).
  3. shared/email_templates/base/email_base.html -> footer con logo a sinistra
     e riferimenti a fianco, che legge dai dati passati nel contesto.
  4. contracts/services/email_sender.py -> il contesto comune carica i dati
     della segreteria dal modello (con fallback ai settings se non compilato).

Backup di ogni file toccato (.bak_footer). Se non trova un punto atteso, si ferma.

DOPO lo script servira' la migrazione (te la guido io):
    python manage.py makemigrations core
    python manage.py migrate core

Lancialo dalla cartella del progetto:
    python applica_footer_segreteria.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "core" / "models.py"
ADMIN = ROOT / "core" / "admin.py"
BASE = ROOT / "shared" / "email_templates" / "base" / "email_base.html"
SENDER = ROOT / "contracts" / "services" / "email_sender.py"
SUFFIX = ".bak_footer"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Lo script si ferma qui.")
    sys.exit(1)


for p in (MODELS, ADMIN, BASE, SENDER):
    if not p.exists():
        fail(f"Non trovo {p}. Lancia dalla cartella del progetto.")

# ===========================================================================
# 1. MODELLO OrganizerSettings (accodato in fondo a core/models.py)
# ===========================================================================
models_src = MODELS.read_text(encoding="utf-8")
if "class OrganizerSettings" in models_src:
    print("[OK] OrganizerSettings gia' presente (salto modello).")
else:
    model_code = '''

class OrganizerSettings(models.Model):
    """
    Impostazioni della segreteria organizzativa (singleton: un solo record).
    Usate nel footer di tutte le email. Modificabili dall'admin.
    """
    name = models.CharField(
        max_length=200, blank=True, verbose_name="Nome segreteria",
    )
    address = models.TextField(
        blank=True, verbose_name="Indirizzo",
    )
    email = models.EmailField(
        blank=True, verbose_name="Email",
    )
    phone = models.CharField(
        max_length=50, blank=True, verbose_name="Telefono",
    )
    website = models.CharField(
        max_length=200, blank=True, verbose_name="Sito internet",
    )
    vat_number = models.CharField(
        max_length=30, blank=True, verbose_name="P.IVA",
    )
    rea = models.CharField(
        max_length=30, blank=True, verbose_name="REA",
    )
    logo = models.FileField(
        upload_to='organizer/', null=True, blank=True,
        verbose_name="Logo segreteria",
        help_text="Logo mostrato nel footer delle email.",
    )

    class Meta:
        verbose_name = "Impostazioni segreteria"
        verbose_name_plural = "Impostazioni segreteria"

    def __str__(self):
        return self.name or "Impostazioni segreteria"

    def save(self, *args, **kwargs):
        # Singleton: forza sempre pk=1, esiste un solo record.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Restituisce l'unico record, creandolo vuoto se non esiste."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
'''
    shutil.copy2(MODELS, str(MODELS) + SUFFIX)
    MODELS.write_text(models_src.rstrip() + "\n" + model_code, encoding="utf-8")
    print(f"[OK] core/models.py aggiornato (backup: core/models.py{SUFFIX})")

# ===========================================================================
# 2. ADMIN — registra il singleton
# ===========================================================================
admin_src = ADMIN.read_text(encoding="utf-8")
if "OrganizerSettings" in admin_src:
    print("[OK] OrganizerSettings gia' registrato nell'admin (salto).")
else:
    admin_code = '''

from django.urls import reverse
from django.utils.html import format_html
from .models import OrganizerSettings


@admin.register(OrganizerSettings)
class OrganizerSettingsAdmin(admin.ModelAdmin):
    """Pannello unico (singleton) per i dati della segreteria."""
    fieldsets = (
        ("Anagrafica segreteria", {
            "fields": ("name", "address", "email", "phone", "website"),
        }),
        ("Dati fiscali", {
            "fields": ("vat_number", "rea"),
        }),
        ("Logo", {
            "fields": ("logo",),
        }),
    )

    def has_add_permission(self, request):
        # Niente "Aggiungi": esiste un solo record.
        return not OrganizerSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Vai dritto alla scheda unica invece della lista.
        obj = OrganizerSettings.load()
        from django.shortcuts import redirect
        url = reverse("admin:core_organizersettings_change", args=[obj.pk])
        return redirect(url)
'''
    shutil.copy2(ADMIN, str(ADMIN) + SUFFIX)
    ADMIN.write_text(admin_src.rstrip() + "\n" + admin_code, encoding="utf-8")
    print(f"[OK] core/admin.py aggiornato (backup: core/admin.py{SUFFIX})")

# ===========================================================================
# 3. EMAIL_SENDER — carica i dati segreteria nel contesto
# ===========================================================================
sender_src = SENDER.read_text(encoding="utf-8")
if "organizer_settings" in sender_src:
    print("[OK] email_sender gia' carica organizer_settings (salto).")
else:
    anchor = "    common = {\n"
    if anchor not in sender_src:
        fail("Non trovo l'inizio di 'common = {' in email_sender.py.")
    loader = (
        "    # Dati segreteria dal pannello admin (fallback ai settings)\n"
        "    try:\n"
        "        from core.models import OrganizerSettings\n"
        "        _org = OrganizerSettings.load()\n"
        "    except Exception:\n"
        "        _org = None\n"
        "\n"
        "    common = {\n"
    )
    sender_src = sender_src.replace(anchor, loader, 1)

    # aggiunge le variabili org_* subito dopo 'site_url'
    site_line = "        'site_url': getattr(settings, 'SITE_URL', '').rstrip('/'),\n"
    if site_line not in sender_src:
        fail("Non trovo la riga 'site_url' in email_sender.py (tappa 1 applicata?).")
    org_vars = site_line + (
        "        'org_name': (_org.name if _org and _org.name else None)"
        " or getattr(settings, 'ORGANIZER_DISPLAY_NAME', ''),\n"
        "        'org_address': (_org.address if _org else '') ,\n"
        "        'org_email': (_org.email if _org else '') ,\n"
        "        'org_phone': (_org.phone if _org else '') ,\n"
        "        'org_website': (_org.website if _org else '') ,\n"
        "        'org_vat': (_org.vat_number if _org else '') ,\n"
        "        'org_rea': (_org.rea if _org else '') ,\n"
        "        'org_logo_url': ((getattr(settings, 'SITE_URL', '').rstrip('/')"
        " + _org.logo.url) if (_org and _org.logo) else ''),\n"
    )
    sender_src = sender_src.replace(site_line, org_vars, 1)

    shutil.copy2(SENDER, str(SENDER) + SUFFIX)
    SENDER.write_text(sender_src, encoding="utf-8")
    print(f"[OK] email_sender.py aggiornato (backup: email_sender.py{SUFFIX})")

# ===========================================================================
# 4. TEMPLATE BASE — footer con logo a sinistra + riferimenti a fianco
# ===========================================================================
base_src = BASE.read_text(encoding="utf-8")
if "footer-segreteria" in base_src:
    print("[OK] Footer segreteria gia' presente nel template base (salto).")
else:
    # Sostituiamo l'intero <td> del footer esistente.
    old_footer_start = '        <!-- FOOTER -->\n'
    if old_footer_start not in base_src:
        fail("Non trovo '<!-- FOOTER -->' nel template base.")

    # Troviamo il blocco footer completo (dal commento alla chiusura </tr>)
    import re
    pattern = re.compile(
        r"        <!-- FOOTER -->\n.*?</tr>\n", re.DOTALL
    )
    new_footer = (
        '        <!-- FOOTER segreteria: logo a sinistra, riferimenti a fianco -->\n'
        '        <tr class="footer-segreteria">\n'
        '          <td style="padding:24px 40px; background-color:#f9fafb;\n'
        '                     border-top:1px solid #e5e7eb; color:#6b7280;\n'
        '                     font-size:12px; line-height:1.5;">\n'
        '            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">\n'
        '              <tr>\n'
        '                {% if org_logo_url %}\n'
        '                <td valign="top" style="width:120px; padding-right:16px;">\n'
        '                  <img src="{{ org_logo_url }}" alt="{{ org_name }}"\n'
        '                       width="110" style="max-width:110px; height:auto; display:block;">\n'
        '                </td>\n'
        '                {% endif %}\n'
        '                <td valign="top" style="color:#6b7280; font-size:12px; line-height:1.6;">\n'
        '                  {% if org_name %}<strong style="color:#374151;">{{ org_name }}</strong><br>{% endif %}\n'
        '                  {% if org_address %}{{ org_address|linebreaksbr }}<br>{% endif %}\n'
        '                  {% if org_phone %}Tel: {{ org_phone }}<br>{% endif %}\n'
        '                  {% if org_email %}Email: <a href="mailto:{{ org_email }}" style="color:#1f4e79;">{{ org_email }}</a><br>{% endif %}\n'
        '                  {% if org_website %}<a href="{{ org_website }}" style="color:#1f4e79;">{{ org_website }}</a><br>{% endif %}\n'
        '                  {% if org_vat %}P.IVA {{ org_vat }}{% if org_rea %} · REA {{ org_rea }}{% endif %}{% elif org_rea %}REA {{ org_rea }}{% endif %}\n'
        '                </td>\n'
        '              </tr>\n'
        '            </table>\n'
        '          </td>\n'
        '        </tr>\n'
    )
    new_base, n = pattern.subn(new_footer, base_src, count=1)
    if n != 1:
        fail("Non riesco a isolare il blocco footer esistente nel template base.")
    shutil.copy2(BASE, str(BASE) + SUFFIX)
    BASE.write_text(new_base, encoding="utf-8")
    print(f"[OK] email_base.html aggiornato (backup: email_base.html{SUFFIX})")

print("\n=== CODICE APPLICATO. ===")
print("Manca solo la migrazione DB:")
print("    python manage.py makemigrations core")
print("    python manage.py migrate core")

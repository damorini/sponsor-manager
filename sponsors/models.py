"""
Modelli dell'app Sponsors.

Sponsor è l'anagrafica azienda (persiste tra eventi).
Contact sono le persone dentro un'azienda sponsor.
"""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import SoftDeleteModel, TimeStampedModel


class ContactRole(models.TextChoices):
    """
    Ruoli di un contatto. Memorizzati come array per supportare
    ruoli multipli (la stessa persona può essere firmatario E marketing).
    """
    SIGNER = 'signer', 'Firmatario'
    MARKETING = 'marketing', 'Marketing'
    FINANCE = 'finance', 'Amministrazione'
    OPERATIONAL = 'operational', 'Operativo'
    CC = 'cc', 'CC'
    EDUCATIONAL = 'educational', 'Educational manager'


class Sponsor(SoftDeleteModel):
    """
    Anagrafica azienda sponsor. Soft delete per preservare lo storico contratti.
    """
    legal_name = models.CharField(
        max_length=255,
        verbose_name="Ragione sociale",
    )
    display_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Nome commerciale",
        help_text="Nome breve, es. 'MedNova' invece di 'MedNova Italia S.r.l.'",
    )

    # Dati fiscali
    vat_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Partita IVA",
        db_index=True,
    )
    tax_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Codice fiscale",
    )
    sdi_code = models.CharField(
        max_length=7,
        blank=True,
        verbose_name="Codice destinatario SDI",
        help_text="Per fatturazione elettronica",
    )
    pec_email = models.EmailField(
        blank=True,
        verbose_name="PEC",
    )

    # Indirizzo sede legale
    address_street = models.CharField(max_length=255, blank=True, verbose_name="Indirizzo")
    address_city = models.CharField(max_length=100, blank=True, verbose_name="Città")
    address_zip = models.CharField(max_length=10, blank=True, verbose_name="CAP")
    address_province = models.CharField(max_length=2, blank=True, verbose_name="Provincia")
    address_country = models.CharField(
        max_length=2,
        default='IT',
        verbose_name="Paese",
        help_text="Codice ISO 3166-1 alpha-2 (es. IT, FR, DE)",
    )


    # Dati Registro Imprese (per contratti)
    rea_city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Città REA",
        help_text="Città del Registro Imprese (es. 'Bologna')",
    )
    rea_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Numero REA",
        help_text="Es. 'BO252016'",
    )
    business_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Descrizione attività",
        help_text="Es. 'prodotti farmaceutici per uso umano' (usato nei contratti)",
    )

    industry = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Settore",
        help_text="Es. pharma, medtech, diagnostics",
    )
    website = models.URLField(blank=True, verbose_name="Sito web")
    logo_file = models.ImageField(
        upload_to='sponsor_logos/',
        blank=True,
        null=True,
        verbose_name="Logo (file caricato)",
        help_text="Immagine caricata dal cliente; ha priorita' sull'URL.",
    )
    logo_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL logo",
        help_text="URL su S3/storage del logo aziendale",
    )

    notes = models.TextField(blank=True, verbose_name="Note")

    portal_message = models.TextField(
        blank=True,
        default='',
        verbose_name="Messaggio in evidenza (portale)",
        help_text="Mostrato a questo sponsor nella home del portale.",
    )

    class Meta:
        verbose_name = "Sponsor"
        verbose_name_plural = "Sponsor"
        ordering = ['legal_name']
        indexes = [
            models.Index(fields=['legal_name']),
        ]

    def __str__(self):
        return self.display_name or self.legal_name

    @property
    def primary_contact(self):
        """Restituisce il contatto principale, se esiste."""
        return self.contacts.filter(is_primary=True).first()

    def get_contacts_with_role(self, role):
        """Restituisce i contatti con un ruolo specifico."""
        return self.contacts.filter(roles__contains=[role])

    # Aliases "billing_*" per compatibilità con i template contratto.
    # I dati reali stanno nei campi address_*; queste property li espongono
    # con i nomi attesi dai template Jinja docxtpl.
    @property
    def billing_street(self):
        return self.address_street

    @property
    def billing_street_number(self):
        return ''  # già incluso in address_street nel modello

    @property
    def billing_city(self):
        return self.address_city

    @property
    def billing_zip(self):
        return self.address_zip

    @property
    def billing_province(self):
        return self.address_province

    @property
    def billing_full_address(self):
        """Indirizzo formattato per i template contratto."""
        parts = []
        if self.address_street:
            parts.append(self.address_street)
        city_zip = f"{self.address_zip} {self.address_city}".strip()
        if city_zip:
            parts.append(city_zip)
        if self.address_province:
            parts.append(f"({self.address_province})")
        return ", ".join(parts) if parts else ""

    @property
    def fiscal_data_dict(self):
        """
        Dizionario con tutti i dati fiscali, utile per snapshot in
        invoice_export e per export CSV verso sistemi esterni.
        """
        return {
            'legal_name': self.legal_name,
            'vat_number': self.vat_number,
            'tax_code': self.tax_code,
            'sdi_code': self.sdi_code,
            'pec_email': self.pec_email,
            'address_street': self.address_street,
            'address_city': self.address_city,
            'address_zip': self.address_zip,
            'address_province': self.address_province,
            'address_country': self.address_country,
        }


class Contact(SoftDeleteModel):
    """
    Persona di contatto presso uno sponsor. Un'azienda ha tipicamente
    più contatti con ruoli diversi.
    """
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name='contacts',
        verbose_name="Sponsor",
    )

    full_name = models.CharField(max_length=255, verbose_name="Nome completo")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=50, blank=True, verbose_name="Telefono")
    job_title = models.CharField(max_length=100, blank=True, verbose_name="Ruolo aziendale")

    # Ruoli funzionali nel sistema (per smistare comunicazioni)
    roles = ArrayField(
        models.CharField(max_length=20, choices=ContactRole.choices),
        default=list,
        blank=True,
        verbose_name="Ruoli funzionali",
        help_text="Determina chi riceve quali comunicazioni",
    )

    is_primary = models.BooleanField(
        default=False,
        verbose_name="Contatto principale",
    )
    marketing_consent = models.BooleanField(
        default=False,
        verbose_name="Consenso marketing",
        help_text="Per newsletter promozionali oltre alle comunicazioni transazionali",
    )

    # Lingua preferita per email e portale
    preferred_language = models.CharField(
        max_length=2,
        default='it',
        verbose_name="Lingua preferita",
        help_text="Usata per email automatiche e UI portale",
    )

    # Accesso al portale sponsor
    has_portal_access = models.BooleanField(
        default=False,
        verbose_name="Accesso portale",
        help_text="Se True, può autenticarsi nel portale sponsor self-service",
    )
    portal_user = models.OneToOneField(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contact_profile',
        verbose_name="Utente portale collegato",
        help_text="Account User per login al portale (se has_portal_access=True)",
    )

    notes = models.TextField(blank=True, verbose_name="Note")

    # ========================================================================
    # Dati per ruolo "Firmatario" (legale rappresentante)
    # Compilati solo se is_signer=True. Usati nei contratti.
    # ========================================================================
    is_signer = models.BooleanField(
        default=False,
        verbose_name="È il legale rappresentante firmatario?",
        help_text="Se True, può firmare i contratti per conto dello sponsor",
    )
    signer_tax_code = models.CharField(
        max_length=16,
        blank=True,
        verbose_name="Codice Fiscale (persona fisica)",
        help_text="Solo se is_signer=True. Es. RSSMRA75C15H501Z",
    )
    birth_date = models.DateField(null=True, blank=True, verbose_name="Data di nascita")
    birth_place = models.CharField(max_length=100, blank=True, verbose_name="Luogo di nascita")
    birth_province = models.CharField(max_length=2, blank=True, verbose_name="Provincia nascita")
    residence_street = models.CharField(max_length=255, blank=True, verbose_name="Via residenza")
    residence_street_number = models.CharField(max_length=10, blank=True, verbose_name="Civico residenza")
    residence_city = models.CharField(max_length=100, blank=True, verbose_name="Città residenza")
    residence_zip = models.CharField(max_length=10, blank=True, verbose_name="CAP residenza")
    residence_province = models.CharField(max_length=2, blank=True, verbose_name="Provincia residenza")

    ID_DOCUMENT_TYPES = [
        ('CI', "Carta d'Identità"),
        ('PA', "Passaporto"),
        ('PG', "Patente di Guida"),
    ]
    id_document_type = models.CharField(
        max_length=2, choices=ID_DOCUMENT_TYPES,
        blank=True, default='CI', verbose_name="Tipo documento",
    )
    id_document_number = models.CharField(
        max_length=20, blank=True, verbose_name="Numero documento",
    )

    class Meta:
        verbose_name = "Contatto"
        verbose_name_plural = "Contatti"
        ordering = ['sponsor', '-is_primary', 'full_name']
        indexes = [
            models.Index(fields=['email']),
            # Indice GIN per ricerca veloce per ruolo
            models.Index(fields=['roles'], name='idx_contact_roles_gin'),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.sponsor.legal_name})"

    def has_role(self, role):
        return role in (self.roles or [])

    @property
    def tax_code(self):
        """Alias per signer_tax_code (usato nei template contratto)."""
        return self.signer_tax_code

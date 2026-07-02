"""
Modelli dell'app Catalog.

Service è il listino dei servizi vendibili (workshop, hostess, spazi ADV...).
DeadlineTemplate definisce le scadenze automatiche generate quando un servizio
viene venduto.

Multilingua: name e description sono JSONField. Vedi TranslatableMixin.
Ecommerce: is_self_purchasable + self_purchase_cutoff_days controllano quali
servizi sono acquistabili nel portale e fino a quando.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from core.translatable import TranslatableMixin
from events.models import Event


class PricingMode(models.TextChoices):
    FIXED = 'fixed', 'Prezzo fisso'
    QUANTITY = 'quantity', 'Per quantità'
    TIERED = 'tiered', 'Scaglioni'


class Service(TranslatableMixin, TimeStampedModel):
    """
    Servizio vendibile a sponsor.
    
    Pricing modes:
    - FIXED: prezzo unico, una sola unità per contratto
    - QUANTITY: prezzo × quantità
    - TIERED: scaglioni (es. 1-10 = 50€, 11-50 = 40€, 51+ = 30€)
    
    Ecommerce:
    - is_self_purchasable: appare nel portale come acquistabile
    - self_purchase_cutoff_days: giorni minimi prima dell'evento per comprare
      (NULL = sempre, 0 = fino al giorno stesso, 7 = chiude 7gg prima)
    """
    TRANSLATABLE_FIELDS = ['name', 'description']

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='services',
        verbose_name="Evento",
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Codice",
        help_text="Es. WORKSHOP_30MIN, HOSTESS_DAY",
    )

    # Multilingua
    name = models.JSONField(
        verbose_name="Nome (multilingua)",
        help_text='Formato: {"it": "...", "en": "..."}',
    )
    description = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Descrizione (multilingua)",
    )

    image = models.FileField(
        upload_to='services/images/',
        null=True,
        blank=True,
        verbose_name="Immagine",
        help_text="Foto dell'articolo mostrata nel catalogo.",
    )

    category = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Categoria",
    )

    # Categoria contabile per raggruppamento nell'allegato 2 ECM
    ACCOUNTING_CATEGORIES = [
        ('viaggio_partecipanti', 'Viaggio/ospitalità partecipanti'),
        ('viaggio_relatori', 'Viaggio/ospitalità relatori'),
        ('affitto_sala', 'Affitto sala'),
        ('stand', 'Spazi espositivi/stand'),
        ('coffee_break', 'Coffee break/colazioni'),
        ('scheda_tecnica', 'Scheda tecnica/cartella'),
        ('quota_iscrizione', "Quota d'iscrizione"),
        ('altro', 'Altre spese'),
    ]
    accounting_category = models.CharField(
        max_length=30,
        choices=ACCOUNTING_CATEGORIES,
        default='altro',
        verbose_name="Categoria contabile",
        help_text="Per raggruppamento nell'allegato 2 dei contratti ECM",
    )

    pricing_mode = models.CharField(
        max_length=20,
        choices=PricingMode.choices,
        default=PricingMode.FIXED,
        verbose_name="Modalità pricing",
    )
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Prezzo base",
    )
    pricing_tiers = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Scaglioni",
    )

    is_active = models.BooleanField(default=True, verbose_name="Attivo")
    max_quantity = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Quantità massima",
    )
    total_available = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Quantità totale disponibile",
        help_text="Quanti pezzi esistono in totale (es. 1 per uno stand unico). Vuoto = illimitato.",
    )

    triggers_deadlines = models.BooleanField(
        default=False,
        verbose_name="Genera scadenze",
    )

    included_services = models.ManyToManyField(
        'self', symmetrical=False, blank=True,
        through='ServiceInclusion',
        through_fields=('parent', 'child'),
        related_name='included_in',
        verbose_name="Servizi inclusi (accessori)",
        help_text="Servizi aggiunti automaticamente a € 0 quando questo servizio viene venduto. Le loro scadenze materiali si generano alla firma. La quantita' inclusa si imposta nella sezione 'Servizi inclusi' in fondo a questa pagina.",
    )

    # Ecommerce
    is_self_purchasable = models.BooleanField(
        default=False,
        verbose_name="Acquistabile self-service",
        help_text="Se True, appare nel portale ecommerce per gli sponsor",
    )
    self_purchase_cutoff_days = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Cutoff acquisto (gg prima evento)",
        help_text=(
            "Giorni minimi prima dell'evento per poter ancora acquistare. "
            "NULL = nessun cutoff. 0 = acquistabile il giorno stesso. "
            "Es. 14 = chiude 14 giorni prima dell'evento."
        ),
    )

    vat_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('22.00'),
        verbose_name="Aliquota IVA (%)",
    )
    vat_exemption_article = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Articolo esenzione IVA",
    )

    display_order = models.IntegerField(
        default=0,
        verbose_name="Ordine visualizzazione",
    )
    catalog_source = models.ForeignKey(
        'catalog.CatalogService',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='instances',
        verbose_name="Origine (catalogo)",
        help_text="Se valorizzato, il servizio nasce da una voce del catalogo.",
    )

    class Meta:
        verbose_name = "Servizio"
        verbose_name_plural = "Servizi"
        ordering = ['event', 'display_order']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'code'],
                name='service_code_unique_per_event',
            ),
        ]
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_self_purchasable', 'is_active']),
        ]

    def __str__(self):
        # Backoffice italiano-first: il menu/etichette admin mostrano sempre il
        # nome italiano (fallback alle altre lingue se l'IT manca).
        return f"{self.translated('name', 'it')} ({self.event.slug})"

    def get_name(self, language=None):
        return self.translated('name', language)

    def get_description(self, language=None):
        return self.translated('description', language)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._neutralizza_nome_immagine()
        self._ottimizza_immagine()

    def _neutralizza_nome_immagine(self):
        """Rinomina l'immagine con un nome neutro (img_<uuid>.<ext>).
        Evita che ad-blocker/estensioni blocchino i file con parole come 'banner'
        o 'ad' (net::ERR_BLOCKED_BY_CLIENT) e rimuove i suffissi anti-collisione."""
        if not self.image:
            return
        try:
            import os as _os, re as _re, uuid as _uuid
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            name = self.image.name
            base = _os.path.basename(name)
            if _re.match(r'^img_[0-9a-f]{32}\.', base):
                return  # gia' neutro
            ext = _os.path.splitext(base)[1].lower() or '.img'
            new_rel = f"services/images/img_{_uuid.uuid4().hex}{ext}"
            with default_storage.open(name, 'rb') as _f:
                data = _f.read()
            saved = default_storage.save(new_rel, ContentFile(data))
            if saved != name and default_storage.exists(name):
                default_storage.delete(name)
            type(self).objects.filter(pk=self.pk).update(image=saved)
            self.image.name = saved
        except Exception:
            pass

    def _ottimizza_immagine(self, max_lato=1000, quality=82):
        """Riduce l'immagine se il lato piu' lungo supera max_lato.
        Idempotente: se e' gia' piccola non fa nulla. Non blocca mai il salvataggio."""
        if not self.image:
            return
        try:
            import io, os as _os
            from PIL import Image
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage
            self.image.open()
            img = Image.open(self.image)
            fmt = (img.format or 'JPEG').upper()
            if max(img.size) <= max_lato:
                self.image.close()
                return
            img.thumbnail((max_lato, max_lato), Image.LANCZOS)
            opts = {'optimize': True}
            if fmt in ('JPEG', 'JPG'):
                img = img.convert('RGB'); opts['quality'] = quality; out = 'JPEG'
            elif fmt == 'WEBP':
                opts['quality'] = quality; out = 'WEBP'
            elif fmt == 'PNG':
                out = 'PNG'
            else:
                out = fmt
            buf = io.BytesIO()
            img.save(buf, format=out, **opts)
            name = self.image.name
            base = _os.path.basename(name)
            self.image.close()
            if default_storage.exists(name):
                default_storage.delete(name)
            self.image.save(base, ContentFile(buf.getvalue()), save=False)
            type(self).objects.filter(pk=self.pk).update(image=self.image.name)
        except Exception:
            pass

    @property
    def DEFAULT_LANGUAGE(self):
        """Override del mixin: usa la default_language dell'evento."""
        return self.event.default_language if self.event_id else 'it'

    def quantity_committed(self, exclude_contract_id=None):
        """Somma delle quantita' impegnate in contratti NON cancellati."""
        from django.db.models import Sum
        qs = self.contract_lines.exclude(contract__status='cancelled')
        if exclude_contract_id is not None:
            qs = qs.exclude(contract_id=exclude_contract_id)
        return qs.aggregate(tot=Sum('quantity'))['tot'] or 0

    def quantity_available(self, exclude_contract_id=None):
        """Pezzi ancora disponibili. None = illimitato."""
        if self.total_available is None:
            return None
        return self.total_available - self.quantity_committed(exclude_contract_id)

    @property
    def is_sold_out(self):
        avail = self.quantity_available()
        return avail is not None and avail <= 0

    def calculate_price(self, quantity=1):
        """Calcola il prezzo totale per una quantità."""
        quantity = int(quantity)
        if quantity < 1:
            return Decimal('0.00')

        if self.pricing_mode == PricingMode.FIXED:
            return self.base_price

        if self.pricing_mode == PricingMode.QUANTITY:
            return self.base_price * quantity

        if self.pricing_mode == PricingMode.TIERED:
            return self._calculate_tiered_price(quantity)

        return Decimal('0.00')

    def _calculate_tiered_price(self, quantity):
        if not self.pricing_tiers:
            return self.base_price * quantity

        for tier in self.pricing_tiers:
            tier_min = tier.get('min', 1)
            tier_max = tier.get('max')
            if quantity >= tier_min and (tier_max is None or quantity <= tier_max):
                unit_price = Decimal(str(tier['unit_price']))
                return unit_price * quantity

        return self.base_price * quantity

    def is_purchasable_today(self, reference_date=None):
        """
        True se questo servizio può essere comprato oggi (rispettando cutoff).
        Per ecommerce: usato per filtrare cosa mostrare nel portale.
        """
        if not self.is_self_purchasable or not self.is_active:
            return False

        if self.self_purchase_cutoff_days is None:
            return True  # nessun cutoff

        today = reference_date or date.today()
        days_until_event = (self.event.start_date - today).days
        return days_until_event >= self.self_purchase_cutoff_days


class ServiceInclusion(models.Model):
    """Legame 'servizio principale -> servizio incluso' con quantita'.
    Modello intermedio del M2M Service.included_services: permette di dire
    quante unita' di un accessorio sono incluse in un servizio padre."""
    parent = models.ForeignKey(
        'catalog.Service',
        on_delete=models.CASCADE,
        related_name='inclusions',
        verbose_name="Servizio principale",
    )
    child = models.ForeignKey(
        'catalog.Service',
        on_delete=models.CASCADE,
        related_name='inclusion_links',
        verbose_name="Servizio incluso",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Quantita' inclusa",
        help_text="Quante unita' di questo accessorio vengono incluse.",
    )

    class Meta:
        verbose_name = "Servizio incluso"
        verbose_name_plural = "Servizi inclusi"
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'child'],
                name='serviceinclusion_unique_parent_child',
            ),
        ]

    def __str__(self):
        return "%s x%s" % (self.child_id, self.quantity)


class ServiceVariant(TimeStampedModel):
    """Variante di un Service (es. colore/misura) con prezzo e scorte proprie."""
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='variants',
        verbose_name="Servizio",
    )
    label = models.CharField(
        max_length=120, verbose_name="Variante",
        help_text="Es. Rosso, Taglia L, ...",
    )
    label_en = models.CharField(
        max_length=120, blank=True, verbose_name="Etichetta (EN)",
        help_text="Traduzione inglese. Vuoto = usa l'italiano.",
    )
    code = models.CharField(max_length=50, blank=True, verbose_name="Codice")
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Prezzo variante",
        help_text="Prezzo di questa variante (sostituisce il prezzo base del servizio).",
    )
    total_available = models.IntegerField(
        null=True, blank=True, verbose_name="Scorte",
        help_text="Quantita' disponibile di questa variante. Vuoto = illimitate.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Attiva")
    display_order = models.IntegerField(default=0, verbose_name="Ordine")

    class Meta:
        verbose_name = "Variante servizio"
        verbose_name_plural = "Varianti servizio"
        ordering = ['display_order', 'label']

    def __str__(self):
        # Mostra "variante — servizio" per distinguerla nelle tendine admin.
        try:
            return f"{self.label} — {self.service.translated('name', 'it')}"
        except Exception:
            return self.label

    def label_display(self):
        """Etichetta nella lingua attiva del portale (fallback: italiano)."""
        from django.utils.translation import get_language
        if (get_language() or '').startswith('en') and self.label_en:
            return self.label_en
        return self.label

    def quantity_committed(self, exclude_contract_id=None):
        from django.db.models import Sum
        qs = self.variant_lines.exclude(contract__status='cancelled')
        if exclude_contract_id is not None:
            qs = qs.exclude(contract_id=exclude_contract_id)
        return qs.aggregate(tot=Sum('quantity'))['tot'] or 0

    def quantity_available(self, exclude_contract_id=None):
        if self.total_available is None:
            return None
        return self.total_available - self.quantity_committed(exclude_contract_id)

    def is_sold_out(self):
        avail = self.quantity_available()
        return avail is not None and avail <= 0


class SubmissionKind(models.TextChoices):
    FILE = 'file', 'Solo file'
    CONTENT = 'content', 'Solo campi da compilare'
    BOTH = 'both', 'File + campi da compilare'
    PHYSICAL = 'physical', 'Materiale fisico (spedizione postale)'


class FieldType(models.TextChoices):
    SHORT_TEXT = 'short_text', 'Testo breve'
    LONG_TEXT = 'long_text', 'Testo lungo'


class DeadlineTemplate(TimeStampedModel):
    """
    Template di scadenza associato a un servizio.
    Quando si vende un servizio con triggers_deadlines=True, viene generata
    una Deadline concreta per ogni DeadlineTemplate associato.
    """
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='deadline_templates',
        verbose_name="Servizio",
    )
    deadline_type = models.CharField(
        max_length=50,
        verbose_name="Tipo scadenza",
    )
    title = models.CharField(max_length=255, verbose_name="Titolo")
    description = models.TextField(blank=True, verbose_name="Descrizione")

    submission_kind = models.CharField(
        max_length=20,
        choices=SubmissionKind.choices,
        default=SubmissionKind.FILE,
        verbose_name="Cosa deve fornire il cliente",
        help_text="File, campi da compilare, oppure entrambi.",
    )

    shipping_instructions = models.TextField(
        blank=True,
        verbose_name="Istruzioni di spedizione",
        help_text="Visibile al cliente nel portale quando il tipo è 'Materiale fisico'. "
                  "Indica indirizzo di spedizione, imballo, riferimento da riportare, ecc.",
    )

    days_before_event = models.IntegerField(
        verbose_name="Giorni prima dell'evento",
        help_text="Quando cade la scadenza: tot giorni prima dell'inizio "
                  "evento. Es. 30 = la scadenza è 30 giorni prima dell'evento.",
    )

    notify_roles = ArrayField(
        models.CharField(max_length=20),
        default=list,
        verbose_name="Ruoli da notificare",
    )

    reminder_days_before = ArrayField(
        models.IntegerField(),
        default=list,
        blank=True,
        verbose_name="Reminder a (giorni prima della scadenza)",
        help_text="Quanti giorni PRIMA DELLA SCADENZA inviare i promemoria. "
                  "Puoi metterne più di uno separati da virgola, es. 15, 7, 3 "
                  "(tre promemoria, a 15-7-3 giorni dalla scadenza). "
                  "Vuoto = nessun reminder automatico.",
    )

    # File "modello" che il cliente puo' scaricare per preparare cio' che deve
    # inviare (es. un template grafico nella misura giusta, o un Excel con le
    # colonne da compilare). Opzionale.
    client_template_file = models.FileField(
        upload_to='deadline_templates/',
        blank=True, null=True,
        verbose_name="Modello da far scaricare al cliente",
        help_text="Facoltativo. File di traccia che il cliente scarica per "
                  "preparare il materiale richiesto: es. un template grafico "
                  "alla misura giusta, oppure un Excel con le colonne/info da "
                  "compilare.",
    )

    is_active = models.BooleanField(default=True, verbose_name="Attivo")
    display_order = models.IntegerField(default=0, verbose_name="Ordine")

    class Meta:
        verbose_name = "Template scadenza"
        verbose_name_plural = "Template scadenze"
        ordering = ['service', 'display_order']

    def __str__(self):
        return f"{self.title} ({self.service.translated('name')})"


class DeadlineFieldTemplate(TimeStampedModel):
    """
    Un campo che il cliente deve compilare per soddisfare una richiesta
    (DeadlineTemplate con submission_kind 'content' o 'both').
    Editabile come riga inline nella richiesta.
    """
    deadline_template = models.ForeignKey(
        DeadlineTemplate,
        on_delete=models.CASCADE,
        related_name='content_fields',
        verbose_name="Richiesta",
    )
    label = models.CharField(max_length=255, verbose_name="Etichetta")
    key = models.SlugField(
        max_length=60, blank=True, verbose_name="Chiave",
        help_text="Lasciare vuoto: viene generata dall'etichetta.",
    )
    field_type = models.CharField(
        max_length=20,
        choices=FieldType.choices,
        default=FieldType.SHORT_TEXT,
        verbose_name="Tipo",
    )
    required = models.BooleanField(default=True, verbose_name="Obbligatorio")
    help_text = models.CharField(
        max_length=255, blank=True, verbose_name="Testo di aiuto",
    )
    display_order = models.IntegerField(default=0, verbose_name="Ordine")

    class Meta:
        verbose_name = "Campo da compilare"
        verbose_name_plural = "Campi da compilare"
        ordering = ['deadline_template', 'display_order']

    def save(self, *args, **kwargs):
        if not self.key:
            from django.utils.text import slugify
            self.key = (slugify(self.label)[:60] or 'campo').replace('-', '_')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} ({self.get_field_type_display()})"


# ============================================================
# CATALOGO SERVIZI (indipendente dall'evento)
# ============================================================
class ServiceCategory(TimeStampedModel):
    # Lista gestita di categorie, condivisa dal catalogo
    code = models.SlugField(max_length=50, unique=True, verbose_name="Codice")
    name = models.CharField(max_length=80, verbose_name="Nome categoria")
    display_order = models.IntegerField(default=0, verbose_name="Ordine")
    is_active = models.BooleanField(default=True, verbose_name="Attiva")

    class Meta:
        verbose_name = "Categoria servizio"
        verbose_name_plural = "Categorie servizio (catalogo)"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class CatalogService(TranslatableMixin, TimeStampedModel):
    # Servizio "madre": definito una volta, istanziato sugli eventi
    TRANSLATABLE_FIELDS = ['name', 'description']

    code = models.CharField(max_length=50, unique=True, verbose_name="Codice")
    name = models.JSONField(verbose_name="Nome (multilingua)", help_text='Formato: {"it": "...", "en": "..."}')
    description = models.JSONField(null=True, blank=True, verbose_name="Descrizione (multilingua)")
    image = models.FileField(upload_to='catalog/images/', null=True, blank=True, verbose_name="Immagine")
    category = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='catalog_services', verbose_name="Categoria")
    accounting_category = models.CharField(max_length=30, choices=Service.ACCOUNTING_CATEGORIES,
                                           default='altro', verbose_name="Categoria contabile")
    pricing_mode = models.CharField(max_length=20, choices=PricingMode.choices,
                                    default=PricingMode.FIXED, verbose_name="Modalità pricing")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                     verbose_name="Prezzo base (default)")
    pricing_tiers = models.JSONField(null=True, blank=True, verbose_name="Scaglioni")
    max_quantity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)],
                                       verbose_name="Quantità massima")
    triggers_deadlines = models.BooleanField(default=False, verbose_name="Genera scadenze")
    is_self_purchasable = models.BooleanField(default=False, verbose_name="Acquistabile self-service")
    self_purchase_cutoff_days = models.IntegerField(null=True, blank=True,
                                                    verbose_name="Cutoff acquisto (gg prima evento)")
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('22.00'),
                                   verbose_name="Aliquota IVA (%)")
    vat_exemption_article = models.CharField(max_length=100, blank=True, verbose_name="Articolo esenzione IVA")
    display_order = models.IntegerField(default=0, verbose_name="Ordine visualizzazione")
    is_active = models.BooleanField(default=True, verbose_name="Attivo")

    class Meta:
        verbose_name = "Servizio a catalogo"
        verbose_name_plural = "Catalogo servizi"
        ordering = ['display_order', 'code']

    def get_name(self, language=None):
        return self.translated('name', language)

    def __str__(self):
        try:
            return f"{self.translated('name')} [{self.code}]"
        except Exception:
            return self.code


class CatalogServiceVariant(TimeStampedModel):
    catalog_service = models.ForeignKey(CatalogService, on_delete=models.CASCADE,
                                        related_name='variants', verbose_name="Servizio a catalogo")
    label = models.CharField(max_length=120, verbose_name="Variante")
    label_en = models.CharField(max_length=120, blank=True, verbose_name="Etichetta (EN)")
    code = models.CharField(max_length=50, blank=True, verbose_name="Codice")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prezzo variante")
    is_active = models.BooleanField(default=True, verbose_name="Attiva")
    display_order = models.IntegerField(default=0, verbose_name="Ordine")

    class Meta:
        verbose_name = "Variante (catalogo)"
        verbose_name_plural = "Varianti (catalogo)"
        ordering = ['display_order', 'label']

    def __str__(self):
        return self.label

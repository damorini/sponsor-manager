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

    triggers_deadlines = models.BooleanField(
        default=False,
        verbose_name="Genera scadenze",
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
        return f"{self.translated('name')} ({self.event.slug})"

    @property
    def DEFAULT_LANGUAGE(self):
        """Override del mixin: usa la default_language dell'evento."""
        return self.event.default_language if self.event_id else 'it'

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

    days_before_event = models.IntegerField(
        verbose_name="Giorni prima dell'evento",
    )

    notify_roles = ArrayField(
        models.CharField(max_length=20),
        default=list,
        verbose_name="Ruoli da notificare",
    )

    reminder_days_before = ArrayField(
        models.IntegerField(),
        default=list,
        verbose_name="Reminder a (giorni prima)",
    )

    is_active = models.BooleanField(default=True, verbose_name="Attivo")
    display_order = models.IntegerField(default=0, verbose_name="Ordine")

    class Meta:
        verbose_name = "Template scadenza"
        verbose_name_plural = "Template scadenze"
        ordering = ['service', 'display_order']

    def __str__(self):
        return f"{self.title} ({self.service.translated('name')})"

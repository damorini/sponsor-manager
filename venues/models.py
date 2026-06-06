"""
Modelli dell'app Venues (spazi espositivi).

StandBlock raggruppa stand venduti come unico spazio.
Stand sono le postazioni espositive fisiche.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import TimeStampedModel
from core.translatable import TranslatableMixin
from events.models import Event


class StandStatus(models.TextChoices):
    AVAILABLE = 'available', 'Disponibile'
    RESERVED = 'reserved', 'Riservato'
    ASSIGNED = 'assigned', 'Assegnato'
    UNAVAILABLE = 'unavailable', 'Non disponibile'


class StandBlock(TranslatableMixin, TimeStampedModel):
    """
    Blocco logico di stand venduti come unico spazio.

    Esempi: "Blocco B12-B13" (due stand adiacenti), "Area Centrale" (4 stand
    a isola). Un contratto può essere assegnato al blocco intero, e tutti gli
    stand del blocco passano automaticamente a 'assigned' (logica gestita in
    Contract.mark_as_signed()).
    """
    TRANSLATABLE_FIELDS = ['quote_description']

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='stand_blocks',
        verbose_name="Evento",
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Codice blocco",
        help_text="Es. 'BLOCCO-B12-B13', 'ISLAND-CENTER'",
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Nome commerciale",
        help_text="Es. 'Area Premium Centrale'",
    )
    block_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Tipo blocco",
        help_text="Es. double_corner, island_combined, linear_pair",
    )

    total_area_sqm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Area totale (mq)",
    )
    block_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prezzo blocco",
        help_text="Prezzo del blocco venduto insieme (può differire dalla somma stand)",
    )

    status = models.CharField(
        max_length=20,
        choices=StandStatus.choices,
        default=StandStatus.AVAILABLE,
        verbose_name="Stato",
    )

    quote_description = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Descrizione per preventivo (IT/EN)",
        help_text="Descrizione mostrata SOLO nel preventivo "
                  "(es. 'stand rettangolare con 1 lato libero, senza arredo...'). "
                  "Non compare nel contratto. L'inglese si compila da solo al salvataggio.",
    )

    notes = models.TextField(blank=True, verbose_name="Note")

    class Meta:
        verbose_name = "Blocco stand"
        verbose_name_plural = "Blocchi stand"
        ordering = ['event', 'code']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'code'],
                name='stand_block_code_unique_per_event',
            ),
        ]
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.name or self.code

    @property
    def stands_count(self):
        return self.stands.count()

    @property
    def stands_price_sum(self):
        """Somma dei prezzi base degli stand che compongono il blocco."""
        return self.stands.aggregate(t=Sum('base_price'))['t'] or Decimal('0.00')

    @property
    def effective_price(self):
        """Prezzo da usare per il blocco:
        - se 'block_price' è impostato a mano, vale quello;
        - altrimenti la somma dei prezzi degli stand inclusi.
        """
        if self.block_price is not None:
            return self.block_price
        return self.stands_price_sum

    @property
    def price_is_computed(self):
        """True se il prezzo deriva dalla somma stand (block_price non impostato)."""
        return self.block_price is None

    def update_status_from_contract(self):
        """
        Aggiorna lo stato del blocco e dei suoi stand in base ai contratti
        attivi che lo riferiscono. Chiamato dopo cambi di stato dei contratti.
        """
        from contracts.models import Contract, ContractStatus

        active_contract = self.contracts.filter(
            status__in=[
                ContractStatus.SIGNED,
                ContractStatus.ACTIVE,
                ContractStatus.COMPLETED,
            ],
            deleted_at__isnull=True,
        ).first()

        if active_contract:
            new_status = StandStatus.ASSIGNED
        else:
            # Riservato se: contratto SENT, OPPURE contratto in DRAFT con opzione
            # ancora attiva (option_until >= oggi). Opzione scaduta -> non conta.
            _oggi = timezone.now().date()
            reserved_contract = self.contracts.filter(
                deleted_at__isnull=True,
            ).filter(
                Q(status=ContractStatus.SENT)
                | Q(status=ContractStatus.DRAFT,
                    option_until__isnull=False,
                    option_until__gte=_oggi)
            ).first()
            new_status = StandStatus.RESERVED if reserved_contract else StandStatus.AVAILABLE

        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])

        # Cascata su tutti gli stand del blocco
        self.stands.update(status=new_status)


class Stand(TranslatableMixin, TimeStampedModel):
    """
    Postazione espositiva fisica. Appartiene a un evento e facoltativamente
    a un blocco.
    """
    TRANSLATABLE_FIELDS = ['quote_description']

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='stands',
        verbose_name="Evento",
    )
    stand_block = models.ForeignKey(
        StandBlock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stands',
        verbose_name="Blocco",
        help_text="Se appartiene a un blocco di stand venduti insieme",
    )

    code = models.CharField(
        max_length=20,
        verbose_name="Codice",
        help_text="Es. 'B12'",
    )

    # Dimensioni
    width_meters = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Larghezza (m)",
    )
    depth_meters = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Profondità (m)",
    )
    # area_sqm è una colonna GENERATED nel DB, in Django la calcoliamo come property
    # (Django non supporta nativamente GENERATED ALWAYS AS, va aggiunto via migration custom)

    stand_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Tipologia",
        help_text="Es. corner_premium, linear, island, custom",
    )

    # Dotazioni
    has_power = models.BooleanField(default=False, verbose_name="Allaccio elettrico")
    power_kw = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Potenza (kW)",
    )
    has_water = models.BooleanField(default=False, verbose_name="Allaccio idrico")
    has_internet = models.BooleanField(default=False, verbose_name="Internet")
    max_height_meters = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Altezza max (m)",
    )

    # Posizione su planimetria
    map_x = models.IntegerField(null=True, blank=True, verbose_name="Coord. X")
    map_y = models.IntegerField(null=True, blank=True, verbose_name="Coord. Y")

    status = models.CharField(
        max_length=20,
        choices=StandStatus.choices,
        default=StandStatus.AVAILABLE,
        verbose_name="Stato",
    )

    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prezzo base",
    )

    quote_description = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Descrizione per preventivo (IT/EN)",
        help_text="Descrizione mostrata SOLO nel preventivo "
                  "(es. 'stand rettangolare con 1 lato libero, senza arredo...'). "
                  "Non compare nel contratto. L'inglese si compila da solo al salvataggio.",
    )

    notes = models.TextField(blank=True, verbose_name="Note")

    class Meta:
        verbose_name = "Stand"
        verbose_name_plural = "Stand"
        ordering = ['event', 'code']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'code'],
                name='stand_code_unique_per_event',
            ),
        ]
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        if self.event_id:
            return f"{self.code} ({self.event.get_name()})"
        return self.code

    @property
    def area_sqm(self):
        """Area calcolata. Se vuoi avere campo DB, usa una migration custom."""
        if self.width_meters and self.depth_meters:
            return self.width_meters * self.depth_meters
        return None

    @property
    def is_in_block(self):
        return self.stand_block_id is not None

    def update_status_from_contract(self):
        """
        Aggiorna lo stato dello stand in base ai contratti attivi.
        Se appartiene a un blocco, l'aggiornamento viene fatto a livello blocco.
        """
        if self.is_in_block:
            self.stand_block.update_status_from_contract()
            return

        from contracts.models import Contract, ContractStatus

        active_contract = self.contracts.filter(
            status__in=[
                ContractStatus.SIGNED,
                ContractStatus.ACTIVE,
                ContractStatus.COMPLETED,
            ],
            deleted_at__isnull=True,
        ).first()

        if active_contract:
            self.status = StandStatus.ASSIGNED
        else:
            # Riservato se: contratto SENT, OPPURE contratto in DRAFT con opzione
            # ancora attiva (option_until >= oggi). Opzione scaduta -> non conta.
            _oggi = timezone.now().date()
            reserved = self.contracts.filter(
                deleted_at__isnull=True,
            ).filter(
                Q(status=ContractStatus.SENT)
                | Q(status=ContractStatus.DRAFT,
                    option_until__isnull=False,
                    option_until__gte=_oggi)
            ).first()
            self.status = StandStatus.RESERVED if reserved else StandStatus.AVAILABLE

        self.save(update_fields=['status', 'updated_at'])

"""
Admin per Stand e StandBlock (spazi espositivi).

Stand inline dentro StandBlock per editare un blocco e i suoi stand insieme.
"""
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Stand, StandBlock, StandStatus


class StandInline(admin.TabularInline):
    """Stand editabili dentro la pagina del blocco."""
    model = Stand
    extra = 1
    fields = (
        'code', 'width_meters', 'depth_meters', 'stand_type',
        'has_power', 'status', 'base_price',
    )
    show_change_link = True


@admin.register(StandBlock)
class StandBlockAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name_or_dash', 'event_link', 'block_type',
        'stands_count_display', 'total_area_display',
        'block_price_display', 'status_badge',
    )
    list_filter = ('status', 'block_type', 'event')
    search_fields = ('code', 'name', 'event__name', 'event__slug')
    list_select_related = ('event',)
    autocomplete_fields = ['event']
    readonly_fields = ('created_at', 'updated_at')
    inlines = [StandInline]

    fieldsets = (
        (None, {
            'fields': ('event', 'code', 'name', 'block_type', 'status'),
        }),
        ('Dimensioni e prezzo', {
            'fields': ('total_area_sqm', 'block_price'),
        }),
        ('Note', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Nome')
    def name_or_dash(self, obj):
        return obj.name or '—'

    @admin.display(description='Evento', ordering='event__slug')
    def event_link(self, obj):
        url = reverse('admin:events_event_change', args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event.slug)

    @admin.display(description='Stand')
    def stands_count_display(self, obj):
        return obj.stands_count

    @admin.display(description='Area totale')
    def total_area_display(self, obj):
        if obj.total_area_sqm:
            return f"{obj.total_area_sqm} m²"
        return '—'

    @admin.display(description='Prezzo')
    def block_price_display(self, obj):
        if obj.block_price is not None:
            return f"€ {obj.block_price:,.2f}"
        return '—'

    @admin.display(description='Stato')
    def status_badge(self, obj):
        return _stand_status_badge(obj.status, obj.get_status_display())


@admin.register(Stand)
class StandAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'event_link', 'block_link', 'dimensions_display',
        'stand_type', 'amenities_display', 'status_badge', 'base_price_display',
    )
    list_filter = ('status', 'stand_type', 'has_power', 'has_water', 'event')
    search_fields = ('code', 'event__name', 'event__slug', 'stand_block__code')
    list_select_related = ('event', 'stand_block')
    autocomplete_fields = ['event', 'stand_block']
    readonly_fields = ('created_at', 'updated_at', 'area_sqm_display')
    ordering = ('event', 'code')

    fieldsets = (
        (None, {
            'fields': ('event', 'stand_block', 'code', 'stand_type', 'status'),
        }),
        ('Dimensioni', {
            'fields': (
                ('width_meters', 'depth_meters'),
                'area_sqm_display',
                'max_height_meters',
            ),
        }),
        ('Dotazioni', {
            'fields': (
                ('has_power', 'power_kw'),
                'has_water',
                'has_internet',
            ),
        }),
        ('Posizionamento', {
            'fields': (('map_x', 'map_y'),),
            'classes': ('collapse',),
        }),
        ('Prezzo', {
            'fields': ('base_price',),
        }),
        ('Note', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Evento', ordering='event__slug')
    def event_link(self, obj):
        url = reverse('admin:events_event_change', args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event.slug)

    @admin.display(description='Blocco')
    def block_link(self, obj):
        if not obj.stand_block_id:
            return '—'
        url = reverse('admin:venues_standblock_change', args=[obj.stand_block_id])
        return format_html('<a href="{}">{}</a>', url, obj.stand_block.code)

    @admin.display(description='Dimensioni')
    def dimensions_display(self, obj):
        if obj.width_meters and obj.depth_meters:
            return f"{obj.width_meters}×{obj.depth_meters} m ({obj.area_sqm} m²)"
        return '—'

    @admin.display(description='Area')
    def area_sqm_display(self, obj):
        return f"{obj.area_sqm} m²" if obj.area_sqm else '—'

    @admin.display(description='Dotazioni')
    def amenities_display(self, obj):
        amenities = []
        if obj.has_power:
            amenities.append('⚡')
        if obj.has_water:
            amenities.append('💧')
        if obj.has_internet:
            amenities.append('🌐')
        return ' '.join(amenities) if amenities else '—'

    @admin.display(description='Stato')
    def status_badge(self, obj):
        return _stand_status_badge(obj.status, obj.get_status_display())

    @admin.display(description='Prezzo')
    def base_price_display(self, obj):
        if obj.base_price is not None:
            return f"€ {obj.base_price:,.2f}"
        return '—'


# Helper condiviso per badge stato
def _stand_status_badge(status, label):
    colors = {
        StandStatus.AVAILABLE: '#41ad7c',
        StandStatus.RESERVED: '#e6a23c',
        StandStatus.ASSIGNED: '#79aec8',
        StandStatus.UNAVAILABLE: '#999',
    }
    color = colors.get(status, '#666')
    return format_html(
        '<span style="background:{}; color:white; padding:2px 8px; '
        'border-radius:3px; font-size:0.85em;">{}</span>',
        color, label
    )

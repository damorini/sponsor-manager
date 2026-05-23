"""
Widget custom per JSONField multilingua.

Trasforma l'editor JSON grezzo in due (o più) campi affiancati, uno per
ogni lingua supportata. Validazione integrata: la lingua di default è
obbligatoria, le altre opzionali.

Uso negli admin:
    from core.admin_widgets import TranslatableJSONField
    
    class EventAdminForm(forms.ModelForm):
        name = TranslatableJSONField(languages=['it', 'en'], required_languages=['it'])
        description = TranslatableJSONField(languages=['it', 'en'], required=False)
        
        class Meta:
            model = Event
            fields = '__all__'
"""
import json

from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


class TranslatableJSONWidget(forms.MultiWidget):
    """
    Widget che renderizza un JSONField multilingua come N input affiancati,
    uno per ogni lingua. Internamente combina i valori in un dizionario
    JSON.
    """

    def __init__(self, languages=None, language_labels=None, attrs=None,
                 use_textarea=False):
        self.languages = languages or ['it', 'en']
        self.language_labels = language_labels or {
            'it': 'Italiano',
            'en': 'English',
            'fr': 'Français',
            'de': 'Deutsch',
            'es': 'Español',
        }
        self.use_textarea = use_textarea

        widget_class = forms.Textarea if use_textarea else forms.TextInput
        widget_attrs = {'class': 'vTextField'}
        if use_textarea:
            widget_attrs['rows'] = 4

        widgets = [
            widget_class(attrs={**widget_attrs, 'data-lang': lang})
            for lang in self.languages
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        """
        Da dict JSON {"it": "...", "en": "..."} a lista di valori per i widget.
        """
        if not value:
            return ['' for _ in self.languages]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return ['' for _ in self.languages]
        if not isinstance(value, dict):
            return ['' for _ in self.languages]
        return [value.get(lang, '') for lang in self.languages]

    def value_from_datadict(self, data, files, name):
        """
        Da dati del form (lista valori) a dict JSON {"it": "...", "en": "..."}.
        """
        values = [
            widget.value_from_datadict(data, files, f"{name}_{i}")
            for i, widget in enumerate(self.widgets)
        ]
        result = {
            lang: val for lang, val in zip(self.languages, values, strict=False)
            if val
        }
        return json.dumps(result, ensure_ascii=False) if result else ''

    def format_output(self, rendered_widgets):
        return mark_safe(''.join(rendered_widgets))

    class Media:
        css = {
            'all': ('admin/css/translatable_widget.css',)
        }


class TranslatableJSONField(forms.JSONField):
    """
    FormField per JSONField multilingua, da usare nei ModelForm degli admin.
    
    Args:
        languages: lista lingue supportate, es. ['it', 'en']
        required_languages: lista lingue obbligatorie. Se vuota, nessuna lingua
            è obbligatoria. Default: ['it'] (italiano sempre obbligatorio).
        use_textarea: True per textarea, False per input single-line. Default: False.
    """

    def __init__(self, languages=None, required_languages=None,
                 use_textarea=False, *args, **kwargs):
        self.languages = languages or ['it', 'en']
        self.required_languages = required_languages or ['it']
        self.use_textarea = use_textarea

        kwargs['widget'] = TranslatableJSONWidget(
            languages=self.languages,
            use_textarea=use_textarea,
        )
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if not value:
            return {} if self.required else None
        if isinstance(value, dict):
            return value
        return super().to_python(value)

    def validate(self, value):
        super().validate(value)
        if not isinstance(value, dict):
            return
        for lang in self.required_languages:
            if not value.get(lang):
                lang_label = TranslatableJSONWidget().language_labels.get(lang, lang)
                raise forms.ValidationError(
                    _("La traduzione in %(language)s è obbligatoria.") % {
                        'language': lang_label
                    }
                )

    def render_with_labels(self, name):
        """
        Helper per generare HTML con etichette di lingua (usato nei template
        admin custom). Per la maggior parte dei casi non serve.
        """
        widget_html = self.widget.render(name, self.initial)
        labels_html = ''.join([
            f'<label class="lang-label" for="id_{name}_{i}">'
            f'{TranslatableJSONWidget().language_labels.get(lang, lang)}'
            f'</label>'
            for i, lang in enumerate(self.languages)
        ])
        return mark_safe(f'{labels_html}{widget_html}')

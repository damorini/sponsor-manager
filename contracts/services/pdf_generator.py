"""
Generatore PDF dei contratti (versione 2 con template reali VALET).

Differenze rispetto alla v1:
- Salta i contratti ADDON (acquistati dal portale ecommerce, non hanno PDF)
- Sceglie il template giusto in base al tipo evento (ECM vs non-ECM)
- Auto-compila l'allegato con i ContractLine raggruppati per categoria
- Usa i tuoi template VALET originali (con dati anagrafici fissi)

Workflow:
    from contracts.services.pdf_generator import generate_contract_pdf
    
    document = generate_contract_pdf(contract)
    # → documento .docx + .pdf creati e salvati in MEDIA_ROOT
    # → record Document creato con storage_url
    # → ritorna il Document creato (None se è un ADDON)

Templates:
    /home/claude/projects/sponsor_manager/contracts/templates_pdf/
        ├── template_ecm_it.docx
        └── template_non_ecm_it.docx
"""
import logging
from datetime import date
from decimal import Decimal
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.utils import timezone

from docxtpl import DocxTemplate
from jinja2 import Environment

logger = logging.getLogger(__name__)


# ============================================================================
# Configurazione
# ============================================================================

# Path base dei template (relativo a BASE_DIR di Django)
TEMPLATES_DIR = Path(settings.BASE_DIR) / 'contracts' / 'templates_pdf'

# Mapping tipo evento → template
TEMPLATE_MAP = {
    ('ecm', 'it'): 'template_ecm_it.docx',
    ('non_ecm', 'it'): 'template_non_ecm_it.docx',
    # In futuro: ('ecm', 'en'): 'template_ecm_en.docx', ecc.
}

# Mapping accounting_category → label per allegato ECM
# (ordine di apparizione nell'allegato)
ECM_CATEGORY_LABELS = [
    ('viaggio_partecipanti', 'Spese complessive di viaggio ed ospitalità partecipanti'),
    ('viaggio_relatori', 'Spese di viaggi ed ospitalità relatori'),
    ('affitto_sala', 'Affitto sala'),
    ('stand', 'Spazi espositivi/stand'),
    ('coffee_break', 'Coffee break e colazioni di lavoro'),
    ('scheda_tecnica', 'Scheda tecnica in cartella'),
    ('quota_iscrizione', 'Quota d\u2019iscrizione'),
    ('altro', 'Altre spese'),
]


# ============================================================================
# Filtri Jinja
# ============================================================================

def format_date_filter(value):
    """Formatta una data come dd/mm/yyyy."""
    if not value:
        return ""
    if hasattr(value, 'strftime'):
        return value.strftime("%d/%m/%Y")
    return str(value)


def format_currency_filter(value):
    """Formatta un numero come valuta italiana (1.234,56)."""
    if value is None:
        return "0,00"
    try:
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(value)


def get_jinja_env():
    """Restituisce un Jinja Environment con i filtri custom."""
    env = Environment()
    env.filters['format_date'] = format_date_filter
    env.filters['format_currency'] = format_currency_filter
    return env


# ============================================================================
# Generazione PDF principale
# ============================================================================

def generate_contract_pdf(contract):
    """
    Genera il PDF (e il .docx intermedio) del contratto.
    
    Args:
        contract: istanza Contract Django
    
    Returns:
        Document creato (instance), oppure None se contract.kind == ADDON
        (per gli addon ecommerce non si genera PDF)
    
    Raises:
        FileNotFoundError se il template non esiste
        ValueError se mancano dati obbligatori (sponsor, evento, firmatario)
    """
    from contracts.models import ContractKind
    from shared.models import Document
    from sponsors.models import Contact

    # ========================================================================
    # 1. SKIP per addon ecommerce
    # ========================================================================
    if contract.contract_kind == ContractKind.ADDON:
        logger.info(
            "Contract %s è un ADDON, skip generazione PDF (ecommerce)",
            contract.contract_number
        )
        return None

    # ========================================================================
    # 2. Scegli template in base a tipo evento e lingua
    # ========================================================================
    event_type = _get_event_type(contract.event)  # 'ecm' o 'non_ecm'
    language = contract.language or 'it'
    
    template_key = (event_type, language)
    template_filename = TEMPLATE_MAP.get(template_key)
    
    if not template_filename:
        # Fallback: non_ecm italiano
        logger.warning(
            "Nessun template per %s, uso fallback non_ecm/it", template_key
        )
        template_filename = TEMPLATE_MAP[('non_ecm', 'it')]
    
    template_path = TEMPLATES_DIR / template_filename
    if not template_path.exists():
        raise FileNotFoundError(
            f"Template contratto non trovato: {template_path}"
        )

    # ========================================================================
    # 3. Costruisci il context per Jinja
    # ========================================================================
    sponsor = contract.sponsor
    event = contract.event
    signer = _get_signer_contact(contract)
    referente = _get_referente_contact(contract)
    
    # Validazione dati minimi
    if not signer:
        raise ValueError(
            f"Contract {contract.contract_number}: nessun Contact con is_signer=True. "
            "Imposta un firmatario sullo Sponsor prima di generare il contratto."
        )
    
    # Raggruppa righe per categoria (per allegato ECM)
    lines_by_category = _group_lines_by_category(contract, event_type)
    
    # Lista servizi piatta (per allegato non-ECM)
    services_list = _build_services_list_string(contract)
    
    context = {
        'contract': contract,
        'sponsor': sponsor,
        'signer': signer,
        'contact_referente': referente,
        'event': event,
        'lines_by_category': lines_by_category,
        'services_list': services_list,
        'stand_size': _get_stand_size(contract),
        'signature_place': getattr(settings, 'SIGNATURE_PLACE', 'Bologna'),
    }
    
    # ========================================================================
    # 4. Render del template .docx
    # ========================================================================
    doc = DocxTemplate(str(template_path))
    doc.render(context, jinja_env=get_jinja_env())
    
    # ========================================================================
    # 5. Salva il .docx intermedio
    # ========================================================================
    docx_filename = f"contratto_{contract.contract_number}_{contract.event.id}.docx"
    relative_docx_path = f"documents/contracts/{contract.id}/{docx_filename}"
    full_docx_path = Path(settings.MEDIA_ROOT) / relative_docx_path
    full_docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(full_docx_path))
    logger.info("Generato .docx: %s", full_docx_path)
    
    # ========================================================================
    # 6. Converti in PDF tramite LibreOffice headless
    # ========================================================================
    pdf_path = _convert_docx_to_pdf(full_docx_path)
    if not pdf_path:
        logger.warning(
            "Conversione PDF fallita per %s, mantengo solo .docx",
            contract.contract_number
        )
        # Crea Document per il .docx
        return _create_document_record(
            contract, full_docx_path, relative_docx_path,
            file_name=docx_filename, mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    
    # ========================================================================
    # 7. Crea record Document per il PDF
    # ========================================================================
    pdf_filename = pdf_path.name
    relative_pdf_path = relative_docx_path.replace('.docx', '.pdf')
    
    document = _create_document_record(
        contract, pdf_path, relative_pdf_path,
        file_name=pdf_filename, mime='application/pdf'
    )
    
    logger.info(
        "Contract %s: PDF generato e salvato (Document id=%s)",
        contract.contract_number, document.id
    )
    return document


# ============================================================================
# Helper: tipo evento (ECM vs non-ECM)
# ============================================================================

def _get_event_type(event):
    """
    Determina se un evento è ECM o non-ECM.
    
    Cerca un attributo `event.is_ecm` (boolean), oppure `event.event_type`
    ('ecm' / 'non_ecm'), oppure determina da `event.ecm_id`.
    
    Default: non_ecm.
    """
    if hasattr(event, 'is_ecm'):
        return 'ecm' if event.is_ecm else 'non_ecm'
    if hasattr(event, 'event_type') and event.event_type:
        return event.event_type
    if hasattr(event, 'ecm_id') and event.ecm_id:
        return 'ecm'
    return 'non_ecm'


# ============================================================================
# Helper: trova Contact firmatario / referente
# ============================================================================

def _get_signer_contact(contract):
    """Trova il Contact con is_signer=True per lo sponsor del contratto."""
    return contract.sponsor.contacts.filter(
        is_signer=True,
        deleted_at__isnull=True,
    ).first()


def _get_referente_contact(contract):
    """
    Trova il Contact 'referente' dello sponsor (responsabile operativo).
    
    Cerca per role='operational' o is_primary=True.
    """
    contacts = contract.sponsor.contacts.filter(deleted_at__isnull=True)
    
    # Prima prova: contact con ruolo 'operational'
    for c in contacts:
        if 'operational' in (c.roles or []):
            return c
    
    # Fallback: primary contact
    return contacts.filter(is_primary=True).first() or contacts.first()


# ============================================================================
# Helper: raggruppa righe per categoria contabile (per allegato ECM)
# ============================================================================

def _group_lines_by_category(contract, event_type):
    """
    Raggruppa le ContractLine per accounting_category del Service.
    
    Restituisce una LISTA di tuple (category_label, [lines]) ordinata
    secondo ECM_CATEGORY_LABELS. Le categorie senza righe vengono saltate.
    
    Per non-ECM, raggruppa tutto in 'altro' (l'allegato non-ECM ha tabella
    diversa, non usa raggruppamento).
    """
    # Raggruppa per category
    grouped = defaultdict(list)
    for line in contract.lines.select_related('service').all():
        category = (
            getattr(line.service, 'accounting_category', None) or 'altro'
        )
        grouped[category].append(line)
    
    # Ordina secondo ECM_CATEGORY_LABELS (e label friendly)
    result = []
    for cat_key, label in ECM_CATEGORY_LABELS:
        if cat_key in grouped and grouped[cat_key]:
            result.append((label, grouped[cat_key]))
    
    # Aggiungi categorie non standard alla fine
    standard_keys = {k for k, _ in ECM_CATEGORY_LABELS}
    for cat_key, lines in grouped.items():
        if cat_key not in standard_keys and lines:
            result.append((cat_key.replace('_', ' ').capitalize(), lines))
    
    return result


def _build_services_list_string(contract):
    """
    Costruisce una stringa con la lista servizi separati da '; '.
    Usata per la cella 'MODALITà DI SPONSORIZZAZIONE SCELTA' del non-ECM.
    """
    parts = []
    for line in contract.lines.all():
        qty = line.quantity if line.quantity > 1 else None
        if qty:
            parts.append(f"{line.service_name_snapshot} (q.tà {qty})")
        else:
            parts.append(line.service_name_snapshot)
    return "; ".join(parts) if parts else ""


def _get_stand_size(contract):
    """Restituisce la dimensione dello stand assegnato (es. '4x3')."""
    if contract.stand:
        return getattr(contract.stand, 'size_label', None) or contract.stand.code
    if contract.stand_block:
        return contract.stand_block.code
    return None


# ============================================================================
# Helper: conversione docx → pdf via LibreOffice
# ============================================================================

def _convert_docx_to_pdf(docx_path):
    """
    Converte un .docx in PDF usando LibreOffice headless.
    
    Restituisce Path del PDF generato, o None in caso di errore.
    """
    import subprocess
    
    docx_path = Path(docx_path)
    output_dir = docx_path.parent
    
    try:
        result = subprocess.run(
            [
                'libreoffice', '--headless',
                '--convert-to', 'pdf',
                '--outdir', str(output_dir),
                str(docx_path),
            ],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error(
                "LibreOffice convert error: %s", result.stderr.decode('utf-8', 'ignore')
            )
            return None
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("LibreOffice non disponibile o timeout: %s", e)
        return None
    
    pdf_path = output_dir / docx_path.name.replace('.docx', '.pdf')
    if pdf_path.exists():
        return pdf_path
    return None


# ============================================================================
# Helper: crea record Document
# ============================================================================

def _create_document_record(contract, full_path, relative_path, file_name, mime):
    """Crea il record Document collegato al contract."""
    from shared.models import Document
    
    contract_ct = ContentType.objects.get_for_model(contract.__class__)
    
    document = Document.objects.create(
        content_type=contract_ct,
        object_id=contract.id,
        title=file_name,
        file_name=file_name,
        file_size_bytes=full_path.stat().st_size,
        mime_type=mime,
        storage_url=settings.MEDIA_URL + relative_path,
        document_type='contract',
    )
    return document


# ============================================================================
# Hook: chiamato da Contract.mark_as_sent()
# ============================================================================

def auto_generate_on_send(contract):
    """
    Genera automaticamente il PDF quando il contratto passa a SENT.
    
    Da chiamare alla fine di Contract.mark_as_sent().
    Cattura tutti gli errori per non bloccare la transizione di stato.
    """
    try:
        document = generate_contract_pdf(contract)
        if document:
            logger.info(
                "Auto-generato PDF per %s (Document id=%s)",
                contract.contract_number, document.id
            )
    except Exception as e:
        logger.exception(
            "Errore auto-generazione PDF per %s: %s",
            contract.contract_number, e
        )
        # Non solleviamo: la transizione di stato deve completarsi

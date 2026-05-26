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
        # Piano pagamento (acconto/saldo), IVA inclusa
        'has_deposit': contract.has_deposit,
        'deposit_percent': contract.deposit_percent,
        'deposit_amount': format_currency_filter(contract.deposit_amount),
        'balance_amount': format_currency_filter(contract.balance_amount),
        'deposit_due_date': format_date_filter(contract.deposit_due_date) if contract.deposit_due_date else '',
        'balance_due_date': format_date_filter(contract.balance_due_date) if contract.balance_due_date else '',
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

    # Aggiunge header congresso + footer organizzatore al .docx generato
    # (i template originali restano intatti). Robusto: se manca qualcosa, salta.
    try:
        _add_header_footer_to_docx(full_docx_path, contract)
    except Exception as e:
        logger.warning("Header/footer PDF non applicati per %s: %s",
                       contract.contract_number, e)
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
    """
    Trova il firmatario da usare per il contratto, in ordine di priorita':
      1) il "Firmatario" scelto sul contratto (contract.sponsor_signer_contact),
         se valorizzato e non cancellato;
      2) FALLBACK: il primo Contact dello sponsor con is_signer=True
         (comportamento storico, mantenuto invariato).
    """
    chosen = getattr(contract, 'sponsor_signer_contact', None)
    if chosen is not None and getattr(chosen, 'deleted_at', None) is None:
        return chosen
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

def _create_document_record(contract, full_path, relative_path, file_name, mime, document_type='contract_pdf'):
    """Crea il record Document collegato al contract.

    Anti-doppioni: Soft-elimina i Document precedenti VIVI dello stesso tipo e
    stesso oggetto, cosi' resta sempre un solo documento vivo per tipo (sempre
    aggiornato). I vecchi restano soft-deleted (recuperabili); i file su disco
    non vengono toccati.
    """
    from shared.models import Document
    
    contract_ct = ContentType.objects.get_for_model(contract.__class__)
    
    # Soft-elimina i Document precedenti dello stesso tipo per questo oggetto
    previous = Document.objects.filter(
        content_type=contract_ct,
        object_id=contract.id,
        document_type=document_type,
        deleted_at__isnull=True,
    )
    for old_doc in previous:
        old_doc.delete()  # soft-delete
    
    document = Document.objects.create(
        content_type=contract_ct,
        object_id=contract.id,
        title=file_name,
        file_name=file_name,
        file_size_bytes=full_path.stat().st_size,
        mime_type=mime,
        storage_url=settings.MEDIA_URL + relative_path,
        document_type=document_type,
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


# ============================================================================
# Helper: header congresso (immagine) + footer organizzatore nel .docx
# ============================================================================

def _add_header_footer_to_docx(docx_path, contract):
    """
    HEADER DI PAGINA (v2): modifica IN-PLACE il .docx generato.

      - HEADER di pagina (su tutte le pagine): inserisce l'immagine header
        dell'evento (contract.event.email_header_image) a tutta larghezza,
        rimuovendo eventuali immagini preesistenti (vecchio logo) ma tenendo
        il testo (es. numero pagina).
      - FOOTER: logo segreteria + 4 righe a bandiera (sinistra) dai dati di
        core.OrganizerSettings.

    Non solleva: ogni parte e' protetta singolarmente.
    """
    from pathlib import Path as _Path
    from docx import Document
    from docx.shared import Mm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    docx_path = _Path(docx_path)
    d = Document(str(docx_path))
    sec = d.sections[0]
    usable_mm = (sec.page_width - sec.left_margin - sec.right_margin) / 36000.0

    changed = False

    # ---- HEADER DI PAGINA: immagine evento su tutte le pagine ----
    event = getattr(contract, 'event', None)
    header_img = getattr(event, 'email_header_image', None) if event else None
    if header_img:
        try:
            img_path = _Path(header_img.path)
            if img_path.exists():
                header = sec.header
                header.is_linked_to_previous = False

                # 1) rimuovi le immagini gia' presenti nell'header (vecchio logo),
                #    tenendo il testo (numero pagina ecc.)
                for p in header.paragraphs:
                    for run in list(p.runs):
                        if '<a:blip' in run._r.xml or '<w:drawing' in run._r.xml:
                            run._r.getparent().remove(run._r)

                # 2) inserisci l'header congresso nel primo paragrafo
                if header.paragraphs:
                    target = header.paragraphs[0]
                else:
                    target = header.add_paragraph()
                target.alignment = WD_ALIGN_PARAGRAPH.CENTER
                target.add_run().add_picture(str(img_path), width=Mm(usable_mm))
                changed = True
        except Exception:
            pass

    # ---- FOOTER: logo segreteria + 4 righe a bandiera ----
    try:
        from core.models import OrganizerSettings
        org = OrganizerSettings.load()
    except Exception:
        org = None

    if org:
        footer = sec.footer
        footer.is_linked_to_previous = False
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)

        # logo (se presente)
        logo = getattr(org, 'logo', None)
        if logo:
            try:
                logo_path = _Path(logo.path)
                if logo_path.exists():
                    p_logo = footer.add_paragraph()
                    p_logo.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p_logo.paragraph_format.space_after = Pt(2)
                    p_logo.add_run().add_picture(str(logo_path), height=Mm(12))
            except Exception:
                pass

        # costruisco le 4 righe (telefono+email+sito sulla stessa riga)
        righe = []
        if org.name:
            righe.append((org.name, True))
        if org.address:
            addr = " ".join(str(org.address).split())  # indirizzo su una riga
            righe.append((addr, False))
        contatti = []
        if org.phone:
            contatti.append("Tel: " + org.phone)
        if org.email:
            contatti.append("Email: " + org.email)
        if org.website:
            contatti.append(org.website)
        if contatti:
            righe.append(("   ".join(contatti), False))
        fisc = []
        if org.vat_number:
            fisc.append("P.IVA " + org.vat_number)
        if org.rea:
            fisc.append("REA " + org.rea)
        if fisc:
            righe.append((" · ".join(fisc), False))

        for testo, grassetto in righe:
            pp = footer.add_paragraph()
            pp.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pp.paragraph_format.space_after = Pt(0)
            pp.paragraph_format.line_spacing = 1.0
            rr = pp.add_run(testo)
            rr.bold = grassetto
            rr.font.size = Pt(7.5)
            rr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        if righe or logo:
            changed = True

    if changed:
        d.save(str(docx_path))


# ============================================================================
# PREVENTIVO: costruzione context segnaposti per il template lettera
# ============================================================================

def build_quote_context(contract):
    """
    Costruisce il dizionario dei segnaposti per il body_template di un
    LetterTemplate, a partire dai dati del contratto.

    Segnaposti prodotti (coerenti con shared.LetterTemplate):
        azienda, evento, date_evento, luogo_evento,
        numero, totale, stand, servizi

    Tutti i valori sono stringhe gia' formattate (date dd/mm/yyyy,
    totale come valuta italiana). Pronto per il render Jinja2.
    """
    sponsor = contract.sponsor
    event = contract.event

    # Nome evento (JSONField multilingua -> stringa nella lingua del contratto)
    lang = getattr(contract, 'language', None) or 'it'
    if hasattr(event, 'get_name'):
        evento = event.get_name(lang)
    else:
        evento = str(event)

    # Date evento (es. "10/06/2026 - 12/06/2026" oppure singola se coincidono)
    start = getattr(event, 'start_date', None)
    end = getattr(event, 'end_date', None)
    if start and end and start != end:
        date_evento = f"{format_date_filter(start)} - {format_date_filter(end)}"
    elif start:
        date_evento = format_date_filter(start)
    else:
        date_evento = ""

    # Luogo evento
    luogo_evento = getattr(event, 'location', "") or ""

    # Stand assegnato (riusa l'helper esistente)
    stand = _get_stand_size(contract) or ""

    # Lista servizi (riusa l'helper esistente, separati da '; ')
    servizi = _build_services_list_string(contract)

    # Aliquota IVA come stringa leggibile (es. '22%')
    try:
        _rate = contract.vat_rate
        aliquota_iva = f"{int(_rate)}%" if _rate == int(_rate) else f"{_rate}%"
    except Exception:
        aliquota_iva = ""

    context = {
        'azienda': sponsor.legal_name if sponsor else "",
        'evento': evento,
        'date_evento': date_evento,
        'luogo_evento': luogo_evento,
        'numero': contract.contract_number or "",
        'totale': format_currency_filter(contract.total),
        'imponibile': format_currency_filter(contract.subtotal),
        'iva': format_currency_filter(contract.vat_amount),
        'aliquota_iva': aliquota_iva,
        'stand': stand,
        'servizi': servizi,
    }
    return context


def render_quote_body(contract):
    """
    Renderizza il body_template del LetterTemplate associato al contratto,
    compilando i segnaposti con build_quote_context().

    Ritorna la stringa di testo della lettera, oppure '' se non c'e' template.
    """
    template = getattr(contract, 'letter_template', None)
    if not template or not template.body_template:
        return ""
    env = get_jinja_env()
    jinja_template = env.from_string(template.body_template)
    return jinja_template.render(**build_quote_context(contract))


# ============================================================================
# PREVENTIVO: generazione lettera PDF AL VOLO (mattone 5)
# ============================================================================

def generate_quote_pdf(contract):
    """
    Genera la lettera di preventivo in PDF, costruendo il .docx al volo con
    python-docx (nessun template .docx dedicato).

    Struttura della lettera:
        - header di pagina = immagine evento (via _add_header_footer_to_docx)
        - data e luogo (allineati a destra)
        - corpo = testo del LetterTemplate con segnaposti compilati
                  (render_quote_body), un paragrafo per riga
        - footer = dati organizzatore (via _add_header_footer_to_docx)

    Args:
        contract: istanza Contract con letter_template valorizzato.

    Returns:
        Document creato (instance) per il PDF (o per il .docx se la
        conversione PDF fallisce).

    Raises:
        ValueError se manca il LetterTemplate o il corpo risulta vuoto.
    """
    from datetime import date as _date
    from docx import Document as _DocxDocument
    from docx.shared import Pt, Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    # ----- 1. Validazione: serve un template con corpo -----
    template = getattr(contract, 'letter_template', None)
    if not template:
        raise ValueError(
            f"Contract {contract.contract_number}: nessun template lettera "
            "selezionato. Scegli un 'Template lettera preventivo' sul contratto."
        )

    body = render_quote_body(contract)
    if not body.strip():
        raise ValueError(
            f"Contract {contract.contract_number}: il template '{template.name}' "
            "ha prodotto un corpo vuoto. Controlla il body_template."
        )

    # ----- 2. Costruzione del .docx al volo -----
    doc = _DocxDocument()

    # Margini ragionevoli (lascia spazio a header immagine e footer)
    for section in doc.sections:
        section.top_margin = Mm(38)
        section.bottom_margin = Mm(32)
        section.left_margin = Mm(22)
        section.right_margin = Mm(22)

    # Riga data e luogo (in alto a destra)
    luogo_firma = getattr(settings, 'SIGNATURE_PLACE', 'Bologna')
    event_location = getattr(contract.event, 'location', '') or luogo_firma
    luogo_data = f"{event_location.split(',')[0].strip()}, {format_date_filter(_date.today())}"
    p_data = doc.add_paragraph(luogo_data)
    p_data.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for r in p_data.runs:
        r.font.size = Pt(10)

    doc.add_paragraph("")  # spazio

    # Corpo: un paragrafo per ogni riga del testo renderizzato
    for line in body.split("\n"):
        para = doc.add_paragraph(line)
        para.paragraph_format.space_after = Pt(6)
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for r in para.runs:
            r.font.size = Pt(11)

    # ----- 3. Salva il .docx intermedio -----
    docx_filename = f"preventivo_{contract.contract_number}_{contract.event.id}.docx"
    relative_docx_path = f"documents/quotes/{contract.id}/{docx_filename}"
    full_docx_path = Path(settings.MEDIA_ROOT) / relative_docx_path
    full_docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(full_docx_path))

    # ----- 4. Header evento + footer organizzatore (riuso helper esistente) -----
    try:
        _add_header_footer_to_docx(full_docx_path, contract)
    except Exception as e:
        logger.warning("Header/footer preventivo non applicati per %s: %s",
                       contract.contract_number, e)

    logger.info("Generato .docx preventivo: %s", full_docx_path)

    # ----- 5. Conversione in PDF -----
    pdf_path = _convert_docx_to_pdf(full_docx_path)
    if not pdf_path:
        logger.warning("Conversione PDF preventivo fallita per %s, tengo .docx",
                       contract.contract_number)
        return _create_document_record(
            contract, full_docx_path, relative_docx_path,
            file_name=docx_filename,
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            document_type='quote',
        )

    # ----- 6. Record Document per il PDF -----
    pdf_filename = pdf_path.name
    relative_pdf_path = relative_docx_path.replace('.docx', '.pdf')
    document = _create_document_record(
        contract, pdf_path, relative_pdf_path,
        file_name=pdf_filename, mime='application/pdf',
        document_type='quote',
    )
    logger.info("Contract %s: PDF preventivo generato (Document id=%s)",
                contract.contract_number, document.id)
    return document


# ============================================================================
# SCHEDA CLIENTE: PDF riepilogo sponsor+evento (mattone 2)
# ============================================================================

def generate_client_summary_pdf(sponsor, event):
    """
    Genera la scheda cliente in PDF per uno sponsor su un evento.
    Aggrega tutti i contratti non annullati (via build_client_summary),
    costruisce un .docx al volo e lo converte in PDF.

    Returns: Document creato. Raises ValueError se non ci sono contratti.
    """
    from datetime import date as _date
    from docx import Document as _DocxDocument
    from docx.shared import Pt, Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from .client_summary import build_client_summary

    data = build_client_summary(sponsor, event)
    if not data['contracts']:
        raise ValueError(
            f"Nessun contratto (non annullato) per {sponsor.legal_name} "
            f"su questo evento: scheda non generabile."
        )

    # contratto di riferimento (per header/footer e per agganciare il Document)
    ref_contract = data['contracts'][0]['contract']
    lang = getattr(ref_contract, 'language', None) or 'it'
    event_name = event.get_name(lang) if hasattr(event, 'get_name') else str(event)

    doc = _DocxDocument()
    for section in doc.sections:
        section.top_margin = Mm(38)
        section.bottom_margin = Mm(32)
        section.left_margin = Mm(20)
        section.right_margin = Mm(20)

    # Titolo
    h = doc.add_paragraph()
    r = h.add_run("Scheda cliente")
    r.bold = True
    r.font.size = Pt(16)

    sub = doc.add_paragraph()
    rs = sub.add_run(f"{sponsor.legal_name} - {event_name}")
    rs.font.size = Pt(12)
    doc.add_paragraph("")

    cur = lambda v: format_currency_filter(v)
    dt = lambda d: d.strftime('%d/%m/%Y') if d else '-'

    # Per ogni contratto
    for cd in data['contracts']:
        p = doc.add_paragraph()
        rp = p.add_run(f"Contratto {cd['numero']}"
                       + (f" - Spazio: {cd['stand']}" if cd['stand'] else ""))
        rp.bold = True
        rp.font.size = Pt(12)

        # tabella servizi
        if cd['lines']:
            table = doc.add_table(rows=1, cols=3)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text = 'Servizio'; hdr[1].text = 'Q.tà'; hdr[2].text = 'Importo'
            for ln in cd['lines']:
                row = table.add_row().cells
                row[0].text = ln['name']
                row[1].text = str(ln['quantity'])
                row[2].text = f"€ {cur(ln['line_total'])}"

        # totali
        doc.add_paragraph(f"Imponibile: € {cur(cd['subtotal'])}   "
                          f"IVA: € {cur(cd['vat_amount'])}   "
                          f"Totale (IVA incl.): € {cur(cd['total'])}")

        # piano pagamento
        if cd['has_deposit']:
            doc.add_paragraph(
                f"Acconto ({cd['deposit_percent']}%): € {cur(cd['deposit_amount'])} "
                f"entro il {dt(cd['deposit_due_date'])}  -  "
                f"Saldo: € {cur(cd['balance_amount'])} entro il {dt(cd['balance_due_date'])}"
            )
        else:
            doc.add_paragraph(
                f"Pagamento unico: € {cur(cd['balance_amount'])} "
                f"entro il {dt(cd['balance_due_date'])}"
            )
        doc.add_paragraph("")

    # Riepilogo economico complessivo
    tot = data['totals']
    pay = data['payments']
    rsum = doc.add_paragraph()
    rr = rsum.add_run("Riepilogo")
    rr.bold = True
    rr.font.size = Pt(12)
    doc.add_paragraph(f"Totale contratti (IVA incl.): € {cur(tot['total'])}")
    doc.add_paragraph(f"Incassato: € {cur(pay['incassato'])}")
    doc.add_paragraph(f"Residuo da incassare: € {cur(pay['residuo'])}")

    if pay['movimenti']:
        doc.add_paragraph("")
        mp = doc.add_paragraph(); mr = mp.add_run("Pagamenti ricevuti"); mr.bold = True
        for m in pay['movimenti']:
            doc.add_paragraph(
                f"  - {dt(m['date'])}: € {cur(m['amount'])} ({m['method']}) "
                f"- {m['contract_number']}"
            )

    # Salvataggio docx
    docx_filename = f"scheda_{sponsor.id}_{event.id}.docx"
    relative_docx_path = f"documents/client_summaries/{sponsor.id}/{docx_filename}"
    full_docx_path = Path(settings.MEDIA_ROOT) / relative_docx_path
    full_docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(full_docx_path))

    try:
        _add_header_footer_to_docx(full_docx_path, ref_contract)
    except Exception as e:
        logger.warning("Header/footer scheda cliente non applicati: %s", e)

    pdf_path = _convert_docx_to_pdf(full_docx_path)
    if not pdf_path:
        logger.warning("Conversione PDF scheda cliente fallita, tengo .docx")
        return _create_document_record(
            ref_contract, full_docx_path, relative_docx_path,
            file_name=docx_filename,
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            document_type='client_summary',
        )

    relative_pdf_path = relative_docx_path.replace('.docx', '.pdf')
    document = _create_document_record(
        ref_contract, pdf_path, relative_pdf_path,
        file_name=pdf_path.name, mime='application/pdf',
        document_type='client_summary',
    )
    logger.info("Scheda cliente generata per %s (Document id=%s)",
                sponsor.legal_name, document.id)
    return document

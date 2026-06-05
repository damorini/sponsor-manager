# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django 5.1 backoffice + sponsor self-service portal for VALET S.r.l. congresses (Italian, IT/EN multilingual). Manages sponsors, events (ECM and non-ECM), service catalog, contracts with auto-generated PDFs, ecommerce checkout (PayPal), automated emails and scheduled deadline reminders.

Runs in WSL2/Ubuntu. README.md has full setup. STATO_PROGETTO.md tracks session-by-session work notes.

## Commands

All Python commands assume `source venv/bin/activate` first. Default settings module is `config.settings.development` (set in `manage.py`).

```bash
# DB / app
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
python manage.py createsuperuser
python manage.py makemigrations <app>
python manage.py shell                       # ipython available
python manage.py shell < some_script.py      # run a one-off script with Django loaded

# Tests (pytest-django, --reuse-db is in pyproject)
pytest                                       # all
pytest tests/test_wishlist_views.py          # one file
pytest tests/test_wishlist_views.py::test_x  # one test
pytest -k "wishlist and not api"             # filter
pytest --cov                                 # coverage

# Lint / format (also wired via pre-commit)
ruff check . --fix
ruff format .
black .

# Async — three terminals
sudo service postgresql start && sudo service redis-server start
celery -A config worker -l info              # tasks (PDF, email, etc.)
celery -A config beat   -l info              # scheduled jobs (daily 07–10)

# Production settings (do NOT use locally by accident)
DJANGO_SETTINGS_MODULE=config.settings.production python manage.py <cmd>
```

Catalog imports (Excel templates live at repo root: `template_catalogo.xlsx`, `template_servizi.xlsx`):
```bash
python manage.py importa_catalogo <file.xlsx>
python manage.py importa_servizi  <file.xlsx>
python manage.py importa_stand    <file.xlsx>
```

In development, `CELERY_TASK_ALWAYS_EAGER=True` — Celery tasks run inline, Beat does NOT run. Trigger scheduled tasks by hand: `from contracts.tasks.scheduled import check_upcoming_deadlines; check_upcoming_deadlines()`. Email backend in dev is `console`.

## Architecture

### Django apps and what owns what

The system revolves around three entities: **Event → Sponsor ↔ Contract → ContractLine → Service**. Everything is scoped to an Event; Sponsors persist across events.

- `core/` — abstract base models (`TimeStampedModel` with UUID PK + timestamps, `SoftDeleteModel`), `TranslatableMixin`, `event_scope` (admin RBAC), the operator "cruscotto" landing page at `/admin/cruscotto/`, DeepL bridge in `translation.py`.
- `users/` — backoffice `User` (extends `AbstractUser`, UUID PK, `role` ∈ admin/operator/readonly/sponsor). `AUTH_USER_MODEL = 'users.User'`.
- `events/` — `Event` (ECM vs non-ECM, multilingual name/description, default_language, supported_languages).
- `sponsors/` — `Sponsor` (company, soft-delete to preserve contract history) and `Contact` (people; `roles` is a PG ArrayField of SIGNER/MARKETING/FINANCE/OPERATIONAL/CC/EDUCATIONAL; `portal_user` links to a `users.User`).
- `venues/` — `Stand`, `StandBlock` (physical exhibition spaces).
- `catalog/` — `Service` (with `PricingMode`: FIXED/QUANTITY/TIERED), `ServiceVariant`, `ServiceCategory`, `ServiceInclusion`, `DeadlineTemplate` (drives auto-generated deadlines on contract sign), `CatalogService`/`ServiceCategory` (new models per migration 0007).
- `contracts/` — `Contract` (states DRAFT → SENT → SIGNED → ACTIVE → COMPLETED, with CANCELLED escape; `ContractKind` MAIN/ADDON/ADDENDUM; `ContractOrigin` MANUAL/ECOMMERCE/IMPORT), `ContractLine`, `Deadline`. Subdirs: `services/` (pdf_generator, email_sender, paypal_service, client_summary, stand_line), `tasks/` (notifications + scheduled), `views/checkout.py`, `urls/{checkout,webhooks}.py`, `templates_pdf/*.docx`.
- `shared/` — polymorphic `Document` and `Communication` via `ContentType` GFK (attachable to Contract/Sponsor/Event/Deadline), audit log, email templates (`shared/email_templates/{it,en,base}/`).
- `portal/` — sponsor self-service site under `/portal/`. Views split: `auth, dashboard, contract, catalog, cart, materials, wishlist, profile`. `services/invitation.py` handles invitation flow. `context_processors.py` injects branding + cart count globally.

### Cross-cutting patterns

- **UUID primary keys everywhere** (via `TimeStampedModel` / `SoftDeleteModel`).
- **Multilingual fields** are `JSONField` keyed by language code (`{"it": "...", "en": "..."}`). Models declaring `TRANSLATABLE_FIELDS` get `obj.translated('name', lang)` with fallback chain: requested → `get_language()` → model default → `'it'` → first available. Never read these JSON fields raw in user-facing code or PDF snapshots — always go through `translated()`.
- **Soft delete** on Sponsor and Contract: deleted rows stay in DB to preserve history. Default manager hides them; use `.all_objects` (or model-specific manager) to include deleted.
- **Admin RBAC by event**: `core/event_scope.py` (`can_see_all`, `scope_by_event`, `scope_generic_by_event`) filters admin querysets to `user.managed_events` unless `is_superuser` or `can_see_all_events`. Superuser/Admin see everything; Operator/Readonly see only their events. Anagrafiche (Sponsor/Contact) remain visible to everyone. Apply in every `ModelAdmin.get_queryset` for event-scoped models.
- **Settings layout**: `config/settings/base.py` is shared; `development.py` and `production.py` extend it via `from .base import *`. Never import `base` directly. All config is `python-decouple`-driven from `.env`.
- **URLs**: `/admin/cruscotto/` (operator landing) and `/admin/` Django admin coexist — landing redirects to cruscotto; the order in `config/urls.py` matters. `/portal/` is sponsor self-service. `/webhooks/` is for PayPal (no auth).

### Cart / ecommerce flow

Self-service purchases create a `Contract` with `kind=ADDON`, not a separate Cart model:
- One active cart **per event per sponsor** (logical constraint, not DB-enforced).
- The ADDON contract's `parent_contract` points to the sponsor's first SIGNED/ACTIVE MAIN contract for that event.
- Lines are normal `ContractLine` rows on the draft.
- Checkout transitions DRAFT → PENDING_PAYMENT, runs PayPal/Card flow (`start_paypal_checkout` / `card_checkout_page` in `contracts/views/checkout.py`), and on success advances SIGNED → ACTIVE.
- `select_for_update` is used in `portal/views/cart.py` to prevent race conditions.
- ⚠ Open issue (see STATO_PROGETTO.md #1): `contract_number` has `unique=True` but is **not** auto-generated for ADDON contracts — second ADDON crashes on uniqueness collision. Needs numbering logic before production.

### Contract PDF generation

`contracts/services/pdf_generator.py` uses docxtpl + LibreOffice headless to render `contracts/templates_pdf/template_{ecm,non_ecm}_{lang}.docx`, then convert to PDF. Output lands in `media/documents/contracts/<id>/` and is recorded as a `shared.Document` with a `storage_url`. ADDON contracts are skipped (no PDF). VALET company data is currently **hardcoded inside the .docx templates** — to change company info, edit the templates, not settings.

When snapshotting service names/descriptions onto `ContractLine` for the PDF, always call `service.translated('name')` — storing the raw JSON dict here was the cause of the bug fixed in commit a940cca.

### Scheduled tasks (Celery Beat, defined in `config/celery.py`)

Daily Europe/Rome:
- 07:00 `send_operator_alerts`
- 08:00 `check_upcoming_deadlines` (T-10, T-3, T-0 reminders)
- 09:00 `check_overdue_deadlines` (post-deadline solleciti)
- 10:00 `check_abandoned_carts` (recovery emails)

Schedule lives in `config/celery.py`. Tasks are in `contracts/tasks/scheduled.py` and they delegate sending to `contracts/tasks/notifications.py`.

### Email templates

HTML responsive templates under `shared/email_templates/{it,en,base}/`. `config/settings/base.py` adds `BASE_DIR` to `TEMPLATES['DIRS']` so they resolve — keep this in mind if reorganizing templates.

## Tests

`tests/` at the repo root holds the pytest suite (`conftest.py` provides `user_sponsor`, `sponsor`, `contact`, `wishlist`, `client_authenticated` fixtures). Per-app tests live next to the app. `pytest.ini` overrides `testpaths = tests` and uses development settings; `pyproject.toml` widens scope to the whole repo with `--reuse-db`. They disagree — prefer running explicit paths if it matters.

## Repo hygiene notes

- The repo root is littered with one-shot patch scripts (`applica_*.py`, `fix_*.py`, `_addbtn.py`, etc.) and `.bak_YYYYMMDD_HHMMSS` files next to almost every modified `models.py` / `admin.py` / `views.py`. These are the user's historical change scripts and backups — **do not edit them, do not delete them unless asked, and do not imitate the pattern**. Edit the real files (`catalog/models.py`, not `models.py.bak_20260604_092540`).
- `README_ORIGINAL.md`, `STATO_PROGETTO.md`, `TODO.md` are user notes — read them for context, don't rewrite them.
- Commit messages in this repo are written in Italian, short, descriptive (`Portale: scadenze pagamento mostrate al cliente come Saldo/Acconto da pagare`). Match that style when committing.

## Common gotchas

- Always activate the venv and ensure postgres + redis are running before `manage.py` or `pytest`.
- `LOGIN_URL = 'portal:login'` — anonymous access to a `@login_required` view redirects into the portal, not Django admin.
- Hardcoded VALET data (P.IVA, REA, IBAN, legal rep) lives in DOCX templates under `contracts/templates_pdf/`, not in settings.
- When asked about "scaglioni" / TIERED pricing, the math is in `catalog/models.py` on `Service`.
- `select_for_update` and `transaction.atomic` are load-bearing in cart and contract state transitions — keep them.

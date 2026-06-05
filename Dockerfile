# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Installa dipendenze di runtime
#  - gettext: per 'manage.py compilemessages' (traduzioni IT/EN)
#  - libreoffice-writer: per i PDF contratto/domanda (docxtpl -> PDF via soffice)
#  - libpango/cairo/gdk-pixbuf + shared-mime-info: per WeasyPrint (PDF preventivo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    gettext \
    libreoffice-writer \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Crea user non-root PRIMA, poi copia i pacchetti nella SUA home.
# (Erano in /root/.local ma il container gira come appuser -> Python non li trovava.)
RUN useradd -m -u 1000 appuser
COPY --from=builder /root/.local /home/appuser/.local

# Copia codice applicazione
COPY . .
# Crea le dir montate come volumi (staticfiles/media/logs) GIÀ di proprietà di
# appuser: così i named volume Docker ereditano i permessi giusti e appuser può
# scrivere (altrimenti collectstatic -> PermissionError).
RUN mkdir -p /app/staticfiles /app/media /app/logs \
    && chown -R appuser:appuser /app /home/appuser/.local

# Imposta PATH (bin dei pacchetti --user di appuser)
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Esponi porta
EXPOSE 8000

# Entrypoint
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "60"]

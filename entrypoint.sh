#!/bin/bash
set -e

echo "🚀 Starting Sponsor Manager..."

# Aspetta che il database sia pronto
echo "⏳ Waiting for database..."
while ! pg_isready -h $DB_HOST -U $DB_USER -d $DB_NAME; do
  sleep 1
done
echo "✅ Database is ready"

# Esegui migrations
echo "📦 Running migrations..."
python manage.py migrate --noinput

# Compila le traduzioni (.po -> .mo). I .mo sono gitignored: senza questo
# step l'inglese non viene caricato in produzione.
echo "🌐 Compiling translations..."
python manage.py compilemessages -l en --ignore=venv --ignore=.venv

# Raccogli static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Crea superuser SOLO se le credenziali sono fornite via ambiente
# (DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD nel .env). Nessuna
# credenziale di default hardcoded: evita l'account admin/admin123.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "👤 Creating superuser from env if needed..."
  python manage.py createsuperuser --noinput 2>/dev/null \
    && echo "✅ Superuser created from env" \
    || echo "✅ Superuser already exists (or not created)"
fi

echo "✅ Setup complete!"
echo "🌐 Starting Gunicorn..."

# Avvia Gunicorn
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --worker-class sync \
    --worker-tmp-dir /dev/shm \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -

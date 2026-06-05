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

# Crea superuser se non esiste
echo "👤 Creating superuser if needed..."
python manage.py shell << PYTHON
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print("✅ Superuser created (admin/admin123)")
else:
    print("✅ Superuser already exists")
PYTHON

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

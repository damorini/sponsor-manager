# Sponsor Manager - Docker Deployment

## 🚀 Quick Start

### 1. Clona il repository
```bash
git clone <repo-url>
cd sponsor_manager
```

### 2. Configura le variabili d'ambiente
```bash
cp .env.docker .env.local
# Edita .env.local con i tuoi valori
```

### 3. Avvia i container
```bash
docker-compose up -d
```

### 4. Accedi all'applicazione
- **Django Admin**: http://localhost/admin (admin/admin123)
- **Applicazione**: http://localhost/

---

## 📋 Servizi

| Servizio | Porta | Descrizione |
|----------|-------|-------------|
| Django + Gunicorn | 8000 | Backend application |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache & Sessions |
| Nginx | 80, 443 | Reverse proxy |

---

## 🛠️ Comandi Utili

```bash
# Visualizza log
docker-compose logs -f web

# Accedi al container Django
docker-compose exec web bash

# Esegui migrations
docker-compose exec web python manage.py migrate

# Crea superuser
docker-compose exec web python manage.py createsuperuser

# Raccogli static files
docker-compose exec web python manage.py collectstatic

# Esegui test
docker-compose exec web pytest tests/

# Arresta container
docker-compose down

# Arresta e cancella volumi
docker-compose down -v
```

---

## 🔒 Production Checklist

- [ ] Cambia `SECRET_KEY` in .env.local
- [ ] Imposta `DEBUG=False`
- [ ] Configura `ALLOWED_HOSTS`
- [ ] Setup SSL/TLS con Let's Encrypt
- [ ] Configura email service (SendGrid/Gmail)
- [ ] Configura backup database
- [ ] Setup monitoring (Sentry)
- [ ] Configura logging
- [ ] Setup database backups
- [ ] Configura CDN per static files

---

## 📊 Monitoring

### Health Checks
- Django: http://localhost/health/
- PostgreSQL: `docker-compose exec db pg_isready`
- Redis: `docker-compose exec redis redis-cli ping`

### Logs
```bash
# Nginx logs
docker-compose logs nginx

# Django logs
docker-compose logs web

# Database logs
docker-compose logs db
```

---

## 🚀 Deploy su Production

### Con Heroku
```bash
heroku login
heroku create sponsor-manager
heroku config:set DEBUG=False SECRET_KEY=<your-key>
git push heroku main
heroku run python manage.py migrate
```

### Con AWS ECS
```bash
# Build e push Docker image
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.eu-west-1.amazonaws.com
docker tag sponsor_manager:latest <account>.dkr.ecr.eu-west-1.amazonaws.com/sponsor_manager:latest
docker push <account>.dkr.ecr.eu-west-1.amazonaws.com/sponsor_manager:latest
```

---

## 📚 Documentazione
- [Django Docs](https://docs.djangoproject.com/)
- [Docker Docs](https://docs.docker.com/)
- [Gunicorn Docs](https://docs.gunicorn.org/)
- [Nginx Docs](https://nginx.org/en/docs/)


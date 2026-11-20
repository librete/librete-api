# Deploying Librete on a single server

This stack runs PostgreSQL, the API (gunicorn) and [Caddy](https://caddyserver.com/), which
serves the PWA and proxies `/api/`, `/_allauth/`, `/admin/` and `/static/` to the API on the
same domain, with automatic HTTPS.

Tested target: Ubuntu Server 26.04 with Docker Engine and the Compose plugin.

## 1. Server preparation

```bash
sudo apt install docker.io docker-compose-v2   # or Docker's own apt repository
sudo usermod -aG docker $USER                  # log out and back in
sudo ufw allow 80,443/tcp && sudo ufw allow 443/udp
```

Point the domain's DNS `A`/`AAAA` records at the server before the first start, so Caddy can
get a certificate.

## 2. Configure

```bash
git clone https://github.com/librete/librete-api.git
cd librete-api/deploy
cp .env.example .env    # set DOMAIN, SECRET_KEY, POSTGRES_PASSWORD, EMAIL_URL
```

## 3. Build the PWA into `deploy/web`

From the `librete-mobile` repository:

```bash
npm ci && npm run build
rsync -a --delete www/ ../librete-api/deploy/web/
```

## 4. Start

```bash
docker compose up -d --build
docker compose exec api python manage.py createsuperuser
```

Migrations run automatically when the API container starts.

## Updating

```bash
git pull && docker compose up -d --build
```

## Backups

`./backup.sh` writes a compressed `pg_dump` to `deploy/backups/`; schedule it with cron and
copy the folder off the server. Restore with:

```bash
gunzip -c backups/<file>.sql.gz | docker compose exec -T db psql -U librete librete
```

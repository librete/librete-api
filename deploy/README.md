# Deploying Librete on a single server

This stack runs PostgreSQL, the API (gunicorn), a reminder `worker` (sends event reminders
to the PWA via Web Push every 60 s) and [Caddy](https://caddyserver.com/), which serves the
PWA and proxies `/api/`, `/_allauth/`, `/admin/` and `/static/` to the API on the same
domain, with automatic HTTPS.

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

Generate the VAPID key pair for Web Push reminders once and paste the two lines it prints
into `.env` (also set `VAPID_SUBJECT=mailto:<your address>`; push services use it to contact
you):

```bash
docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 api python manage.py generate_vapid_keys
```

Keep the keys: replacing them invalidates every browser's push subscription (users have to
enable reminders again). Without keys the API and app work, but the PWA gets no reminders
(the Android app schedules its reminders locally either way).

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

Migrations run automatically when the API container starts. Check the reminder worker with
`docker compose logs -f worker`.

Check the deployment from your workstation (in `librete-mobile`):

```bash
E2E_BASE_URL=https://librete.eu npm run e2e
```

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

# librete-api

REST API for **Librete**, a personal organizer for events, notes and tasks grouped into
categories. Built with Django 5.2 LTS, Django REST framework and django-allauth (headless).

## Development

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python automatically).

```bash
cp .env.example .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

- API docs (Swagger UI): http://localhost:8000/api/docs/
- Auth API docs (allauth): http://localhost:8000/_allauth/openapi.html
- Admin: http://localhost:8000/admin/

With `EMAIL_URL=consolemail://`, verification and password-reset codes are printed to the
console.

### With Docker (PostgreSQL)

```bash
docker compose up --build        # API on http://localhost:8000
docker compose exec api python manage.py createsuperuser
```

## Tests and linting

```bash
uv run pytest            # add --cov=librete for coverage
uv run ruff check .
uv run ruff format .
```

## API overview

| Endpoint | Description |
|----------|-------------|
| `/_allauth/app/v1/auth/signup`, `/auth/login`, `/auth/session` (DELETE = logout), `/auth/email/verify`, `/auth/password/request`, `/auth/password/reset`, `/account/password/change` | Authentication (django-allauth headless, "app" client) |
| `/api/users/me/` | GET / PATCH the current user's profile (`first_name`, `last_name`, `language`) |
| `/api/users/me/delete/` | POST `{password}` to delete the account and all data |
| `/api/users/me/ics/`, `/ics/<token>.ics` | Calendar subscription feed (secret URL: create/rotate, revoke, include tasks) |
| `/api/categories/`, `/api/events/`, `/api/notes/`, `/api/tasks/` | CRUD, scoped to the current user; filtering, `?search=`, `?ordering=`, `?page=`/`?page_size=` |
| `/api/stats/?year=&tz=` | Totals and monthly activity for the home screen |
| `/api/health/` | Health check |

Authenticated requests send the session token returned by login/signup in the
`X-Session-Token` header. A `401` means the token is missing, invalid or expired.

Email verification is mandatory by default and uses short codes (`ABCD-EFGH`) rather than
links, so it works the same in the mobile app and the PWA.

## Deployment

See [`deploy/README.md`](deploy/README.md): Docker Compose with PostgreSQL, gunicorn and
Caddy (automatic HTTPS), serving the PWA and the API from one domain.

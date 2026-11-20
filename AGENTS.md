# AGENTS.md — librete-api

REST API for Librete (personal organizer: categories, events, notes, tasks). The client is
[librete-mobile](https://github.com/librete/librete-mobile) (Android app + PWA).

## Stack
- Python 3.13 (`.python-version`), **uv** (`pyproject.toml`, `uv.lock`)
- Django **5.2 LTS**, Django REST framework, django-filter, drf-spectacular (OpenAPI)
- **django-allauth headless** ("app" client) for authentication; django-parler for the
  translated default categories
- PostgreSQL in Docker/production, SQLite by default locally; WhiteNoise, gunicorn, Caddy
- Tests: pytest + pytest-django + factory_boy. Lint/format: ruff

## Commands
```bash
uv sync                                   # install
uv run python manage.py runserver         # needs DEBUG=1 (see .env.example) or SECRET_KEY
uv run pytest                             # tests (librete/settings_test.py)
uv run pytest --cov=librete
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations    # with DEBUG=1
uv run python manage.py makemessages -l bg --ignore=.venv --ignore=staticfiles --ignore=deploy
uv run python manage.py compilemessages -l bg --ignore=.venv   # commit the .mo file too
uv run python manage.py generate_vapid_keys         # Web Push key pair (with DEBUG=1)
uv run python manage.py send_reminders [--loop]     # send due reminders (once / forever)
docker compose up --build                 # API + reminder worker + Postgres on :8000
```
`uv` may live in `~/.local/bin`. Run the suite against Postgres with
`DATABASE_URL=postgres://librete:librete@localhost:5432/librete uv run pytest` (start
`docker compose up db` first).

## Layout
```
librete/
  settings.py          all config from env vars (django-environ); .env.example lists them
  settings_test.py     test overrides (MD5 hasher, locmem email)
  urls.py              router + /api/users/me/, /api/stats/, /api/push/vapid-key/,
                       /api/health/, /api/schema/, /api/docs/, /_allauth/ (allauth
                       headless), /admin/
  templates/account/email/   branded allauth email templates
  utils/               TimestampModel, OwnedModel (author FK), OwnedModelViewSet,
                       OwnedPrimaryKeyRelatedField, DateRangeValidationMixin,
                       SessionTokenAuthentication, StandardPagination
  contrib/
    users/             custom User (email login, no username, `language`, `time_zone`,
                       `default_reminders`), MeView, AccountDeleteView, SignupForm (extra
                       allauth signup fields)
    categories/        Category, DefaultCategory (parler), services.create_default_categories,
                       signals (allauth user_signed_up), seed data migration 0003
    events/ notes/ tasks/   models, serializers, viewsets (+ tests/test_api.py each)
    stats/             StatsView (totals + monthly counts, ?year=&tz=)
    reminders/         event reminders: validators + RemindersField (shared by Event and
                       User), ScheduledReminder + services.sync_event_reminders (post_save
                       signal), PushSubscription + views (Web Push), sender.py (payload +
                       delivery), commands generate_vapid_keys / send_reminders
  tests/               factories, cross-cutting tests (ownership, pagination, i18n, misc)
conftest.py            fixtures: api_client, user, other_user, auth_client, client_for
locale/bg/             Bulgarian catalogue
deploy/                production compose (Postgres, API, reminder worker, Caddy), Caddyfile,
                       backup.sh, README
```

## Reminders (contract shared with librete-mobile — don't change it unilaterally)
- `Event.reminders`: minutes before `start_date`, each 0..40320, at most 5, deduplicated,
  stored/returned sorted descending (`"reminders": [60, 15]`). Omitted on create → the
  author's `default_reminders`; `[]` = none.
- `/api/users/me/`: `default_reminders` (same rules, default `[15]`) and `time_zone` (IANA
  name, default `"UTC"`, used to format push text).
- `ScheduledReminder(event, minutes_before, remind_at, sent_at)` rows are derived from the
  event on every save (rescheduled rows get `sent_at = null`); never edit them directly.
- Web Push for the PWA (the Android app schedules local notifications instead):
  `GET /api/push/vapid-key/` → `{"public_key": str | null}`;
  `POST /api/push/subscriptions/` with the browser `PushSubscription` JSON → 201/200
  `{"id", "endpoint", "created_at"}` (an endpoint registered by another user moves to the
  caller; HTTPS only); `DELETE /api/push/subscriptions/<id>/` → 204 (own only).
  `PushSubscription` has a `user` FK (not `OwnedModel`); its viewset filters by
  `request.user` itself.
- `send_reminders` (the `worker` service runs it with `--loop`, every 60 s) sends due rows to
  all of the author's subscriptions, skips rows more than 1 h late (marked sent), deletes
  subscriptions answering 404/410, and does nothing without `VAPID_*` keys. Payload is the
  Angular service worker format: `{"notification": {title, body, icon, badge,
  tag: "event-<id>-<minutes>", data: {eventId, onActionClick.default:
  {operation: "navigateLastFocusedOrOpen", url: "/events/<id>"}}}}`, body localized with the
  user's `language` and `time_zone`. Tests mock `pywebpush.webpush` and pass `now`.

## Conventions and rules
- **Every user-owned model extends `OwnedModel`**; viewsets extend `OwnedModelViewSet`
  (queryset filtered to `request.user`, author set on create). Related fields to other
  owned objects must use `OwnedPrimaryKeyRelatedField` — never a plain queryset (that was
  an IDOR in the legacy code). `tests/test_ownership.py` covers every resource; add new
  resources to it.
- Reverse accessors: `user.categories`, `user.events`, `user.notes`, `user.tasks`
  (`related_name="%(app_label)s"`).
- Serializers use integer IDs, explicit `fields` tuples (no `__all__`).
- Auth: clients send `X-Session-Token`. Missing/invalid token → **401** (custom
  `SessionTokenAuthentication`). allauth endpoints live under `/_allauth/app/v1/`; email
  verification is mandatory and both verification and password reset use **codes**
  (`ABCD-EFGH`), not links. allauth returns 401 with `meta.session_token` for pending flows.
- allauth hides whether an email exists (signup with a known email returns the same pending
  response and emails the owner).
- User-facing strings: wrap in `gettext_lazy`, add the Bulgarian translation, compile.
  Responses and emails follow `Accept-Language`.
- Tests: pytest functions with fixtures from `conftest.py` and factories from
  `librete/tests/factories.py`; assert behaviour (status codes, JSON) and isolation between
  users. Keep the suite fast (~1 s).
- Settings changes need an env var with a safe default, an entry in `.env.example` and,
  if production-relevant, in `deploy/compose.yaml`.
- No live data existed when the API was rebuilt (2026-11); from now on add migrations
  normally — don't edit applied ones.

## Gotchas
- `django-environ` URLs: absolute paths need four slashes (`sqlite:////abs/db.sqlite3`,
  `filemail:////abs/dir`); three slashes are relative.
- WhiteNoise warns if `staticfiles/` is missing; it is kept with a `.gitkeep`.
- DRF throttling and allauth rate limits use the cache; tests clear it (autouse fixture).

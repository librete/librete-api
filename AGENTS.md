# AGENTS.md — librete-api

REST API for Librete (personal organizer: categories, events, notes, tasks). The client is
[librete-mobile](https://github.com/librete/librete-mobile) (Android app + PWA).

## Stack
- Python 3.13 (`.python-version`), **uv** (`pyproject.toml`, `uv.lock`)
- Django **5.2 LTS**, Django REST framework, django-filter, drf-spectacular (OpenAPI),
  python-dateutil (RRULE expansion)
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
uv run python manage.py send_reminders [--loop]     # send due reminders + series top-up
docker compose up --build                 # API + reminder worker + Postgres on :8000
```
`uv` may live in `~/.local/bin`. Run the suite against Postgres with
`DATABASE_URL=postgres://librete:librete@localhost:5432/librete uv run pytest` (start
`docker compose up db` first). Search ranking tests only run there (skipped on SQLite).

## Layout
```
librete/
  settings.py          all config from env vars (django-environ); .env.example lists them
  settings_test.py     test overrides (MD5 hasher, locmem email)
  urls.py              router + /api/users/me/, /api/stats/, /api/sync/, /api/search/,
                       /api/actions/<token>/, /api/push/vapid-key/, /api/health/,
                       /api/schema/, /api/docs/, /_allauth/ (allauth headless), /admin/
  templates/account/email/   branded allauth email templates
  utils/               TimestampModel, OwnedModel (author FK, client_id, version,
                       lock_owner), OwnedModelViewSet (idempotent create, If-Match/409,
                       ETag), OwnedModelSerializer, OwnedPrimaryKeyRelatedField,
                       DateRangeValidationMixin, SessionTokenAuthentication,
                       StandardPagination, recurrence.py (RRULE validation/expansion,
                       shared by events and tasks)
  contrib/
    users/             custom User (email login, no username, `language`, `time_zone`,
                       `default_reminders`, `default_task_reminders`), MeView (a time zone
                       change refreshes series reminders), AccountDeleteView, SignupForm
    categories/        Category, DefaultCategory (parler), services.create_default_categories,
                       signals (allauth user_signed_up), seed data migration 0003
    events/ notes/ tasks/   models, serializers, viewsets (+ tests/test_api.py each);
                       events/recurrence.py (occurrence expansion, exdates),
                       events/tests/rrule_vectors.json (shared with the app),
                       tasks/services.py (next instance of a repeating task)
    stats/             StatsView (totals + monthly counts, ?year=&tz=)
    reminders/         event + task reminders: validators + RemindersField (shared by
                       Event, Task and User), ScheduledReminder + services (sync_event_ /
                       sync_task_reminders via signals, series window, top-up),
                       PushSubscription + views (Web Push, ActionView), sender.py (payload +
                       delivery), actions.py (signed action tokens), UsedActionToken,
                       WorkerRun, commands generate_vapid_keys / send_reminders
    sync/              offline sync: Change (per-user change log), signals that record
                       it, resources.py (type → model/serializer/queryset), SyncView
    search/            SearchView (/api/search/); migration 0001 = pg_trgm + GIN trigram
                       indexes (PostgreSQL only, no-op elsewhere)
  tests/               factories, cross-cutting tests (ownership, pagination, i18n, misc)
conftest.py            fixtures: api_client, user, other_user, auth_client, client_for
locale/bg/             Bulgarian catalogue
deploy/                production compose (Postgres, API, reminder worker, Caddy), Caddyfile,
                       backup.sh, README
```

## Reminders (contract shared with librete-mobile — don't change it unilaterally)
- `Event.reminders` / `Task.reminders`: minutes before the event start / task due date
  (`end_date`, else `start_date`), each 0..40320, at most 5, deduplicated, stored/returned
  sorted descending (`"reminders": [60, 15]`). Omitted on create → the author's
  `default_reminders` (events, default `[15]`) / `default_task_reminders` (tasks, default
  `[]`); `[]` = none. Tasks without a date, or finished, get no scheduled reminders.
- `/api/users/me/`: `default_reminders`, `default_task_reminders` and `time_zone` (IANA
  name, default `"UTC"`; formats push text and is the zone recurrences expand in).
- `ScheduledReminder(event | task (exactly one), occurrence_start, minutes_before,
  remind_at, sent_at, one_off)` rows are derived on every save (rescheduled rows get
  `sent_at = null`); never edit them directly. A **series** gets rows for occurrences
  starting in [now − 1 h, now + 60 days] (`occurrence_start` set; exdates and overridden
  occurrences skipped); saving the series, saving/deleting one of its overrides and
  changing the user's time zone refresh them, and the worker tops the window up every
  12 h. `one_off` rows are snoozes from notification actions; the sync never touches them.
- Web Push for the PWA (the Android app schedules local notifications instead):
  `GET /api/push/vapid-key/` → `{"public_key": str | null}`;
  `POST /api/push/subscriptions/` with the browser `PushSubscription` JSON → 201/200
  `{"id", "endpoint", "created_at"}` (an endpoint registered by another user moves to the
  caller; HTTPS only); `DELETE /api/push/subscriptions/<id>/` → 204 (own only).
  `PushSubscription` has a `user` FK (not `OwnedModel`); its viewset filters by
  `request.user` itself.
- `send_reminders` (the `worker` service runs it with `--loop`, every 60 s) first runs the
  series top-up when the last one (a `WorkerRun` row) is ≥ 12 h old (it also deletes snoozes
  and used action tokens older than 8 days), then sends due rows to all of the author's
  subscriptions. It skips rows more than 1 h late or whose event/occurrence started (task
  was due) more than 1 h ago (snoozes: only lateness counts) and marks them sent, deletes
  subscriptions answering 404/410, and does nothing without `VAPID_*` keys.
- Payload (Angular service worker format), localized with the user's `language` and
  `time_zone`: `{"notification": {title, body, icon, badge, tag, actions, data}}`.
  - Events: title = name, body "Starts at 18:00" / "Starts on 05/02/2030 at 18:00"
    (+ " · location"), `tag: "event-<id>-<occurrence start (event start for plain events)
    epoch s>-<minutes>"`, `actions: [{action: "snooze", title: "Snooze 10 min"}]`,
    `data: {eventId, occurrenceStart: ISO | null, onActionClick: {default:
    {operation: "navigateLastFocusedOrOpen", url: "/events/<id>" (+ "?occurrence=<ISO>")},
    snooze: {operation: "sendRequest", url: "/api/actions/<token>/"}}}`.
  - Tasks: title = name, body "Due at 18:00" / "Due on 05/02/2030 at 18:00" (+ " · category"),
    `tag: "task-<id>-<minutes>"`, actions done ("Mark done") + snooze ("Snooze 1 h"),
    `data: {taskId, onActionClick: {default → "/tasks/<id>", done, snooze → sendRequest}}`.
  Tests mock `pywebpush.webpush` and pass `now`.
- `GET /api/actions/<token>/` (no login; `authentication_classes = []`): token =
  `django.core.signing.dumps({"op": "done"|"snooze", "type": "event"|"task", "id",
  "occurrence": ISO|null, "minutes", "user", "jti"}, salt="librete.actions")`, valid 7 days,
  single use (`UsedActionToken(jti)`). `done` (tasks only) finishes the task through
  `save()` (version, change log, next repeat instance); `snooze` adds a one-off reminder at
  now + `minutes` (events 10, tasks 60; `minutes_before = 0`). 204; malformed/tampered →
  400; expired, reused, or item gone → 410; nothing changes on errors.

## Recurrence (contract shared with librete-mobile — don't change it unilaterally)
- `Event.recurrence` / `Task.repeat`: RRULE body without `RRULE:` (≤ 500 chars), stored
  upper-cased; FREQ DAILY/WEEKLY/MONTHLY/YEARLY; parts INTERVAL, COUNT, UNTIL
  (`YYYYMMDDTHHMMSSZ` only), WKST, BYDAY, BYMONTHDAY, BYMONTH, BYYEARDAY, BYWEEKNO, BYSETPOS
  (no BYHOUR/BYMINUTE/BYSECOND); not COUNT and UNTIL together; a rule without an end must
  produce an occurrence within 10 years. `null`/`""` = doesn't repeat.
- Expansion (`utils/recurrence.py`): dateutil with DTSTART = the start (task: due date)
  converted to the author's `time_zone`, microseconds dropped; wall-clock time kept across
  DST; a nonexistent local time uses the offset before the change, an ambiguous one is the
  first; DTSTART is only an occurrence if it matches the rule. Occurrences last
  `end_date - start_date`. The vectors in `events/tests/rrule_vectors.json` (copied into
  the app) pin this down; their `expected_starts` are the occurrences overlapping
  [range_start, range_end] (start ≤ range_end and end ≥ range_start).
- `Event.exdates`: original starts skipped, stored as sorted unique
  `YYYY-MM-DDTHH:MM:SSZ`. Overrides: `recurrence_parent` (own series only, CASCADE) +
  `original_start` (both or neither; DB check constraint), never with `recurrence`.
- `GET /api/events/?expand=1&end_date__gte=<start>&start_date__lte=<end>` (both required,
  ≤ 400 days, else 400): stored non-recurring events and overrides filtered as usual
  (overrides with `occurrence_start = original_start`), plus every overlapping occurrence of
  each series as the series' data with the occurrence's dates, `id` = series id,
  `occurrence_start` and `is_occurrence: true`; overridden/exdate occurrences left out.
  `category`/`search` apply to series; `start_date__gte`/`end_date__lte` to occurrences;
  `ordering` is ignored (sorted by `start_date`, then id), paginated as usual. Everywhere
  else events have `occurrence_start: null, is_occurrence: false`.
- Completing a repeating task (status → finished via PUT/PATCH, the done action, admin or
  code; `Task.save` detects the transition) creates the next instance in the same
  transaction: copy of name, category, parent, description, priority, repeat (COUNT − 1),
  reminders; `status=active`; dates shifted by (next occurrence strictly after the due
  date − due date); `client_id = uuid5(NAMESPACE_URL, "librete:task-repeat:" + (client_id
  as lower-case hyphenated UUID, or "id:<pk>") + ":" + next due "YYYY-MM-DDTHH:MM:SSZ")`.
  Nothing if that `client_id` exists for the author or the rule ended. Un-finishing
  doesn't delete it.

## Search
`GET /api/search/?q=&types=&category=&limit=` → `{"query", "results": [{"type", "id",
"score", "item"}], "counts": {<requested type>: n}}`. `q` ≥ 2 chars after trimming; `limit`
per type (default 10, capped at 50); `category` limits events/notes/tasks. PostgreSQL: score =
greatest `similarity`/`word_similarity` over the fields (events name/location/description,
notes name/text, tasks name/description, categories name/description); match when ≥ 0.3 or
icontains (score ≥ 0.5). SQLite: icontains only (ASCII-only case folding), score 1.0. Sorted
by score, then `updated_at`, descending. `item` is exactly the detail payload.

## Offline sync (contract shared with librete-mobile — don't change it unilaterally)
Applies to categories, events, notes and tasks (everything on `OwnedModel`). New fields
(`Category.color` — `#rrggbb` or null, input any case; event recurrence fields; task
`reminders`/`repeat`) are ordinary fields in GET/list/sync payloads.
- **`client_id`** (UUID or null): sent by the app on create, writable on create only
  (ignored on PUT/PATCH). Unique per (author, resource) when set. A POST with a
  `client_id` the author already used for that resource → **200** with the existing item
  (payload ignored, no validation); otherwise **201**. A concurrent duplicate that hits the
  unique constraint is answered the same way. Other users' `client_id`s are irrelevant.
- **`version`** (read-only int): 1 on create, +1 on every save (API, admin, code —
  `OwnedModel.save`). Single-item responses (GET/POST/PUT/PATCH) carry `ETag: "<version>"`.
- **`If-Match`** on PUT, PATCH, DELETE: `3`, `"3"` or `W/"3"` (`*` = no check). Different from
  the current version → **409** `{"detail": "This item was changed elsewhere."
  (translated), "current": <item as GET returns it>}` and nothing changes. Absent → last
  write wins. Unparseable → **400** `{"detail": ...}`. CORS allows `If-Match` and exposes
  `ETag`.
- **`GET /api/sync/`**: without `since` → `{"cursor": <latest change id of the user or 0>,
  "has_more": false, "changes": []}` (the app calls it before its initial full load).
  With `since=<int ≥ 0>` (+ `limit`, default 500, capped at 1000; + `types=events,notes`):
  `{"cursor": <seq of the last returned change, or since>, "has_more": bool, "changes":
  [{"seq", "type", "id", "op": "upsert" | "delete", "data": <item exactly as
  GET /api/<type>/<id>/ returns it, incl. category counts> | null}]}`, ordered by `seq`.
  Each object appears at most once (its latest change); an upsert whose object vanished is
  reported as a delete. Negative/invalid `since`, `limit < 1` or unknown types → 400.
- `Change(user, type, object_id, op, created_at)`, `id` = seq: exactly one row per (user,
  type, object_id); every change deletes the old row and inserts a new one in the same
  transaction (post_save / post_delete signals in `contrib/sync/signals.py`; cascaded
  deletes get their own rows; deleting the user just drops the log). Migration
  `sync/0002_backfill` gave pre-existing items an upsert row.
- Every write to an owned model takes `lock_owner(author)` (the user row, `SELECT … FOR
  UPDATE`) first, so a user's writes are serialized: `If-Match` checks can't race and change
  ids are committed in order (a cursor never skips a change committed late).

## Conventions and rules
- **Every user-owned model extends `OwnedModel`**; viewsets extend `OwnedModelViewSet`
  (queryset filtered to `request.user`, author set on create). Related fields to other
  owned objects must use `OwnedPrimaryKeyRelatedField` — never a plain queryset (that was
  an IDOR in the legacy code). `tests/test_ownership.py` covers every resource; add new
  resources to it.
- **Every write to an owned model must record a `Change`** — go through `save()` /
  `delete()` (signals do it). Never use queryset `.update()`, `bulk_create()` or
  `bulk_update()` on categories, events, notes or tasks; if you must, record the changes
  with `sync.services.record_change` after `lock_owner`, in the same transaction. New
  synced resources: extend `OwnedModel` + `OwnedModelSerializer` (list `client_id` and
  `version` in `fields`), add them to `Change.Type` and `sync/resources.py`.
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

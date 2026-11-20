# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, for layer caching.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
    && useradd --system --uid 1000 --home /app librete \
    && chown -R librete /app/staticfiles

USER librete
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/')"

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "librete.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]

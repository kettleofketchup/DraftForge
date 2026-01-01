# ---- Builder (production deps only) ----
FROM python:3.12-bookworm AS poetry
LABEL org.opencontainers.image.source "https://github.com/kettleofketchup/dota_tournament"
WORKDIR /app

RUN pip install poetry==2.1.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

FROM poetry AS deps
# Copy lockfiles only
COPY pyproject.toml poetry.lock /app/
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --no-root --without dev

# ---- Dev Deps----
FROM deps AS deps-dev
# Install full deps (including dev/test)
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --no-root --with dev


FROM deps AS source
WORKDIR /app
COPY __init__.py paths.py tasks.py /app/
COPY ./scripts /app/scripts
COPY ./backend /app/backend


FROM deps-dev AS source-dev
WORKDIR /app
COPY __init__.py paths.py tasks.py /app/
COPY ./scripts /app/scripts
COPY ./backend /app/backend

# ---- Runtime (production) ----
FROM source AS runtime
LABEL org.opencontainers.image.source "https://github.com/kettleofketchup/dota_tournament"

WORKDIR /app
EXPOSE 8000
ENTRYPOINT ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]

# ---- Runtime for dev/test ----
FROM source-dev AS runtime-dev
LABEL org.opencontainers.image.source "https://github.com/kettleofketchup/dota_tournament"
WORKDIR /app
EXPOSE 8000
ENTRYPOINT ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]

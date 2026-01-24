# ---- Builder (production deps only) ----
FROM python:3.12-bookworm AS poetry
LABEL org.opencontainers.image.source "https://github.com/kettleofketchup/draftforge"
WORKDIR /app

RUN pip install poetry==2.1.2

# Create non-root user early so it's cached for all downstream stages
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home appuser

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


# ---- Runtime (production) ----
FROM deps AS runtime
LABEL org.opencontainers.image.source "https://github.com/kettleofketchup/draftforge"
WORKDIR /app

# Copy with ownership set directly (avoids slow recursive chown)
COPY --chown=appuser:appuser __init__.py paths.py tasks.py /app/
COPY --chown=appuser:appuser ./scripts /app/scripts
COPY --chown=appuser:appuser ./backend /app/backend

WORKDIR /app/backend
EXPOSE 8000
USER appuser
ENTRYPOINT ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]

# ---- Runtime for dev/test ----
FROM deps-dev AS runtime-dev
LABEL org.opencontainers.image.source "https://github.com/kettleofketchup/draftforge"
WORKDIR /app

# Copy with ownership set directly (avoids slow recursive chown)
COPY --chown=appuser:appuser __init__.py paths.py tasks.py /app/
COPY --chown=appuser:appuser ./scripts /app/scripts
COPY --chown=appuser:appuser ./backend /app/backend

WORKDIR /app/backend
EXPOSE 8000
USER appuser
ENTRYPOINT ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]

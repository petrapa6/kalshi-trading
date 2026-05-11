FROM python:3.13.3-slim-bookworm@sha256:8bc60ca09afaa8ea0d6d1220bde073bacfedd66a4bf8129cbdc8ef0e16c8a952

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install third-party dependencies only (cached layer — busts on lockfile change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy app code (bust cache via ARG)
ARG CACHE_BUST=0
COPY src/ ./src/

# Install the predictions package itself now that src/ is present
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "uvicorn", "predictions.api:app", "--host", "0.0.0.0", "--port", "8000"]

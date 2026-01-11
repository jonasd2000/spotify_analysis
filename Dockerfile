# Install uv
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y build-essential python3-dev

# to install python from uv to app folder
# to get fully contained environment
ENV UV_PYTHON_INSTALL_DIR="/app"
ENV UV_MANAGED_PYTHON=1

# Change the working directory to the `app` directory
WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# Copy the project into the intermediate image
COPY . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python:3.12-slim AS runtime

ENV IS_PRODUCTION=1

# Copy the environment, but not the source code
COPY --from=builder --chown=app:app /app /app

EXPOSE 8080

# Run the application
CMD ["/app/.venv/bin/spotify-analysis"]
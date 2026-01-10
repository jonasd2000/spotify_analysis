FROM ghcr.io/astral-sh/uv:debian-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential python3-dev

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy the project into the image
COPY . .

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# default nicegui port
EXPOSE 8080

CMD ["uv", "run", "./main.py"]
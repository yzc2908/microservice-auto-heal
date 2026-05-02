FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir -e ".[dev]"

COPY src/ ./src/
COPY tests/ ./tests/

RUN useradd -m -u 1000 autoheal && chown -R autoheal:autoheal /app
USER autoheal

ENTRYPOINT ["auto-heal"]
CMD ["poll", "--workspace", "/workspace", "--interval", "300"]

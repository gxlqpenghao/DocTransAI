FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY contracts ./contracts
RUN pip install --no-cache-dir uv==0.12.19 && uv sync --locked --no-dev --python /usr/local/bin/python
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/app/.venv/bin/doctransai"]

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc poppler-utils fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY contracts ./contracts
RUN pip install --no-cache-dir . pdf2image==1.17.0
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src DOCTRANSAI_RENDER_PYTHON=python \
    DOCTRANSAI_DOCX_RENDERER=/renderer/render_docx.py
ENTRYPOINT ["doctransai"]

# Deterministic production image for the backend.
#
# WHY THIS EXISTS: Coolify was building this app with Nixpacks, and the
# live 2026-07-13 PDF failure ("cannot load library 'libgobject-2.0-0'")
# proved backend/nixpacks.toml's aptPkgs never made it into the deployed
# image — libglib2.0-0 is a hard Depends: of libpango-1.0-0, so if that
# apt phase had run at all, libgobject would exist. Rather than debugging
# which config file which builder version reads, this Dockerfile makes
# the build explicit. In Coolify: backend app -> Build -> Build Pack =
# "Dockerfile" (base directory /backend), then redeploy and confirm the
# apt-get layer appears in the build log.
#
# Chromium is deliberately NOT installed — WeasyPrint is the production
# PDF engine (PDF_ENGINE defaults to weasyprint in core/config.py);
# Chromium with its ~40 shared-library deps stays a local/dev engine.
FROM python:3.11-slim

# WeasyPrint's system libraries. libglib2.0-0 listed explicitly — it
# provides libgobject-2.0.so.0, the exact library named in the live
# failure. fonts-dejavu-core gives text rendering a real default font.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first so code-only changes reuse the pip layer cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Shell form so Coolify's $PORT is honored when set (Render did the same
# via render.yaml's startCommand); 8000 otherwise.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}

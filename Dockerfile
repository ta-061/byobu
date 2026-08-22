FROM node:26-alpine AS pdfjs

# keep in sync with PDFJS_VERSION in src/kogo/cli.py
ARG PDFJS_VERSION=6.2.108
WORKDIR /pdfjs
RUN npm pack "pdfjs-dist@${PDFJS_VERSION}" --silent \
    && mkdir package \
    && tar -xzf pdfjs-dist-*.tgz -C package --strip-components=1


FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JOBS_DIR=/data/jobs

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY --from=pdfjs /pdfjs/package/build/pdf.min.mjs ./src/kogo/server/static/vendor/pdfjs/build/pdf.mjs
COPY --from=pdfjs /pdfjs/package/build/pdf.worker.min.mjs ./src/kogo/server/static/vendor/pdfjs/build/pdf.worker.mjs
COPY --from=pdfjs /pdfjs/package/web/pdf_viewer.mjs ./src/kogo/server/static/vendor/pdfjs/web/pdf_viewer.mjs
COPY --from=pdfjs /pdfjs/package/web/pdf_viewer.css ./src/kogo/server/static/vendor/pdfjs/web/pdf_viewer.css
COPY --from=pdfjs /pdfjs/package/web/images ./src/kogo/server/static/vendor/pdfjs/web/images
COPY --from=pdfjs /pdfjs/package/cmaps ./src/kogo/server/static/vendor/pdfjs/cmaps
COPY --from=pdfjs /pdfjs/package/standard_fonts ./src/kogo/server/static/vendor/pdfjs/standard_fonts
COPY --from=pdfjs /pdfjs/package/wasm ./src/kogo/server/static/vendor/pdfjs/wasm
COPY --from=pdfjs /pdfjs/package/LICENSE ./src/kogo/server/static/vendor/pdfjs/LICENSE

RUN pip install --no-cache-dir '.[serve]'

RUN addgroup --system --gid 10001 kogo \
    && adduser --system --uid 10001 --ingroup kogo kogo \
    && mkdir -p /data/jobs \
    && chown -R kogo:kogo /data

USER kogo
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["kogo", "serve", "--host", "0.0.0.0", "--port", "8080"]

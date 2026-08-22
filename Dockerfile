FROM node:24-alpine AS pdfjs

# keep in sync with PDFJS_VERSION in src/byobu/cli.py
ARG PDFJS_VERSION=6.2.108
WORKDIR /pdfjs
RUN npm pack "pdfjs-dist@${PDFJS_VERSION}" --silent \
    && mkdir package \
    && tar -xzf pdfjs-dist-*.tgz -C package --strip-components=1


FROM python:3.12-slim

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
COPY --from=pdfjs /pdfjs/package/build/pdf.min.mjs ./src/byobu/server/static/vendor/pdfjs/build/pdf.mjs
COPY --from=pdfjs /pdfjs/package/build/pdf.worker.min.mjs ./src/byobu/server/static/vendor/pdfjs/build/pdf.worker.mjs
COPY --from=pdfjs /pdfjs/package/web/pdf_viewer.mjs ./src/byobu/server/static/vendor/pdfjs/web/pdf_viewer.mjs
COPY --from=pdfjs /pdfjs/package/web/pdf_viewer.css ./src/byobu/server/static/vendor/pdfjs/web/pdf_viewer.css
COPY --from=pdfjs /pdfjs/package/web/images ./src/byobu/server/static/vendor/pdfjs/web/images
COPY --from=pdfjs /pdfjs/package/cmaps ./src/byobu/server/static/vendor/pdfjs/cmaps
COPY --from=pdfjs /pdfjs/package/standard_fonts ./src/byobu/server/static/vendor/pdfjs/standard_fonts
COPY --from=pdfjs /pdfjs/package/wasm ./src/byobu/server/static/vendor/pdfjs/wasm
COPY --from=pdfjs /pdfjs/package/LICENSE ./src/byobu/server/static/vendor/pdfjs/LICENSE

RUN pip install --no-cache-dir '.[serve]'

RUN addgroup --system --gid 10001 byobu \
    && adduser --system --uid 10001 --ingroup byobu byobu \
    && mkdir -p /data/jobs \
    && chown -R byobu:byobu /data

USER byobu
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["byobu", "serve", "--host", "0.0.0.0", "--port", "8080"]

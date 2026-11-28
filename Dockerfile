FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS web
WORKDIR /work
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS static-tools-amd64
ADD --checksum=sha256:551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz /tmp/gitleaks.tgz
ADD --checksum=sha256:fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8 https://github.com/google/osv-scanner/releases/download/v2.7.1/osv-scanner_linux_amd64 /tools/osv-scanner

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS static-tools-arm64
ADD --checksum=sha256:e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080 https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_arm64.tar.gz /tmp/gitleaks.tgz
ADD --checksum=sha256:983d22fbad9724514e3fcc6acc83b5fa64c5ffa6b0d9f510028f22c1b223ff81 https://github.com/google/osv-scanner/releases/download/v2.7.1/osv-scanner_linux_arm64 /tools/osv-scanner

FROM static-tools-${TARGETARCH} AS static-tools
RUN tar -xzf /tmp/gitleaks.tgz -C /tools gitleaks LICENSE \
    && mv /tools/LICENSE /tools/Gitleaks-LICENSE \
    && chmod 0555 /tools/gitleaks /tools/osv-scanner
ADD --chmod=0444 --checksum=sha256:cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30 https://raw.githubusercontent.com/google/osv-scanner/v2.7.1/LICENSE /tools/OSV-Scanner-LICENSE
ADD --checksum=sha256:fc59fe15b782dd1ed7db71464d4a70268dac9ee3ab595da28875ad5756896834 https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip?generation=1795219387680825 /osv/osv-scalibr/PyPI/all.zip
RUN chmod 0444 /osv/osv-scalibr/PyPI/all.zip \
    && python -c "from pathlib import Path; Path('/osv/database-date').write_text('2026-11-21\\n', encoding='ascii')"

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS runtime
WORKDIR /srv/basira
COPY requirements.txt .
# pip check fails the build when the pinned requirements do not resolve together.
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY backend/ ./backend/
COPY ops/init-model-vault.py ops/migrate-platform.py ./ops/
COPY alembic.ini ./
COPY --from=web /work/dist ./frontend/dist
COPY --from=static-tools /tools/ /opt/basira-tools/
COPY --from=static-tools /osv/ /opt/basira-osv/
ENV BASIRA_DB_PATH=/srv/basira/data/basira.sqlite3 \
    PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 basira && useradd --uid 10001 --gid 10001 --no-create-home basira \
    && mkdir -p /srv/basira/data /srv/basira/spool /srv/basira/model-secrets \
    && chown -R basira:basira /srv/basira/data /srv/basira/spool /srv/basira/model-secrets \
    && chmod 0700 /srv/basira/model-secrets
USER basira
EXPOSE 8000
# Compose and Docker can now restart or route around a hung process instead of
# a container that only looks up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/product', timeout=3)"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--no-access-log", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS npm-advisories
ADD --checksum=sha256:64021a51406b00b341f9b5b4e8428cec210404db3a857d4f9ff8cb2767091e24 https://osv-vulnerabilities.storage.googleapis.com/npm/all.zip?generation=1795332791486905 /tmp/npm.zip
COPY ops/index-npm-advisories.py /tmp/index-npm-advisories.py
RUN python /tmp/index-npm-advisories.py /tmp/npm.zip /index/npm-advisories.sqlite3 \
    && printf '%s\n' '2026-11-22' > /index/npm-database-date \
    && chmod 0444 /index/npm-advisories.sqlite3 /index/npm-database-date

FROM runtime AS scanner-npm
COPY --from=npm-advisories /index/ /opt/basira-osv/

FROM runtime AS app

FROM node:22-bookworm-slim AS web
WORKDIR /work
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS static-tools-amd64
ADD --checksum=sha256:551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz /tmp/gitleaks.tgz
ADD --checksum=sha256:fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8 https://github.com/google/osv-scanner/releases/download/v2.7.1/osv-scanner_linux_amd64 /tools/osv-scanner

FROM python:3.13-slim AS static-tools-arm64
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

FROM python:3.13-slim
WORKDIR /srv/marsad
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY ops/init-model-vault.py ops/migrate-platform.py ./ops/
COPY alembic.ini ./
COPY --from=web /work/dist ./frontend/dist
COPY --from=static-tools /tools/ /opt/marsad-tools/
COPY --from=static-tools /osv/ /opt/marsad-osv/
ENV MARSAD_DB_PATH=/srv/marsad/data/marsad.sqlite3
RUN groupadd --gid 10001 marsad && useradd --uid 10001 --gid 10001 --no-create-home marsad \
    && mkdir -p /srv/marsad/data /srv/marsad/spool /srv/marsad/model-secrets \
    && chown -R marsad:marsad /srv/marsad/data /srv/marsad/spool /srv/marsad/model-secrets \
    && chmod 0700 /srv/marsad/model-secrets
USER marsad
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--no-access-log", "--host", "0.0.0.0", "--port", "8000"]

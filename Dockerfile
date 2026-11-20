FROM node:22-bookworm-slim AS web
WORKDIR /work
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /srv/marsad
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY alembic.ini ./
COPY --from=web /work/dist ./frontend/dist
ENV MARSAD_DB_PATH=/srv/marsad/data/marsad.sqlite3
RUN groupadd --gid 10001 marsad && useradd --uid 10001 --gid 10001 --no-create-home marsad \
    && mkdir -p /srv/marsad/data /srv/marsad/spool && chown -R marsad:marsad /srv/marsad/data /srv/marsad/spool
USER marsad
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--no-access-log", "--host", "0.0.0.0", "--port", "8000"]

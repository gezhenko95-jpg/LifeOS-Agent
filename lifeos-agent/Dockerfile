FROM python:3.11-slim

# tzdata — без него ENV TZ (см. docker-compose.yml) молча не применится:
# python:slim не включает базу IANA-таймзон по умолчанию, а без неё
# datetime.now().astimezone()/date.today() внутри контейнера всегда
# читают UTC, даже если TZ выставлен (баг, из-за которого все
# ежедневные сообщения приходили на 3 часа позже ожидаемого).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
# scripts/ нужен в образе ради scripts/backup_upload.py — его запускает
# docker exec из хостового scripts/backup_db.sh (см. docker-compose.yml).
COPY scripts ./scripts
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

EXPOSE 8000

# --proxy-headers/--forwarded-allow-ips — без них uvicorn не знает про
# X-Forwarded-Proto от Caddy (см. docker-compose.yml на VPS) и генерирует
# редиректы (например, /ui -> /ui/) с http:// вместо https://.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

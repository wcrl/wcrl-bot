FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ is a mount point for the SQLite volume; owned by the runtime user so
# the bot can create wcrl.db and its -wal/-shm sidecars.
RUN useradd --create-home --uid 1000 wcrl \
    && mkdir -p /app/data \
    && chown -R wcrl:wcrl /app
USER wcrl

# No EXPOSE: the bot is outbound-only (Discord gateway), no inbound port.
CMD ["python", "bot.py"]

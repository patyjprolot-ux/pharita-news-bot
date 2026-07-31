FROM python:3.11-slim

# Playwright (для TikTok-источника, если включён) требует системные библиотеки
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium || true

COPY . .

VOLUME ["/app/data"]

CMD ["python", "main.py"]

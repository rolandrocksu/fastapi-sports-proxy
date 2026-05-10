FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PROVIDER=openliga \
    RATE_LIMIT_RPS=5 \
    MAX_RETRIES=3 \
    BACKOFF_BASE_DELAY=0.5 \
    BACKOFF_MAX_DELAY=10.0 \
    LOG_BODY_MAX_CHARS=200

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

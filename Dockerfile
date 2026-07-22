FROM python:3.12-alpine

# Non-root user — the app has no reason to run as root
RUN addgroup -S app && adduser -S app -G app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html ./

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8080/api/status || exit 1

# 2 gunicorn workers is enough for a demo app; --threads lets each worker
# handle the /api/status polling without blocking on a stress request.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "app:app"]
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODELS_DIR=/app/models

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Qur'an text and app code. Models are NOT baked in: they are downloaded on the
# first start into the mounted ./models folder and reused afterwards.
COPY data/ ./data
COPY app/ ./app
COPY qa/ ./qa

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

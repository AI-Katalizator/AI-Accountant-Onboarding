# docreader — чтение УПД/актов/накладных/договоров/доверенностей для сценариев AI-Accountant-1C.
# Образ для клиентов: Debian slim + Python 3.12, все пакеты со свободными лицензиями (см. NOTICE).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8011 FILES_ROOTS=/files
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng ocrmypdf unpaper ghostscript \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /srv/requirements.txt
RUN pip install -r /srv/requirements.txt
COPY app /srv/app
COPY definitions /srv/definitions
COPY NOTICE LICENSE /srv/
EXPOSE 8011
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8011/health',timeout=4)"
CMD ["python", "-m", "app.server"]

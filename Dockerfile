FROM python:3.11-slim

LABEL maintainer="LOUPZ GmbH & Co. KG"
LABEL description="Microsoft-zu-Notion Migration Suite — Web-GUI"

# System-Dependencies fuer lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies zuerst (Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir gunicorn && \
    pip install --no-cache-dir \
        $(grep -v -E '^\s*#|black|ruff|mypy|pytest' requirements.txt | tr '\n' ' ')

# Anwendungscode
COPY core/ core/
COPY tools/ tools/
COPY web/ web/
COPY documentation/ documentation/

ENV PYTHONUNBUFFERED=1
ENV FLASK_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')" || exit 1

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--threads", "24", \
     "--timeout", "900", \
     "--access-logfile", "-", \
     "web.app:app"]

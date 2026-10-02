ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/teachbuddy
COPY requirements-web.txt .
RUN pip install -r requirements-web.txt && useradd --uid 10001 --create-home teachbuddy
COPY app/__init__.py app/config.py ./app/
COPY app/core ./app/core
COPY app/resources ./app/resources
COPY web ./web
RUN mkdir -p /srv/data && chown -R teachbuddy:teachbuddy /srv/data
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
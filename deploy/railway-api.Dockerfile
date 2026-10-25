FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements-f2.lock requirements-f5.txt ./
RUN pip install --no-cache-dir -r requirements-f5.txt \
    && python -c "import psycopg_pool; from psycopg_pool import ConnectionPool"
COPY app/ ./app/
COPY migrations/ ./migrations/
CMD ["sh","-c","exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
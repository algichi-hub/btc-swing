FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements-f2.lock ./
RUN pip install --no-cache-dir -r requirements-f2.lock
COPY app/ ./app/
COPY migrations/ ./migrations/
CMD ["python","-m","app.automation.cloud_worker"]
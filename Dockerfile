FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Cài dependencies trước để tận dụng layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (db.sqlite/.env bị loại qua .dockerignore)
COPY . .

CMD ["python", "main.py"]

# app/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей для OpenCV, PostgreSQL и TensorFlow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование всего проекта
COPY . .

# Создаем скрипт для запуска приложения
RUN echo '#!/bin/bash' > /app/entrypoint.sh && \
    echo 'set -e' >> /app/entrypoint.sh && \
    echo '' >> /app/entrypoint.sh && \
    echo '# Ждем готовности базы данных' >> /app/entrypoint.sh && \
    echo 'echo "Waiting for database..."' >> /app/entrypoint.sh && \
    echo 'while ! pg_isready -h db -p 5432 -U postgres; do' >> /app/entrypoint.sh && \
    echo '  sleep 1' >> /app/entrypoint.sh && \
    echo 'done' >> /app/entrypoint.sh && \
    echo 'echo "Database is ready!"' >> /app/entrypoint.sh && \
    echo '' >> /app/entrypoint.sh && \
    echo '# Запускаем миграции' >> /app/entrypoint.sh && \
    echo 'echo "Running migrations..."' >> /app/entrypoint.sh && \
    echo 'python create_tables.py || echo "Tables already exist"' >> /app/entrypoint.sh && \
    echo 'python add_chat_tables.py || echo "Chat tables already exist"' >> /app/entrypoint.sh && \
    echo 'python simplified_add_chat_tables.py || echo "Simplified chat tables already exist"' >> /app/entrypoint.sh && \
    echo 'python update_user_status_fields.py || echo "User status fields already exist"' >> /app/entrypoint.sh && \
    echo 'python create_founded_pets_table.py || echo "Founded pets table already exist"' >> /app/entrypoint.sh && \
    echo 'echo "All migrations completed!"' >> /app/entrypoint.sh && \
    echo '' >> /app/entrypoint.sh && \
    echo '# Запускаем приложение' >> /app/entrypoint.sh && \
    echo 'echo "Starting FastAPI application..."' >> /app/entrypoint.sh && \
    echo 'uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-use-colors' >> /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

# Устанавливаем pg_isready для проверки готовности базы данных
RUN apt-get update && apt-get install -y postgresql-client && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Переменные окружения для TensorFlow
ENV CUDA_VISIBLE_DEVICES="-1"
ENV TF_FORCE_GPU_ALLOW_GROWTH="true"
ENV TF_CPP_MIN_LOG_LEVEL="2"
ENV PYTHONUNBUFFERED=1
ENV DOCKER_ENV="true"

# Порт для FastAPI
EXPOSE 8000

# Запуск через entrypoint скрипт
CMD ["/app/entrypoint.sh"]
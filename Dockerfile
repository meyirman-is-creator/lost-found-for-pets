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
    postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование всего проекта
COPY . .

# Создаем универсальный скрипт запуска
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Функция для проверки подключения к БД' >> /app/start.sh && \
    echo 'wait_for_db() {' >> /app/start.sh && \
    echo '    echo "Checking database connection..."' >> /app/start.sh && \
    echo '    python -c "' >> /app/start.sh && \
    echo 'import time' >> /app/start.sh && \
    echo 'import os' >> /app/start.sh && \
    echo 'from sqlalchemy import create_engine' >> /app/start.sh && \
    echo 'db_url = os.getenv(\"DATABASE_URL\", \"postgresql://postgres:postgres@localhost:5432/lostpets_db\")' >> /app/start.sh && \
    echo 'if db_url.startswith(\"postgres://\"):' >> /app/start.sh && \
    echo '    db_url = db_url.replace(\"postgres://\", \"postgresql://\", 1)' >> /app/start.sh && \
    echo 'max_retries = 30' >> /app/start.sh && \
    echo 'for i in range(max_retries):' >> /app/start.sh && \
    echo '    try:' >> /app/start.sh && \
    echo '        engine = create_engine(db_url)' >> /app/start.sh && \
    echo '        with engine.connect() as conn:' >> /app/start.sh && \
    echo '            conn.execute(\"SELECT 1\")' >> /app/start.sh && \
    echo '        print(\"Database is ready!\")' >> /app/start.sh && \
    echo '        break' >> /app/start.sh && \
    echo '    except Exception as e:' >> /app/start.sh && \
    echo '        if i == max_retries - 1:' >> /app/start.sh && \
    echo '            print(f\"Failed to connect to database: {e}\")' >> /app/start.sh && \
    echo '            exit(1)' >> /app/start.sh && \
    echo '        print(f\"Waiting for database... ({i+1}/{max_retries})\")' >> /app/start.sh && \
    echo '        time.sleep(2)' >> /app/start.sh && \
    echo '"' >> /app/start.sh && \
    echo '}' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Проверяем подключение к БД' >> /app/start.sh && \
    echo 'wait_for_db' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Создаем таблицы через основное приложение' >> /app/start.sh && \
    echo 'echo "Initializing database tables..."' >> /app/start.sh && \
    echo 'python -c "' >> /app/start.sh && \
    echo 'from app.db.database import engine, Base' >> /app/start.sh && \
    echo 'from app.models import models' >> /app/start.sh && \
    echo 'try:' >> /app/start.sh && \
    echo '    Base.metadata.create_all(bind=engine)' >> /app/start.sh && \
    echo '    print(\"Database tables created/verified successfully!\")' >> /app/start.sh && \
    echo 'except Exception as e:' >> /app/start.sh && \
    echo '    print(f\"Warning during table creation: {e}\")' >> /app/start.sh && \
    echo '"' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Запускаем приложение' >> /app/start.sh && \
    echo 'echo "Starting FastAPI application..."' >> /app/start.sh && \
    echo 'PORT=${PORT:-8000}' >> /app/start.sh && \
    echo 'echo "Running on port: $PORT"' >> /app/start.sh && \
    echo 'exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-use-colors' >> /app/start.sh && \
    chmod +x /app/start.sh

# Переменные окружения для TensorFlow
ENV CUDA_VISIBLE_DEVICES="-1"
ENV TF_FORCE_GPU_ALLOW_GROWTH="true"
ENV TF_CPP_MIN_LOG_LEVEL="2"
ENV PYTHONUNBUFFERED=1

# Railway устанавливает PORT автоматически
EXPOSE 8000

# Запуск через скрипт
CMD ["/app/start.sh"]
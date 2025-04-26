# app/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей для OpenCV, PostgreSQL и TensorFlow
# Добавлен curl для healthcheck
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

# Установка uvicorn с поддержкой websockets и SQLAlchemy сначала
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "uvicorn[standard]>=0.27.0" websockets>=11.0.3 sqlalchemy>=2.0.0

# Установка TensorFlow и связанных библиотек
RUN pip install --no-cache-dir \
    tensorflow==2.15.0 \
    scikit-learn==1.0.2 \
    Pillow==9.5.0 \
    scipy==1.10.1 \
    numpy==1.24.3

# Установка остальных зависимостей из requirements.txt
RUN pip install --no-cache-dir --ignore-installed -r requirements.txt

# Копирование исходного кода приложения
COPY . .

# Переменная окружения для использования CPU вместо GPU
ENV CUDA_VISIBLE_DEVICES="-1"
ENV TF_FORCE_GPU_ALLOW_GROWTH="true"
ENV TF_CPP_MIN_LOG_LEVEL="2"
ENV PYTHONUNBUFFERED=1
ENV DOCKER_ENV="true"

# Установка переменной порта с значением по умолчанию
ENV PORT=8000

# Порт для FastAPI
EXPOSE 8000

# Запуск всех миграций перед запуском приложения
# Создаем единый скрипт для запуска всех миграций с безопасной проверкой
RUN echo '#!/bin/bash' > /app/run_migrations.sh && \
    echo 'set -e' >> /app/run_migrations.sh && \
    echo 'python create_tables.py' >> /app/run_migrations.sh && \
    echo 'python add_chat_tables.py' >> /app/run_migrations.sh && \
    echo 'python simplified_add_chat_tables.py' >> /app/run_migrations.sh && \
    echo 'python update_user_status_fields.py' >> /app/run_migrations.sh && \
    echo 'python create_founded_pets_table.py' >> /app/run_migrations.sh && \
    echo 'echo "All migrations completed successfully"' >> /app/run_migrations.sh && \
    chmod +x /app/run_migrations.sh

# Запуск миграций и приложения
CMD /app/run_migrations.sh && \
    python -c "import os; print('Starting app with DOCKER_ENV=', os.environ.get('DOCKER_ENV'))" && \
    uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-use-colors
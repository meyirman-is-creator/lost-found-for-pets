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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt
COPY requirements.txt .

# Установка основных зависимостей с актуальными версиями TensorFlow
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
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

# Порт для FastAPI
EXPOSE 8000

# Создание таблиц при запуске и запуск приложения
CMD python create_tables.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT
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

# Установка TensorFlow и основных зависимостей заранее
RUN pip install --no-cache-dir tensorflow==2.9.1 scikit-learn==1.0.2 Pillow==9.5.0 scipy==1.10.1 numpy==1.24.3

# Установка остальных зависимостей из requirements.txt, игнорируя ошибки совместимости
RUN pip install --no-cache-dir --ignore-installed \
    fastapi>=0.109.0 \
    uvicorn>=0.27.0 \
    pydantic>=2.5.3 \
    pydantic-settings>=2.1.0 \
    sqlalchemy>=2.0.25 \
    psycopg2-binary>=2.9.9 \
    python-multipart>=0.0.6 \
    python-jose[cryptography]>=3.3.0 \
    passlib[bcrypt]>=1.7.4 \
    python-dotenv>=1.0.0 \
    alembic>=1.13.1 \
    boto3>=1.34.14 \
    opencv-python>=4.9.0 \
    requests>=2.31.0

# Копирование исходного кода приложения
COPY . .

# Переменная окружения для использования CPU вместо GPU
ENV CUDA_VISIBLE_DEVICES="-1"
ENV TF_FORCE_GPU_ALLOW_GROWTH="true"
ENV TF_CPP_MIN_LOG_LEVEL="2"

# Порт для FastAPI
EXPOSE 8000

# Создание таблиц при запуске и запуск приложения
CMD python create_tables.py && uvicorn app.main:app --host 0.0.0.0 --port 8000
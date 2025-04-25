from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.db.database import engine, Base
from app.core.config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# Создание таблиц в базе данных
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем заглушку для similarity_service
class DummySimilarityService:
    def compute_similarity(self, img1_source, img2_source):
        logger.warning("TensorFlow not available, returning dummy similarity score.")
        return 0.5  # Возвращаем условное среднее значение

# Пытаемся загрузить настоящий сервис, а если не получится - используем заглушку
try:
    import tensorflow as tf
    from app.services.cv.similarity import similarity_service
    logger.info("TensorFlow loaded successfully")
except ImportError:
    logger.warning("TensorFlow not properly installed. Using dummy similarity service.")
    # Монтируем заглушку вместо реального сервиса
    import sys
    import app.services.cv
    if not hasattr(app.services.cv, 'similarity'):
        app.services.cv.similarity = type('', (), {})()
    app.services.cv.similarity.similarity_service = DummySimilarityService()

# Загружаем маршруты API
try:
    from app.api.api import api_router
    app.include_router(api_router, prefix=settings.API_V1_STR)
    logger.info("API routes loaded successfully")
except Exception as e:
    logger.error(f"Failed to load API routes: {e}")
    import traceback
    logger.error(traceback.format_exc())

@app.get("/")
def root():
    """
    Root endpoint to check if the API is running
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} {settings.PROJECT_VERSION}",
        "docs": f"{settings.API_V1_STR}/docs"
    }

@app.get("/health")
def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
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

# Переименовываем экземпляр FastAPI с app на fastapi_app
fastapi_app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# Настройка CORS
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Сначала импортируем заглушку для similarity_service
try:
    from app.services.cv.dummy_similarity import similarity_service

    logger.info("Dummy similarity service loaded successfully")
except ImportError as e:
    logger.error(f"Failed to load dummy similarity service: {e}")


    # Создаем локальную заглушку, если не удалось импортировать из файла
    class DummySimilarityService:
        def compute_similarity(self, img1_source, img2_source):
            logger.warning("Using inline dummy similarity service")
            return 0.5


    similarity_service = DummySimilarityService()

# Монтируем заглушку в правильный путь
import sys
import app.services.cv

if not hasattr(app.services.cv, 'similarity'):
    app.services.cv.similarity = type('', (), {})()
app.services.cv.similarity.similarity_service = similarity_service

# Загружаем маршруты API
try:
    from app.api.api import api_router

    fastapi_app.include_router(api_router, prefix=settings.API_V1_STR)
    logger.info("API routes loaded successfully")
except Exception as e:
    logger.error(f"Failed to load API routes: {e}")


@fastapi_app.get("/")
def root():
    """
    Root endpoint to check if the API is running
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} {settings.PROJECT_VERSION}",
        "docs": f"{settings.API_V1_STR}/docs"
    }


@fastapi_app.get("/health")
def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok"}
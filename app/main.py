from fastapi import FastAPI, Depends
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

# Подключение маршрутов API с обработкой ошибок импорта TensorFlow
try:
    from app.api.api import api_router

    app.include_router(api_router, prefix=settings.API_V1_STR)
    logger.info("API routes loaded successfully")
except ModuleNotFoundError as e:
    if "tensorflow.keras" in str(e):
        logger.error("TensorFlow not properly installed. Image similarity features will be unavailable.")
        logger.error("Please install TensorFlow with: pip install tensorflow-macos tensorflow-metal")

        # Try to load API routes without CV functionality
        try:
            # This is a placeholder - you would need to implement a version of your API
            # that doesn't depend on TensorFlow or handle it gracefully within your endpoints
            logger.warning("Attempting to load API with limited functionality...")

            # You could implement a simplified version of your API without the CV module
            # or modify your endpoints to handle the missing dependency gracefully
            from app.api.api import api_router  # You would need a version that handles the missing dependency

            app.include_router(api_router, prefix=settings.API_V1_STR)
        except Exception as inner_e:
            logger.error(f"Failed to load API with limited functionality: {inner_e}")
    else:
        logger.error(f"Module import error: {e}")


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
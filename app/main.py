from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.db.database import engine, Base
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

fastapi_app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    import tensorflow as tf
    from app.services.cv.similarity import similarity_service
    logger.info("TensorFlow loaded successfully")
except ImportError:
    logger.warning("TensorFlow not properly installed. Using dummy similarity service.")

try:
    from app.api.api import api_router
    fastapi_app.include_router(api_router, prefix=settings.API_V1_STR)
    logger.info("API routes loaded successfully")
except Exception as e:
    logger.error(f"Failed to load API routes: {e}")
    import traceback
    logger.error(traceback.format_exc())

@fastapi_app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} {settings.PROJECT_VERSION}",
        "docs": f"{settings.API_V1_STR}/docs"
    }

@fastapi_app.get("/health")
def health_check():
    return {"status": "ok"}

app = fastapi_app

if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
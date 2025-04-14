from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import os

# Определяем, запущено ли приложение в Docker или локально
in_docker = os.environ.get('DOCKER_ENV', False)

# Выбираем соответствующий URL для подключения к базе данных
if in_docker:
    db_url = settings.DATABASE_URL
else:
    db_url = settings.DATABASE_URL_LOCAL

# Создаем подключение к базе данных
engine = create_engine(db_url)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем функцию для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
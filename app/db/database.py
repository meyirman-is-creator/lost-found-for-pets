from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import os

# Для Railway всегда используем DATABASE_URL
# Railway автоматически устанавливает эту переменную
db_url = os.getenv("DATABASE_URL", settings.DATABASE_URL)

# Railway использует postgres://, но SQLAlchemy требует postgresql://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

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
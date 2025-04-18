from app.db.database import engine, Base
from app.models.models import Chat, ChatMessage
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_chat_tables():
    """
    Создает таблицы чата в базе данных, используя существующие модели
    """
    logger.info("Starting to create chat tables...")

    # Создаем таблицы из моделей
    # Base.metadata.create_all() создаст только те таблицы, которых еще нет в базе данных
    Base.metadata.create_all(bind=engine)

    logger.info("Chat tables created successfully!")


if __name__ == "__main__":
    create_chat_tables()
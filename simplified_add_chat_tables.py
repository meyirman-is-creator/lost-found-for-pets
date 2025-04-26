from app.db.database import engine, Base
from app.models.models import Chat, ChatMessage
import logging
import sqlalchemy as sa

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_chat_tables():
    """
    Создает таблицы чата в базе данных, используя существующие модели
    """
    logger.info("Starting to check for chat tables...")

    # Проверяем, существуют ли уже таблицы
    inspector = sa.inspect(engine)
    existing_tables = inspector.get_table_names()

    if 'chats' in existing_tables and 'chat_messages' in existing_tables:
        logger.info("Chat tables already exist. Skipping creation.")
        return

    logger.info("Creating chat tables...")

    # Создаем таблицы из моделей
    # Base.metadata.create_all() создаст только те таблицы, которых еще нет в базе данных
    Base.metadata.create_all(bind=engine, tables=[
        Base.metadata.tables["chats"],
        Base.metadata.tables["chat_messages"]
    ])

    logger.info("Chat tables created successfully!")


if __name__ == "__main__":
    create_chat_tables()
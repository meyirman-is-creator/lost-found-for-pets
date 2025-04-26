from app.db.database import engine, Base
from app.models.models import User, Pet
from sqlalchemy import Column, Integer, ForeignKey, Text, Boolean, DateTime, Table, MetaData, inspect
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import sqlalchemy as sa
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_chat_tables():
    logger.info("Starting migration to add chat tables...")

    # Проверяем, существуют ли уже таблицы
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if 'chats' in existing_tables and 'chat_messages' in existing_tables:
        logger.info("Chat tables already exist. Skipping migration.")
        return

    # Динамически добавляем классы моделей в метаданные, если их еще нет
    class Chat(Base):
        __tablename__ = "chats"

        id = Column(Integer, primary_key=True, index=True)
        created_at = Column(DateTime, default=func.now())
        updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
        user1_id = Column(Integer, ForeignKey("users.id"))
        user2_id = Column(Integer, ForeignKey("users.id"))
        pet_id = Column(Integer, ForeignKey("pets.id"), nullable=True)

    class ChatMessage(Base):
        __tablename__ = "chat_messages"

        id = Column(Integer, primary_key=True, index=True)
        chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
        sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        content = Column(Text, nullable=False)
        is_read = Column(Boolean, default=False)
        created_at = Column(DateTime, default=func.now())

    # Создаем только новые таблицы
    try:
        logger.info("Creating chat tables...")
        Base.metadata.create_all(engine, tables=[
            Base.metadata.tables["chats"],
            Base.metadata.tables["chat_messages"]
        ])
        logger.info("Chat tables created successfully!")
    except Exception as e:
        logger.error(f"Error creating chat tables: {e}")


if __name__ == "__main__":
    create_chat_tables()
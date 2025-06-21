"""
Добавляет поле whoid в таблицу chat_messages
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем URL базы данных
DATABASE_URL = os.getenv("DATABASE_URL", os.getenv("DATABASE_URL_LOCAL"))
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    logger.error("DATABASE_URL not found!")
    sys.exit(1)

# Создаем подключение к БД
engine = create_engine(DATABASE_URL)


def add_whoid_column():
    """Добавляет колонку whoid в таблицу chat_messages"""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Проверяем, существует ли колонка
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('chat_messages')]

            if 'whoid' in columns:
                logger.info("Column 'whoid' already exists in chat_messages table")
                trans.commit()
                return

            logger.info("Adding 'whoid' column to chat_messages table...")

            # Добавляем колонку как nullable
            conn.execute(text("""
                ALTER TABLE chat_messages 
                ADD COLUMN whoid INTEGER
            """))

            # Добавляем foreign key
            conn.execute(text("""
                ALTER TABLE chat_messages 
                ADD CONSTRAINT fk_chat_messages_whoid_users 
                FOREIGN KEY (whoid) REFERENCES users(id)
            """))

            # Заполняем whoid значениями
            conn.execute(text("""
                UPDATE chat_messages cm
                SET whoid = CASE
                    WHEN cm.sender_id = c.user1_id THEN c.user2_id
                    WHEN cm.sender_id = c.user2_id THEN c.user1_id
                    ELSE cm.sender_id
                END
                FROM chats c
                WHERE cm.chat_id = c.id AND cm.whoid IS NULL
            """))

            # Делаем колонку NOT NULL
            conn.execute(text("""
                ALTER TABLE chat_messages 
                ALTER COLUMN whoid SET NOT NULL
            """))

            trans.commit()
            logger.info("✅ Successfully added 'whoid' column to chat_messages table")

        except ProgrammingError as e:
            trans.rollback()
            if "already exists" in str(e):
                logger.info("Column 'whoid' already exists")
            else:
                logger.error(f"Error adding column: {e}")
                raise
        except Exception as e:
            trans.rollback()
            logger.error(f"Unexpected error: {e}")
            raise


if __name__ == "__main__":
    try:
        add_whoid_column()
        logger.info("Migration completed successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
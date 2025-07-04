# Путь: update_user_status_fields.py

from app.db.database import engine, Base
from app.models.models import User
from sqlalchemy import Column, Boolean, DateTime
import sqlalchemy as sa
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_user_status_fields():
    logger.info("Starting migration to add user status fields...")

    # Проверяем, существуют ли уже колонки
    inspector = sa.inspect(engine)
    columns = inspector.get_columns('users')
    column_names = [col['name'] for col in columns]

    if 'is_online' in column_names and 'last_active_at' in column_names:
        logger.info("User status fields already exist. Skipping migration.")
        return

    with engine.begin() as conn:
        # Добавляем поле is_online, если его еще нет
        if 'is_online' not in column_names:
            logger.info("Adding is_online column to users table...")
            conn.execute(sa.text(
                "ALTER TABLE users ADD COLUMN is_online BOOLEAN DEFAULT FALSE"
            ))
            logger.info("is_online column added successfully.")
        else:
            logger.info("is_online column already exists, skipping.")

        # Добавляем поле last_active_at, если его еще нет
        if 'last_active_at' not in column_names:
            logger.info("Adding last_active_at column to users table...")
            conn.execute(sa.text(
                "ALTER TABLE users ADD COLUMN last_active_at TIMESTAMP"
            ))
            logger.info("last_active_at column added successfully.")
        else:
            logger.info("last_active_at column already exists, skipping.")

    logger.info("User status fields migration completed!")


if __name__ == "__main__":
    add_user_status_fields()
from app.db.database import engine, Base, SessionLocal
from app.models.models import Pet, User
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Table, MetaData, inspect
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import sqlalchemy as sa
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Определение новой таблицы с использованием метаданных SQLAlchemy
metadata = MetaData()
founded_pets = Table(
    "founded_pets",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("pet_id", Integer, ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
    Column("coordX", String, nullable=True),
    Column("coordY", String, nullable=True),
    Column("created_at", DateTime, server_default=func.now())
)


def create_founded_pets_table():
    """
    Создает таблицу founded_pets и переносит данные из полей coordX и coordY таблицы pets
    """
    inspector = sa.inspect(engine)
    existing_tables = inspector.get_table_names()

    # Проверяем, существует ли уже таблица
    if "founded_pets" in existing_tables:
        logger.info("Таблица founded_pets уже существует. Пропускаем миграцию.")
        return

    with engine.begin() as conn:
        # Проверяем наличие полей coordX и coordY в таблице pets
        columns = inspector.get_columns('pets')
        column_names = [col['name'] for col in columns]
        has_coord_fields = 'coordX' in column_names and 'coordY' in column_names

        # Создаем новую таблицу
        logger.info("Создание таблицы founded_pets...")
        founded_pets.create(conn)
        logger.info("Таблица founded_pets успешно создана")

        # Если есть поля с координатами, переносим данные
        if has_coord_fields:
            logger.info("Перенос данных из полей координат в новую таблицу...")

            # Получаем все записи с координатами
            result = conn.execute(sa.text(
                "SELECT id, \"coordX\", \"coordY\" FROM pets WHERE \"coordX\" IS NOT NULL OR \"coordY\" IS NOT NULL"
            ))
            rows = result.fetchall()

            # Вставляем данные в новую таблицу
            for row in rows:
                pet_id, coordX, coordY = row
                if coordX or coordY:
                    conn.execute(
                        sa.text(
                            "INSERT INTO founded_pets (pet_id, \"coordX\", \"coordY\") VALUES (:pet_id, :coordX, :coordY)"
                        ),
                        {"pet_id": pet_id, "coordX": coordX, "coordY": coordY}
                    )

            logger.info(f"Перенесено {len(rows)} записей с координатами")

            # Удаляем поля coordX и coordY из таблицы pets
            logger.info("Удаление полей coordX и coordY из таблицы pets...")
            try:
                conn.execute(sa.text('ALTER TABLE pets DROP COLUMN IF EXISTS "coordX"'))
                conn.execute(sa.text('ALTER TABLE pets DROP COLUMN IF EXISTS "coordY"'))
                logger.info("Поля координат успешно удалены")
            except Exception as e:
                logger.error(f"Ошибка при удалении полей координат: {e}")

    logger.info("Миграция успешно завершена")


if __name__ == "__main__":
    create_founded_pets_table()
# add_pet_coordinates.py
from app.db.database import engine
import sqlalchemy as sa
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_pet_coordinates():
    logger.info("Starting migration to add pet coordinates fields...")

    # Проверяем, существуют ли уже колонки
    inspector = sa.inspect(engine)
    columns = inspector.get_columns('pets')
    column_names = [col['name'] for col in columns]  # Не приводим к нижнему регистру

    logger.info(f"Existing columns: {column_names}")

    with engine.begin() as conn:
        try:
            # Добавляем поле coordX, если его еще нет
            if 'coordX' not in column_names:
                logger.info("Adding coordX column to pets table...")
                conn.execute(sa.text(
                    'ALTER TABLE pets ADD COLUMN "coordX" VARCHAR'
                ))
            else:
                logger.info("Column coordX already exists in pets table")

            # Добавляем поле coordY, если его еще нет
            if 'coordY' not in column_names:
                logger.info("Adding coordY column to pets table...")
                conn.execute(sa.text(
                    'ALTER TABLE pets ADD COLUMN "coordY" VARCHAR'
                ))
            else:
                logger.info("Column coordY already exists in pets table")
        except Exception as e:
            # Логируем ошибку подробно
            logger.error(f"Error adding columns: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise  # Останавливаем выполнение в случае ошибки

    logger.info("Pet coordinates fields migration completed!")


if __name__ == "__main__":
    add_pet_coordinates()
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
    column_names = [col['name'] for col in columns]

    with engine.begin() as conn:
        # Добавляем поле coordX, если его еще нет
        if 'coordX' not in column_names:
            logger.info("Adding coordX column to pets table...")
            conn.execute(sa.text(
                "ALTER TABLE pets ADD COLUMN coordX VARCHAR"
            ))

        # Добавляем поле coordY, если его еще нет
        if 'coordY' not in column_names:
            logger.info("Adding coordY column to pets table...")
            conn.execute(sa.text(
                "ALTER TABLE pets ADD COLUMN coordY VARCHAR"
            ))

    logger.info("Pet coordinates fields added successfully!")


if __name__ == "__main__":
    add_pet_coordinates()
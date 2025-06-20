from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.append(str(Path(__file__).parent.parent))

# Импортируем модели и базу данных
from app.db.database import Base
from app.models.models import *
from app.core.config import settings

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = Base.metadata


def get_database_url():
    """Get database URL from environment or config"""
    # Для локальной разработки
    db_url = "postgresql://postgres:postgres@localhost:5432/lostpets_db"

    # Если есть переменная окружения DATABASE_URL_LOCAL
    if os.getenv("DATABASE_URL_LOCAL"):
        db_url = os.getenv("DATABASE_URL_LOCAL")

    # Если мы в Railway (есть DATABASE_URL)
    if os.getenv("DATABASE_URL"):
        db_url = os.getenv("DATABASE_URL")

    # Railway использует postgres://, но SQLAlchemy требует postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    print(f"Using database URL: {db_url[:30]}...")  # Показываем только начало URL для безопасности
    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
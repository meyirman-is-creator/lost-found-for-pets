#!/bin/bash
set -e

echo "Running database migrations..."

# Запускаем все миграции по порядку
python create_tables.py
python add_chat_tables.py
python simplified_add_chat_tables.py
python update_user_status_fields.py
python create_founded_pets_table.py
python add_whoid_to_chat_messages.py  # Новая миграция

echo "All migrations completed successfully"

# Запускаем приложение
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-use-colors
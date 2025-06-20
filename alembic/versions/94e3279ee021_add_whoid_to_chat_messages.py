"""add_whoid_to_chat_messages

Revision ID: 94e3279ee021
Revises: 
Create Date: 2025-06-21 03:12:11.779110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94e3279ee021'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляем поле whoid в таблицу chat_messages"""

    # Проверяем, существует ли уже колонка
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Получаем список колонок таблицы
    columns = [col['name'] for col in inspector.get_columns('chat_messages')]

    # Если колонки нет, добавляем её
    if 'whoid' not in columns:
        # 1. Добавляем колонку whoid (сначала как nullable)
        op.add_column('chat_messages',
            sa.Column('whoid', sa.Integer(), nullable=True)
        )

        # 2. Создаем foreign key на таблицу users
        op.create_foreign_key(
            'fk_chat_messages_whoid_users',  # имя constraint
            'chat_messages',                   # исходная таблица
            'users',                          # целевая таблица
            ['whoid'],                        # колонка в исходной таблице
            ['id']                            # колонка в целевой таблице
        )

        # 3. Заполняем whoid на основе существующих данных
        # Используем raw SQL для обновления
        op.execute("""
            UPDATE chat_messages cm
            SET whoid = CASE
                WHEN cm.sender_id = c.user1_id THEN c.user2_id
                WHEN cm.sender_id = c.user2_id THEN c.user1_id
                ELSE cm.sender_id
            END
            FROM chats c
            WHERE cm.chat_id = c.id AND cm.whoid IS NULL
        """)

        # 4. Делаем колонку обязательной (NOT NULL)
        op.alter_column('chat_messages', 'whoid',
            existing_type=sa.Integer(),
            nullable=False
        )

        print("✅ Колонка whoid успешно добавлена в таблицу chat_messages")
    else:
        print("⚠️ Колонка whoid уже существует в таблице chat_messages")


def downgrade() -> None:
    """Откат миграции - удаляем поле whoid"""

    # Проверяем, существует ли колонка
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('chat_messages')]

    if 'whoid' in columns:
        # 1. Удаляем foreign key constraint
        op.drop_constraint('fk_chat_messages_whoid_users', 'chat_messages', type_='foreignkey')

        # 2. Удаляем колонку
        op.drop_column('chat_messages', 'whoid')

        print("✅ Колонка whoid успешно удалена из таблицы chat_messages")
    else:
        print("⚠️ Колонка whoid не найдена в таблице chat_messages")
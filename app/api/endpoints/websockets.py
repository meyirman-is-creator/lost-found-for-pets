from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional, Set
import json
from datetime import datetime
import asyncio
import logging

from app.api.dependencies import get_current_user_from_token
from app.core.config import settings
from app.db.database import get_db, SessionLocal
from app.models.models import User, Chat, ChatMessage
from app.schemas.schemas import WebSocketMessage, WebSocketResponse, MessageType, WebSocketMessageRequest, \
    WebSocketStatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Хранение активных соединений: chat_id -> {user_id: WebSocket}
active_connections: Dict[int, Dict[int, WebSocket]] = {}

# Хранение информации о печатающих пользователях: chat_id -> set(user_ids)
typing_users: Dict[int, Set[int]] = {}

# Хранение информации о статусе пользователей: user_id -> {"is_online": bool, "last_active_at": datetime}
user_status: Dict[int, Dict[str, Any]] = {}


async def update_user_status(db: Session, user_id: int, is_online: bool):
    """Обновляет статус пользователя в базе данных"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_online = is_online
        user.last_active_at = datetime.utcnow()
        db.add(user)
        db.commit()


async def broadcast_user_status(user_id: int, is_online: bool, last_active_at: Optional[datetime] = None):
    """Отправляет статус пользователя всем его собеседникам"""
    status_type = MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE

    # Если не указано время последней активности, используем текущее время
    if not last_active_at:
        last_active_at = datetime.utcnow()

    # Обновляем статус в нашем локальном хранилище
    user_status[user_id] = {
        "is_online": is_online,
        "last_active_at": last_active_at
    }

    # Находим все чаты, в которых участвует пользователь
    user_chats = []
    for chat_id, users in active_connections.items():
        for uid in users:
            if uid != user_id:  # Другой участник чата
                try:
                    # Отправляем статус пользователя
                    status_response = WebSocketStatusResponse(
                        user_id=user_id,
                        status_type=status_type,
                        last_active_at=last_active_at
                    )
                    await users[uid].send_text(status_response.model_dump_json())
                except Exception as e:
                    logger.error(f"Error sending status update: {e}")


@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        chat_id: int,
        token: str = Query(None)  # Явно указываем, что токен берется из параметра запроса
):
    """
    WebSocket endpoint для чата
    """
    db = SessionLocal()
    try:
        logger.info(f"Попытка подключения к WebSocket, chat_id: {chat_id}, token предоставлен: {bool(token)}")

        # Проверка наличия токена
        if not token:
            logger.warning("Отсутствует токен аутентификации")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Аутентификация пользователя по токену
        try:
            current_user = await get_current_user_from_token(token, db)
            logger.info(f"Успешная аутентификация пользователя: {current_user.id} ({current_user.email})")
        except Exception as e:
            logger.error(f"Ошибка аутентификации: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Проверка, что пользователь является участником чата
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Чат с id {chat_id} не найден")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
            logger.warning(f"Пользователь {current_user.id} не является участником чата {chat_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Принять соединение
        await websocket.accept()
        logger.info(f"WebSocket соединение принято для пользователя {current_user.id} в чате {chat_id}")

        # Добавление нового соединения
        if chat_id not in active_connections:
            active_connections[chat_id] = {}
        active_connections[chat_id][current_user.id] = websocket

        # Инициализация набора печатающих пользователей для чата, если его нет
        if chat_id not in typing_users:
            typing_users[chat_id] = set()

        # Обновляем статус пользователя как онлайн
        await update_user_status(db, current_user.id, True)

        # Отправляем уведомление о статусе онлайн всем участникам чатов
        await broadcast_user_status(current_user.id, True)

        # Отметить все сообщения как прочитанные для текущего пользователя
        unread_messages = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.sender_id != current_user.id,
            ChatMessage.is_read == False
        ).all()

        if unread_messages:
            # Обновляем статус сообщений в базе данных
            for message in unread_messages:
                message.is_read = True
            db.commit()

            # Отправляем подтверждения о прочтении отправителю
            other_user_id = chat.user1_id if chat.user1_id != current_user.id else chat.user2_id
            if other_user_id in active_connections.get(chat_id, {}):
                for message in unread_messages:
                    read_notification = WebSocketStatusResponse(
                        user_id=current_user.id,
                        status_type=MessageType.MESSAGE_READ,
                        message_id=message.id
                    )
                    try:
                        await active_connections[chat_id][other_user_id].send_text(read_notification.model_dump_json())
                    except Exception as e:
                        logger.error(f"Error sending read receipt: {e}")

        try:
            # Отправим пользователю информацию о статусе собеседника
            other_user_id = chat.user1_id if chat.user1_id != current_user.id else chat.user2_id
            other_user = db.query(User).filter(User.id == other_user_id).first()

            if other_user:
                is_online = other_user_id in user_status and user_status[other_user_id]["is_online"]
                status_response = WebSocketStatusResponse(
                    user_id=other_user_id,
                    status_type=MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE,
                    last_active_at=other_user.last_active_at
                )
                await websocket.send_text(status_response.model_dump_json())

            # Отправим тестовое сообщение, чтобы убедиться, что соединение работает
            test_message = json.dumps({"message": "Соединение установлено успешно", "type": "system"})
            await websocket.send_text(test_message)

            # Бесконечный цикл для получения сообщений
            while True:
                # Ожидание сообщения от клиента
                data = await websocket.receive_text()
                try:
                    logger.info(f"Получено сообщение от пользователя {current_user.id}: {data[:100]}...")
                    message_data = json.loads(data)
                    ws_message = WebSocketMessageRequest(**message_data)

                    # Обновление времени последней активности пользователя
                    await update_user_status(db, current_user.id, True)

                    # Обработка различных типов сообщений
                    if ws_message.message_type == MessageType.TEXT:
                        # Текстовое сообщение
                        content = ws_message.content.strip() if ws_message.content else ""

                        if not content:
                            continue

                        # Создание нового сообщения в базе данных
                        new_message = ChatMessage(
                            chat_id=chat_id,
                            sender_id=current_user.id,
                            content=content,
                            is_read=False
                        )
                        db.add(new_message)
                        db.commit()
                        db.refresh(new_message)

                        # Обновление времени последнего сообщения в чате
                        chat.updated_at = datetime.utcnow()
                        db.add(chat)
                        db.commit()

                        # Удаляем пользователя из списка печатающих
                        if current_user.id in typing_users.get(chat_id, set()):
                            typing_users[chat_id].remove(current_user.id)

                        # Создание ответа
                        response = WebSocketResponse(
                            message_id=new_message.id,
                            content=new_message.content,
                            chat_id=new_message.chat_id,
                            sender_id=new_message.sender_id,
                            is_read=new_message.is_read,
                            created_at=new_message.created_at
                        )
                        response_json = response.model_dump_json()

                        # Отправка сообщения всем участникам чата
                        for user_id, conn in active_connections.get(chat_id, {}).items():
                            try:
                                # Если это получатель сообщения и он онлайн, отмечаем как прочитанное
                                if user_id != current_user.id:
                                    new_message.is_read = True
                                    db.add(new_message)
                                    db.commit()

                                await conn.send_text(response_json)
                            except Exception as e:
                                logger.error(f"Error sending message: {e}")

                    elif ws_message.message_type == MessageType.TYPING_STARTED:
                        # Пользователь начал печатать
                        typing_users[chat_id].add(current_user.id)

                        # Уведомляем других участников чата
                        for user_id, conn in active_connections.get(chat_id, {}).items():
                            if user_id != current_user.id:
                                typing_notification = WebSocketStatusResponse(
                                    user_id=current_user.id,
                                    status_type=MessageType.TYPING_STARTED
                                )
                                try:
                                    await conn.send_text(typing_notification.model_dump_json())
                                except Exception as e:
                                    logger.error(f"Error sending typing notification: {e}")

                    elif ws_message.message_type == MessageType.TYPING_ENDED:
                        # Пользователь перестал печатать
                        if current_user.id in typing_users.get(chat_id, set()):
                            typing_users[chat_id].remove(current_user.id)

                        # Уведомляем других участников чата
                        for user_id, conn in active_connections.get(chat_id, {}).items():
                            if user_id != current_user.id:
                                typing_notification = WebSocketStatusResponse(
                                    user_id=current_user.id,
                                    status_type=MessageType.TYPING_ENDED
                                )
                                try:
                                    await conn.send_text(typing_notification.model_dump_json())
                                except Exception as e:
                                    logger.error(f"Error sending typing notification: {e}")

                    elif ws_message.message_type == MessageType.MESSAGE_READ:
                        # Пользователь прочитал сообщение
                        if ws_message.message_id:
                            message = db.query(ChatMessage).filter(
                                ChatMessage.id == ws_message.message_id,
                                ChatMessage.chat_id == chat_id
                            ).first()

                            if message and not message.is_read:
                                message.is_read = True
                                db.add(message)
                                db.commit()

                                # Уведомляем отправителя о прочтении
                                if message.sender_id in active_connections.get(chat_id, {}):
                                    read_notification = WebSocketStatusResponse(
                                        user_id=current_user.id,
                                        status_type=MessageType.MESSAGE_READ,
                                        message_id=message.id
                                    )
                                    try:
                                        await active_connections[chat_id][message.sender_id].send_text(
                                            read_notification.model_dump_json())
                                    except Exception as e:
                                        logger.error(f"Error sending read receipt: {e}")

                except json.JSONDecodeError:
                    logger.error("Received invalid JSON data")
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")

        except WebSocketDisconnect:
            logger.info(f"WebSocket отключен для пользователя {current_user.id} в чате {chat_id}")
            # Удаляем соединение при отключении
            if chat_id in active_connections and current_user.id in active_connections[chat_id]:
                del active_connections[chat_id][current_user.id]
                if not active_connections[chat_id]:
                    del active_connections[chat_id]

            # Удаляем пользователя из списка печатающих
            if chat_id in typing_users and current_user.id in typing_users[chat_id]:
                typing_users[chat_id].remove(current_user.id)
                if not typing_users[chat_id]:
                    del typing_users[chat_id]

        except Exception as e:
            logger.error(f"Unexpected error in WebSocket handler: {e}")

        finally:
            # Обновляем статус пользователя как оффлайн
            await update_user_status(db, current_user.id, False)

            # Отправляем уведомление о статусе оффлайн всем участникам чатов
            await broadcast_user_status(current_user.id, False)

    except Exception as e:
        logger.error(f"Ошибка в WebSocket: {e}")

    finally:
        db.close()